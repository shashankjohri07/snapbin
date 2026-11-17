import logging
from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


def tracked(name):
    """Record each run of a job in PipelineRun (status, duration, rows, error)."""
    from functools import wraps

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from .models import PipelineRun

            run = PipelineRun.objects.create(name=name)
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                run.status, run.error = "failed", str(exc)[:1000]
                run.finished_at = timezone.now()
                run.save()
                raise
            run.rows_processed = result if isinstance(result, int) else 0
            run.finished_at = timezone.now()
            run.save()
            return result

        return wrapper

    return decorator


@shared_task
@tracked("cleanup_expired_pastes")
def cleanup_expired_pastes():
    from .models import Paste

    expired = Paste.objects.filter(
        expires_at__lte=timezone.now(), is_active=True
    )
    short_codes = list(expired.values_list("short_code", flat=True))
    count = expired.update(is_active=False)

    for code in short_codes:
        try:
            cache.delete(f"paste:{code}")
        except Exception:
            pass

    logger.info("Cleaned up %d expired pastes", count)
    return count


def _rollup_day(day):  # returns number of rows written
    """Rebuild the DailyStats rows for one day from raw events (idempotent)."""
    from datetime import datetime, time, timedelta

    from django.db import transaction
    from django.db.models import Count

    from .models import DailyStats, Paste, PasteViewEvent

    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = start + timedelta(days=1)

    views = {
        r["language"]: r
        for r in PasteViewEvent.objects.filter(viewed_at__gte=start, viewed_at__lt=end)
        .values("language")
        .annotate(views=Count("id"), unique=Count("short_code", distinct=True))
    }
    created = {
        r["language"]: r["n"]
        for r in Paste.objects.filter(created_at__gte=start, created_at__lt=end)
        .values("language")
        .annotate(n=Count("id"))
    }

    with transaction.atomic():
        DailyStats.objects.filter(date=day).delete()
        rows = DailyStats.objects.bulk_create(
            [
                DailyStats(
                    date=day,
                    language=lang,
                    views=views.get(lang, {}).get("views", 0),
                    unique_pastes_viewed=views.get(lang, {}).get("unique", 0),
                    pastes_created=created.get(lang, 0),
                )
                for lang in set(views) | set(created)
            ]
        )
    return len(rows)


@shared_task
@tracked("rollup_daily_stats")
def rollup_daily_stats(days=2):
    """ETL: aggregate raw view events + paste creations into DailyStats."""
    today = timezone.now().date()
    rows = sum(_rollup_day(today - timedelta(days=offset)) for offset in range(days))
    logger.info("Rolled up %d stat rows for last %d day(s)", rows, days)
    return rows


@shared_task
@tracked("prune_old_events")
def prune_old_events(retention_days=30):
    """Retention policy: drop raw events older than N days (rollups are kept)."""
    from .models import PasteViewEvent

    cutoff = timezone.now() - timedelta(days=retention_days)
    deleted, _ = PasteViewEvent.objects.filter(viewed_at__lt=cutoff).delete()
    logger.info("Pruned %d old view events", deleted)
    return deleted
