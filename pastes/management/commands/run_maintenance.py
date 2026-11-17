from django.core.management.base import BaseCommand

from pastes.quality import run_all_checks
from pastes.tasks import cleanup_expired_pastes, load_hourly_facts, prune_old_events, rollup_daily_stats


class Command(BaseCommand):
    help = (
        "Run the periodic jobs once (expired-paste cleanup, daily stats rollup, "
        "event retention). Use as a cron job where no Celery worker is available."
    )

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=2, help="Days to re-aggregate")
        parser.add_argument("--retention-days", type=int, default=30)

    def handle(self, *args, **opts):
        expired = cleanup_expired_pastes()
        loaded = load_hourly_facts()
        rollup_daily_stats(opts["days"])
        pruned = prune_old_events(opts["retention_days"])
        self.stdout.write(
            self.style.SUCCESS(f"cleaned={expired} loaded_events={loaded} rolled_up_days={opts['days']} pruned={pruned}")
        )
        for r in run_all_checks():
            self.stdout.write(f"[{'PASS' if r['passed'] else 'FAIL'}] {r['check']}: {r['detail']}")
