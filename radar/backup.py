import json
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core import serializers
from django.core.management.color import no_style
from django.db import connection, transaction
from django.utils import timezone

from .catalog import CATALOG_RELEASES
from .forms import SOURCE_FIELDS
from .models import Event, EventReference, Observation, Preferences, Runtime, Source
from .network import public_url

BACKUP_VERSION = 1
MODELS = (Source, Event, EventReference, Observation, Preferences)


def preferences_row():
    return Preferences.objects.get_or_create(pk=1)[0]


def source_configuration(source):
    return {name: getattr(source, name) for name in SOURCE_FIELDS}


def export_backup():
    nested = connection.in_atomic_block
    with transaction.atomic():
        if connection.vendor == "postgresql" and not nested:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        records = [row for model in MODELS for row in serializers.serialize("python", model.objects.order_by("pk").iterator())]
        return {"schema": BACKUP_VERSION, "kind": "ai-radar-backup", "exported_at": timezone.now(), "records": records}


def checked_backup(document):
    if not isinstance(document, dict) or document.get("schema") != BACKUP_VERSION or document.get("kind") != "ai-radar-backup":
        raise ValueError("不支持的备份格式或版本")
    records = document.get("records")
    if not isinstance(records, list) or len(records) > 120_000:
        raise ValueError("备份记录缺失或超出限制")
    labels = {model._meta.label_lower for model in MODELS}
    seen = set()
    for row in records:
        if not isinstance(row, dict) or row.get("model") not in labels or type(row.get("pk")) is not int or row["pk"] < 1:
            raise ValueError("备份包含无效记录")
        key = (row["model"], row["pk"])
        if key in seen:
            raise ValueError("备份包含重复记录")
        seen.add(key)
        fields = row.get("fields")
        if not isinstance(fields, dict):
            raise ValueError("备份缺少字段")
        for name in ("url", "canonical_url", "bridge_url", "fetch_url"):
            if fields.get(name):
                public_url(fields[name], source=row["model"] == "radar.source")
        evidence = fields.get("evidence")
        if evidence is not None:
            if not isinstance(evidence, dict):
                raise ValueError("福利证据格式无效")
            if evidence.get("official_url"):
                public_url(evidence["official_url"])
        if row["model"] == "radar.eventreference":
            if fields.get("event") is None:
                raise ValueError("事件来源缺少事件")
        if row["model"] == "radar.preferences" and row["pk"] != 1:
            raise ValueError("备份包含未知配置")
    return records


@transaction.atomic
def restore_backup(document, *, replace=False):
    records = checked_backup(document)
    Runtime.objects.select_for_update().get_or_create(pk="ingest")
    if not replace and (Event.objects.exists() or Observation.objects.exists() or Source.objects.exists()):
        raise ValueError("目标已有数据，需要显式确认替换")
    for model in reversed(MODELS):
        model.objects.all().delete()
    for row in serializers.deserialize("python", records, ignorenonexistent=False, handle_forward_references=True):
        if isinstance(row.object, Source):
            row.object.lease_until = None
        row.save()
        if row.deferred_fields:
            raise ValueError("备份记录顺序或关联有误")
    connection.check_constraints()
    with connection.cursor() as cursor:
        for statement in connection.ops.sequence_reset_sql(no_style(), MODELS):
            cursor.execute(statement)
    for key, _ in CATALOG_RELEASES:
        Runtime.objects.get_or_create(pk=key)
    return len(records)


def read_json(file, limit=20 * 1024 * 1024):
    data = file.read(limit + 1)
    if len(data) > limit:
        raise ValueError("文件超出上传大小限制")
    return json.loads(data.decode("utf-8-sig"))


def sqlite_daily_backup():
    if not settings.PRODUCTION or connection.vendor != "sqlite" or not settings.SQLITE_PATH:
        return
    source = Path(settings.SQLITE_PATH)
    directory = source.parent / "backups"
    directory.mkdir(mode=0o700, exist_ok=True)
    final = directory / f"radar-{timezone.localdate().isoformat()}.sqlite3"
    if final.exists():
        return
    temporary = final.with_suffix(".tmp")
    try:
        reader = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True, timeout=5)
        writer = sqlite3.connect(temporary, timeout=5)
        try:
            reader.backup(writer)
            if writer.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("SQLite backup integrity check failed.")
        finally:
            writer.close()
            reader.close()
        temporary.replace(final)
    finally:
        temporary.unlink(missing_ok=True)
    for old in sorted(directory.glob("radar-????-??-??.sqlite3"), reverse=True)[7:]:
        old.unlink()
