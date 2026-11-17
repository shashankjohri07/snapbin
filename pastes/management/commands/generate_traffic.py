import math
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from pastes.models import Paste, PasteViewEvent
from pastes.utils import generate_short_code

LANGUAGES = ["python", "javascript", "sql", "java", "go", "bash", "typescript", "rust", "html", "yaml"]
LANG_WEIGHTS = [30, 24, 12, 8, 6, 6, 5, 4, 3, 2]
PREFIX = "[synthetic] "


class Command(BaseCommand):
    help = (
        "Generate synthetic pastes and view events to test the pipeline at volume. "
        "Pastes are titled '[synthetic] ...'; remove everything with --purge. "
        "Do not run against production data you care about."
    )

    def add_arguments(self, parser):
        parser.add_argument("--pastes", type=int, default=2000)
        parser.add_argument("--events", type=int, default=200_000)
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--purge", action="store_true", help="Delete synthetic data and exit")

    def handle(self, *args, **opts):
        if opts["purge"]:
            codes = list(Paste.objects.filter(title__startswith=PREFIX).values_list("short_code", flat=True))
            PasteViewEvent.objects.filter(short_code__in=codes).delete()
            deleted, _ = Paste.objects.filter(title__startswith=PREFIX).delete()
            self.stdout.write(self.style.SUCCESS(f"Purged {deleted} synthetic pastes and their events"))
            return

        rng = random.Random(opts["seed"])
        now = timezone.now()
        langs = rng.choices(LANGUAGES, weights=LANG_WEIGHTS, k=opts["pastes"])

        codes, seen = [], set()
        while len(codes) < opts["pastes"]:
            c = generate_short_code()
            if c not in seen:
                seen.add(c)
                codes.append(c)
        pastes = [
            Paste(
                short_code=c,
                title=f"{PREFIX}{i}",
                content=f"-- synthetic {i}",
                language=lang,
                created_at=now,
            )
            for i, (c, lang) in enumerate(zip(codes, langs))
        ]
        Paste.objects.bulk_create(pastes, batch_size=2000)

        # Zipf-like popularity: a few pastes get most of the views
        weights = [1 / math.sqrt(i + 1) for i in range(opts["pastes"])]
        day_weights = [0.6 if (now - timedelta(days=d)).weekday() >= 5 else 1.0 for d in range(opts["days"])]
        hour_weights = [1 + 3 * math.exp(-((h - 15) ** 2) / 18) for h in range(24)]  # peak around 15:00 UTC

        batch, total = [], 0
        picks = rng.choices(range(opts["pastes"]), weights=weights, k=opts["events"])
        days = rng.choices(range(opts["days"]), weights=day_weights, k=opts["events"])
        hours = rng.choices(range(24), weights=hour_weights, k=opts["events"])
        for p, d, h in zip(picks, days, hours):
            ts = (now - timedelta(days=d)).replace(hour=h, minute=rng.randrange(60), second=rng.randrange(60))
            batch.append(PasteViewEvent(short_code=codes[p], language=langs[p], viewed_at=ts))
            if len(batch) >= 10_000:
                PasteViewEvent.objects.bulk_create(batch)
                total += len(batch)
                batch = []
        if batch:
            PasteViewEvent.objects.bulk_create(batch)
            total += len(batch)
        self.stdout.write(self.style.SUCCESS(f"Created {len(pastes)} pastes and {total} view events"))
