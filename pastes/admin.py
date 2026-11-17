from django.contrib import admin

from .models import DailyStats, HourlyFact, Paste, PipelineRun, PipelineWatermark


@admin.register(Paste)
class PasteAdmin(admin.ModelAdmin):
    list_display = ["short_code", "title", "language", "is_active", "created_at", "expires_at"]
    list_filter = ["is_active", "language"]
    search_fields = ["short_code", "title", "content"]
    readonly_fields = ["id", "short_code", "created_at", "view_count"]


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "started_at", "duration_seconds", "rows_processed"]
    list_filter = ["name", "status"]


@admin.register(DailyStats)
class DailyStatsAdmin(admin.ModelAdmin):
    list_display = ["date", "language", "views", "unique_pastes_viewed", "pastes_created"]
    list_filter = ["language"]


@admin.register(HourlyFact)
class HourlyFactAdmin(admin.ModelAdmin):
    list_display = ["hour", "language", "views"]
    list_filter = ["language"]


@admin.register(PipelineWatermark)
class PipelineWatermarkAdmin(admin.ModelAdmin):
    list_display = ["name", "last_event_id", "updated_at"]
