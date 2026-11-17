"""Lazy scheduler for hosts without a Celery worker (e.g. Render free tier).

Runs a job inline if its last successful run is older than `max_age`. A cache
lock stops concurrent requests from starting the same job twice. When a real
Celery beat worker is running the jobs are already fresh, so this is a no-op.
"""
import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from .models import PipelineRun
from . import tasks

logger = logging.getLogger(__name__)

JOBS = [
    ("load_hourly_facts", timedelta(minutes=30)),
    ("rollup_daily_stats", timedelta(minutes=60)),
    ("cleanup_expired_pastes", timedelta(minutes=60)),
    ("prune_old_events", timedelta(days=1)),
]


def ensure_fresh_jobs():
    """Run any overdue job. Returns the names of the jobs that were run."""
    ran = []
    for name, max_age in JOBS:
        last = PipelineRun.objects.filter(name=name, status="success").first()
        if last and timezone.now() - last.started_at < max_age:
            continue
        if not cache.add(f"lazy-job-lock:{name}", 1, 60):  # someone else is running it
            continue
        try:
            getattr(tasks, name)()
            ran.append(name)
        except Exception:
            logger.exception("Lazy run of %s failed", name)
        finally:
            cache.delete(f"lazy-job-lock:{name}")
    return ran
