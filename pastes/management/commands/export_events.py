import csv

from django.core.management.base import BaseCommand

from pastes.models import PasteViewEvent


class Command(BaseCommand):
    help = "Export raw view events to CSV (input for analytics/spark_rollup.py)."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="events.csv")

    def handle(self, *args, **opts):
        rows = PasteViewEvent.objects.values_list("short_code", "language", "viewed_at").iterator()
        with open(opts["output"], "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["short_code", "language", "viewed_at"])
            count = 0
            for code, lang, ts in rows:
                writer.writerow([code, lang, ts.isoformat()])
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Exported {count} events to {opts['output']}"))
