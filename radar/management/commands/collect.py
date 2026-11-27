from django.core.management.base import BaseCommand, CommandError

from radar.collector import collect_one, run_due
from radar.models import Source


class Command(BaseCommand):
    help = "Collect due sources (or one requested source)."

    def add_arguments(self, parser):
        parser.add_argument("--source", type=int)
        parser.add_argument("--limit", type=int, default=30)

    def handle(self, *args, **options):
        if options["source"]:
            if not Source.objects.filter(pk=options["source"]).exists():
                raise CommandError("Unknown source.")
            run = collect_one(options["source"], manual=True)
            runs = [run] if run else []
        else:
            runs = run_due(limit=min(100, max(1, options["limit"])))
        self.stdout.write(f"sources={len(runs)} success={sum(r.status == 'ok' for r in runs)} new={sum(r.added for r in runs)}")
