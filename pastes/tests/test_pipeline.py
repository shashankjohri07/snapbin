from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from pastes.models import DailyStats, Paste, PasteViewEvent, PipelineRun
from pastes.quality import check_freshness, check_orphan_events, check_reconciliation
from pastes.tasks import rollup_daily_stats


@pytest.fixture
def paste():
    return Paste.objects.create(short_code="pipe0001", content="x", language="python")


@pytest.mark.django_db
class TestPipelineRuns:
    def test_successful_run_is_logged(self, paste):
        PasteViewEvent.objects.create(short_code="pipe0001", language="python")
        rollup_daily_stats(days=1)
        run = PipelineRun.objects.get(name="rollup_daily_stats")
        assert run.status == "success" and run.rows_processed == 1
        assert run.duration_seconds is not None

    def test_failed_run_is_logged_and_reraised(self):
        with patch("pastes.tasks._rollup_day", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                rollup_daily_stats(days=1)
        run = PipelineRun.objects.get(name="rollup_daily_stats")
        assert run.status == "failed" and "boom" in run.error


@pytest.mark.django_db
class TestQualityChecks:
    def test_reconciliation_passes_after_rollup(self, paste):
        PasteViewEvent.objects.create(short_code="pipe0001", language="python")
        rollup_daily_stats(days=3)
        assert check_reconciliation()["passed"]

    def test_reconciliation_detects_stale_rollup(self, paste):
        PasteViewEvent.objects.create(short_code="pipe0001", language="python")
        DailyStats.objects.create(date=timezone.now().date(), language="python", views=99)
        assert not check_reconciliation()["passed"]

    def test_orphan_events_detected(self):
        PasteViewEvent.objects.create(short_code="ghost001", language="text")
        result = check_orphan_events()
        assert not result["passed"] and "ghost001" in result["detail"]

    def test_freshness(self, paste):
        assert not check_freshness()["passed"]  # never ran
        rollup_daily_stats(days=1)
        assert check_freshness()["passed"]
        PipelineRun.objects.update(started_at=timezone.now() - timedelta(hours=5))
        assert not check_freshness()["passed"]

    def test_health_endpoint_and_command(self, api_client, paste):
        rollup_daily_stats(days=3)
        data = api_client.get("/api/pipeline/health/").data
        assert data["healthy"] is True and data["recent_runs"]
        call_command("check_data_quality")
        call_command("run_maintenance")
