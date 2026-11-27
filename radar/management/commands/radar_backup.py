import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from radar.backup import export_backup, read_json, restore_backup


class Command(BaseCommand):
    help = "Export a user-data backup or restore into an empty database."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["export", "restore"])
        parser.add_argument("file", type=Path)
        parser.add_argument("--replace", action="store_true")

    def handle(self, *args, **options):
        path = options["file"]
        try:
            if options["action"] == "export":
                with path.open("x", encoding="utf-8", newline="\n") as output:
                    json.dump(export_backup(), output, cls=DjangoJSONEncoder, ensure_ascii=False)
                self.stdout.write("Backup exported.")
            else:
                with path.open("rb") as source:
                    count = restore_backup(read_json(source, 150 * 1024 * 1024), replace=options["replace"])
                self.stdout.write(f"Restored {count} records.")
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from None
