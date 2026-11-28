from django.core.management.base import BaseCommand
from django.db import transaction

from radar.catalog import CATALOG_RELEASES
from radar.models import Runtime, Source

class Command(BaseCommand):
    help = "Install each checked catalog release once without overwriting source settings."

    @transaction.atomic
    def handle(self, *args, **options):
        count = 0
        for key, definitions in CATALOG_RELEASES:
            _, created = Runtime.objects.get_or_create(pk=key)
            if not created:
                continue
            for definition in definitions:
                fields = definition.copy()
                url = fields.pop("url")
                _, was_created = Source.objects.get_or_create(url=url, defaults=fields)
                count += was_created
        self.stdout.write(f"Added {count} catalog entries.")
