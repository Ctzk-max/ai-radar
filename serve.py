import logging
import os
import threading

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "radar.settings")

import django

django.setup()

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from waitress import serve

from radar.collector import scheduler
from radar.security import password_hash


def main():
    logger = logging.getLogger("radar")
    try:
        if settings.PRODUCTION:
            with connection.cursor() as cursor:
                cursor.execute("CREATE SCHEMA IF NOT EXISTS radar")
        password_hash(settings.ADMIN_PASSWORD_HASH, settings.LEGACY_PASSWORD)
        call_command("migrate", interactive=False, verbosity=0)
        call_command("seed_sources", verbosity=0)
        call_command("collectstatic", interactive=False, verbosity=0)
        from radar.wsgi import application
    except Exception as exc:
        logger.critical("startup failed (%s); check application environment and database access", type(exc).__name__)
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
