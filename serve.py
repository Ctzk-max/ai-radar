import logging
import os
import re
import threading
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "radar.settings")

import django

django.setup()

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from waitress import serve

from radar.collector import scheduler
from radar.security import password_hash


def startup_failure(exc):
    cause = exc.__cause__ or exc
    code = getattr(cause, "sqlstate", "") or ""
    if not re.fullmatch(r"[0-9A-Z]{5}", code):
        code = "none"
    detail = str(cause).casefold()
    signals = [
        ("authentication", ("password authentication failed", "no password supplied", "pg_hba.conf")),
        ("database-missing", ("database", "does not exist")),
        ("dns", ("could not translate host name", "name or service not known", "temporary failure in name resolution", "failed to resolve host")),
        ("timeout", ("timeout expired", "timed out")),
        ("network", ("connection refused", "network is unreachable", "no route to host")),
        ("tls", ("ssl", "tls", "certificate")),
        ("permissions", ("permission denied", "must be owner", "no schema has been selected")),
        ("connection-closed", ("server closed the connection", "connection reset", "eof detected")),
    ]
    for reason, markers in signals:
        if (all if reason == "database-missing" else any)(marker in detail for marker in markers):
            return code, reason
    return code, "unknown"


def main():
    logger = logging.getLogger("radar")
    stage = "connect"
    try:
        if settings.PRODUCTION and connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("CREATE SCHEMA IF NOT EXISTS radar")
        elif settings.PRODUCTION and connection.vendor == "sqlite":
            data = Path(settings.SQLITE_PATH)
            data.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not data.is_file() and not settings.SQLITE_INIT:
                raise FileNotFoundError("Persistent database is missing; restore before starting.")
            os.umask(0o077)
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA journal_mode=WAL")
        stage = "authentication"
        password_hash(settings.ADMIN_PASSWORD_HASH, settings.LEGACY_PASSWORD)
        stage = "migrations"
        call_command("migrate", interactive=False, verbosity=0)
        stage = "catalog"
        call_command("seed_sources", verbosity=0)
        stage = "static"
        call_command("collectstatic", interactive=False, verbosity=0)
        from radar.wsgi import application
    except Exception as exc:
        code, reason = startup_failure(exc)
        logger.critical("startup failed stage=%s type=%s sqlstate=%s reason=%s", stage, type(exc).__name__, code, reason)
        return 1
    stop = threading.Event()
    worker = None
    if os.getenv("RADAR_SCHEDULER", "1") == "1":
        worker = threading.Thread(target=scheduler, args=(stop,), name="radar-scheduler", daemon=True)
        worker.start()
    try:
        proxy = {"trusted_proxy": "*", "trusted_proxy_count": 1, "trusted_proxy_headers": {"x-forwarded-proto"}} if settings.PRODUCTION else {}
        serve(
            application, host="0.0.0.0" if settings.PRODUCTION else "127.0.0.1",
            port=int(os.getenv("PORT", "8018")), threads=6, channel_timeout=25,
            max_request_body_size=22 * 1024 * 1024, max_request_header_size=32 * 1024,
            clear_untrusted_proxy_headers=True,
            **proxy,
        )
    finally:
        stop.set()
        if worker:
            worker.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
