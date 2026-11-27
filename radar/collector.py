import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.db import close_old_connections, connection, transaction
from django.db.models import Q
from django.utils import timezone

from .adapters import collect_source
from .backup import sqlite_daily_backup
from .benchmarks import update_benchmarks
from .intelligence import canonical, ingest
from .models import Event, EventReference, FetchRun, LoginWindow, Runtime, Source
from .network import FetchError

log = logging.getLogger(__name__)


def claim_source(source_id, manual=False):
    now = timezone.now()
    lease = now + timedelta(minutes=4)
    eligible = Source.objects.filter(pk=source_id).filter(Q(lease_until__isnull=True) | Q(lease_until__lt=now))
    if not manual:
        eligible = eligible.filter(enabled=True, next_check__lte=now)
    if not eligible.update(lease_until=lease, last_checked=now):
        return None
    return Source.objects.filter(pk=source_id, lease_until=lease).first()


def collect_one(source_id, manual=False):
    close_old_connections()
    source = claim_source(source_id, manual)
    if source is None:
        return None
    started = time.monotonic()
    error, retry, batch, status = "", 0, None, "ok"
    try:
        batch = collect_source(source)
    except FetchError as exc:
        error, status, retry = str(exc), exc.status, exc.retry_seconds
    except Exception as exc:
        error, status = f"解析异常（{type(exc).__name__}）", "error"
    elapsed_ms = int((time.monotonic() - started) * 1000)
    now = timezone.now()
    with transaction.atomic():
        Runtime.objects.select_for_update().get_or_create(pk="ingest", defaults={"at": now})
        locked = Source.objects.select_for_update().filter(pk=source_id, revision=source.revision, lease_until=source.lease_until).first()
        if locked is None:
            return None
        locked.last_count = 0
        if batch is not None:
            locked.last_count = ingest(locked, batch.items, now)
            locked.detected_kind = batch.kind
            locked.fetch_url = batch.url
            if batch.fingerprints:
                locked.fingerprints = batch.fingerprints
            if locked.fingerprints and batch.kind == Source.Kind.WEB:
                digest = hashlib.sha256((canonical(batch.url) + locked.fingerprints[-1]).encode()).hexdigest()
                event_id = EventReference.objects.filter(digest=digest, source=locked).values_list("event_id", flat=True).first()
                if event_id:
                    Event.objects.filter(pk=event_id, first_party=True).update(checked_at=now)
            locked.etag = batch.etag[:300]
            locked.last_modified = batch.modified[:140]
            locked.last_success = now
            locked.streak = 0
        else:
            locked.streak += 1
            if status == "unsupported":
                locked.detected_kind = Source.Kind.X if source.kind in {Source.Kind.AUTO, Source.Kind.X} and "X " in error else source.kind
        wait_minutes = locked.interval if not error else min(1440, max(5, min(locked.interval, 60)) * 2 ** min(locked.streak - 1, 8))
        if status == "unsupported":
            wait_minutes = 1440
        locked.error = error[:300]
        locked.next_check = now + timedelta(seconds=max(retry, wait_minutes * 60))
        locked.lease_until = None
        locked.save()
        run = FetchRun.objects.create(
            source=locked, at=now, status=status, parsed=len(batch.items) if batch else 0,
            added=locked.last_count, elapsed_ms=elapsed_ms, error=locked.error,
        )
    log.info("source=%s status=%s parsed=%s added=%s duration_ms=%s", source_id, status, run.parsed, run.added, elapsed_ms)
    return run


def run_thread(source_id):
    try:
        return collect_one(source_id)
    finally:
        connection.close()


def run_due(limit=20, workers=4):
    now = timezone.now()
    Runtime.objects.update_or_create(pk="heartbeat", defaults={"at": now})
    source_ids = list(Source.objects.filter(enabled=True, next_check__lte=now)
                      .filter(Q(lease_until__isnull=True) | Q(lease_until__lt=now))
                      .order_by("next_check", "-weight").values_list("pk", flat=True)[:limit])
    if not source_ids:
        return []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="radar-fetch") as pool:
        futures = [pool.submit(run_thread, source_id) for source_id in source_ids]
        results = []
        for future in futures:
            try:
                if run := future.result():
                    results.append(run)
            except Exception as exc:
                log.error("source task failed (%s)", type(exc).__name__)
    Runtime.objects.update_or_create(pk="heartbeat", defaults={"at": timezone.now()})
    return results


def maintenance():
    now = timezone.now()
    last = Runtime.objects.filter(pk="maintenance").values_list("at", flat=True).first()
    if last and last > now - timedelta(hours=24):
        return
    sqlite_daily_backup()
    with transaction.atomic():
        FetchRun.objects.filter(at__lt=now - timedelta(days=45)).delete()
        LoginWindow.objects.filter(at__lt=now - timedelta(days=1)).delete()
        Session.objects.filter(expire_date__lt=now).delete()
        Runtime.objects.update_or_create(pk="maintenance", defaults={"at": now})


def scheduler(stop_event, poll_seconds=45):
    while not stop_event.is_set():
        try:
            close_old_connections()
            run_due(limit=8, workers=4)
            try:
                update_benchmarks()
            except FetchError as exc:
                log.warning("benchmark refresh failed: %s", exc)
            maintenance()
        except Exception as exc:
            log.error("scheduler tick failed (%s)", type(exc).__name__)
        finally:
            connection.close()
        stop_event.wait(poll_seconds)
