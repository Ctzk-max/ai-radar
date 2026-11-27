from django.core.management.base import BaseCommand
from django.db import transaction

from radar.catalog import SOURCES
from radar.models import Runtime, Source


class Command(BaseCommand):
    help = "Install the checked source catalog one time."

    @transaction.atomic
    def handle(self, *args, **options):
        flag, created = Runtime.objects.get_or_create(pk="seed_v1")
        if not created:
            self.stdout.write("Source catalog previously installed.")
            return
        count = 0
        for definition in SOURCES:
            fields = definition.copy()
            url = fields.pop("url")
            _, was_created = Source.objects.get_or_create(url=url, defaults=fields)
            count += was_created
        self.stdout.write(f"Added {count} catalog entries.")
