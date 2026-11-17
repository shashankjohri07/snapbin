"""Data quality checks for the analytics pipeline (reconciliation, orphans, freshness)."""
from datetime import datetime, time, timedelta

from django.db.models import Sum
from django.utils import timezone

from .models import DailyStats, HourlyFact, Paste, PasteViewEvent, PipelineRun, PipelineWatermark


def check_reconciliation(days=3):
    """Rollup totals must equal the raw event counts for each recent day."""
    tz = timezone.get_current_timezone()
    today = timezone.now().date()
    mismatches = []
    for offset in range(days):
        day = today - timedelta(days=offset)
        start = timezone.make_aware(datetime.combine(day, time.min), tz)
        raw = PasteViewEvent.objects.filter(
            viewed_at__gte=start, viewed_at__lt=start + timedelta(days=1)
        ).count()
        rolled = DailyStats.objects.filter(date=day).aggregate(s=Sum("views"))["s"] or 0
        if raw != rolled:
            mismatches.append(f"{day}: raw={raw} rollup={rolled}")
    return {
        "check": "rollup_matches_raw_events",
        "passed": not mismatches,
        "detail": "; ".join(mismatches) or f"last {days} days reconcile",
    }


def check_orphan_events():
    """Every event must point to an existing paste (referential integrity)."""
    known = set(Paste.objects.values_list("short_code", flat=True))
    seen = set(PasteViewEvent.objects.values_list("short_code", flat=True).distinct())
    orphans = sorted(seen - known)
    return {
        "check": "no_orphan_events",
        "passed": not orphans,
        "detail": f"{len(orphans)} orphan short_codes" + (f": {orphans[:5]}" if orphans else ""),
    }


def check_freshness(max_age_hours=3):
    """The rollup job must have succeeded recently."""
    last = PipelineRun.objects.filter(name="rollup_daily_stats", status="success").first()
    if not last:
        return {"check": "rollup_fresh", "passed": False, "detail": "rollup has never succeeded"}
    age = timezone.now() - last.started_at
    return {
        "check": "rollup_fresh",
        "passed": age <= timedelta(hours=max_age_hours),
        "detail": f"last success {int(age.total_seconds() // 60)} min ago",
    }


def check_fact_reconciliation():
    """Fact table total must equal the number of events up to the watermark."""
    wm = PipelineWatermark.objects.filter(name="hourly_facts").first()
    upto = wm.last_event_id if wm else 0
    expected = PasteViewEvent.objects.filter(id__lte=upto).count()
    actual = HourlyFact.objects.aggregate(s=Sum("views"))["s"] or 0
    return {
        "check": "fact_matches_loaded_events",
        "passed": expected == actual,
        "detail": f"events<=watermark={expected} fact_views={actual} (watermark={upto})",
    }


def run_all_checks():
    return [
        check_reconciliation(),
        check_fact_reconciliation(),
        check_orphan_events(),
        check_freshness(),
    ]
