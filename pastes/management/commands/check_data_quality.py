from django.core.management.base import BaseCommand, CommandError

from pastes.quality import run_all_checks


class Command(BaseCommand):
    help = "Run data quality checks; exits non-zero if any check fails (CI/cron friendly)."

    def handle(self, *args, **opts):
        failed = 0
        for r in run_all_checks():
            line = f"[{'PASS' if r['passed'] else 'FAIL'}] {r['check']}: {r['detail']}"
            self.stdout.write(self.style.SUCCESS(line) if r["passed"] else self.style.ERROR(line))
            failed += not r["passed"]
        if failed:
            raise CommandError(f"{failed} data quality check(s) failed")
