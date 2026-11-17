import uuid

from django.db import models
from django.utils import timezone


class Paste(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    short_code = models.CharField(max_length=8, unique=True, db_index=True)
    title = models.CharField(max_length=200, blank=True, default="")
    content = models.TextField()
    language = models.CharField(max_length=50, default="text")
    highlighted_html = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    view_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    delete_token = models.CharField(max_length=64, blank=True, default="", editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.short_code} - {self.title or 'Untitled'}"

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        return timezone.now() >= self.expires_at


class PasteViewEvent(models.Model):
    """Append-only event log: one row per paste view (raw layer)."""

    short_code = models.CharField(max_length=8, db_index=True)
    language = models.CharField(max_length=50, default="text")
    viewed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-viewed_at"]
        indexes = [models.Index(fields=["viewed_at", "language"], name="evt_time_lang_idx")]

    def __str__(self):
        return f"{self.short_code} @ {self.viewed_at:%Y-%m-%d %H:%M}"


class DailyStats(models.Model):
    """Daily rollup per language (aggregated layer), rebuilt idempotently from events."""

    date = models.DateField(db_index=True)
    language = models.CharField(max_length=50)
    views = models.PositiveIntegerField(default=0)
    unique_pastes_viewed = models.PositiveIntegerField(default=0)
    pastes_created = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date", "language"]
        constraints = [
            models.UniqueConstraint(fields=["date", "language"], name="uniq_daily_stats_date_language")
        ]

    def __str__(self):
        return f"{self.date} {self.language}: {self.views} views"


class PipelineRun(models.Model):
    """Run log for every batch job (observability: status, duration, rows)."""

    STATUS_CHOICES = [("success", "success"), ("failed", "failed")]

    name = models.CharField(max_length=100, db_index=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="success")
    rows_processed = models.IntegerField(default=0)
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]

    @property
    def duration_seconds(self):
        if not self.finished_at:
            return None
        return round((self.finished_at - self.started_at).total_seconds(), 3)


class PipelineWatermark(models.Model):
    """Incremental-load bookmark: highest event id already loaded by a job."""

    name = models.CharField(max_length=100, unique=True)
    last_event_id = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class HourlyFact(models.Model):
    """Fact table, grain = (hour, language). Loaded incrementally from raw events.

    Only additive measures are stored: distinct counts cannot be summed across
    batches, so unique-paste metrics live in the daily rollup instead.
    """

    hour = models.DateTimeField(db_index=True)
    language = models.CharField(max_length=50)
    views = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-hour", "language"]
        constraints = [
            models.UniqueConstraint(fields=["hour", "language"], name="uniq_hourly_fact_hour_language")
        ]
