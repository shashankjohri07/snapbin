from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone

from pastes.middleware import RateLimitMiddleware
from pastes.models import DailyStats, Paste, PasteViewEvent
from pastes.tasks import prune_old_events, rollup_daily_stats
from pastes.utils import normalize_language


@pytest.fixture
def paste():
    return Paste.objects.create(short_code="evt00001", content="x", language="python")


@pytest.mark.django_db
class TestViewEvents:
    def test_view_logs_event_and_counts(self, api_client, paste):
        cache.clear()
        api_client.get("/api/pastes/evt00001/")
        api_client.get("/api/pastes/evt00001/")  # second hit served from cache
        assert PasteViewEvent.objects.filter(short_code="evt00001").count() == 2
        paste.refresh_from_db()
        assert paste.view_count == 2

    def test_unknown_language_falls_back_to_text(self, api_client):
        r = api_client.post("/api/pastes/", {"content": "x", "language": "nope"}, format="json")
        assert r.data["language"] == "text"
        assert normalize_language("Python") == "python"


@pytest.mark.django_db
class TestRollup:
    def test_rollup_is_idempotent(self, paste):
        for _ in range(3):
            PasteViewEvent.objects.create(short_code="evt00001", language="python")
        rollup_daily_stats(days=1)
        rollup_daily_stats(days=1)
        row = DailyStats.objects.get(language="python")
        assert (row.views, row.unique_pastes_viewed, row.pastes_created) == (3, 1, 1)
        assert DailyStats.objects.count() == 1

    def test_prune_old_events(self):
        old = PasteViewEvent.objects.create(short_code="old00001", language="text")
        PasteViewEvent.objects.filter(pk=old.pk).update(viewed_at=timezone.now() - timedelta(days=40))
        PasteViewEvent.objects.create(short_code="new00001", language="text")
        assert prune_old_events(retention_days=30) == 1

    def test_analytics_endpoints(self, api_client, paste):
        PasteViewEvent.objects.create(short_code="evt00001", language="python")
        rollup_daily_stats(days=1)
        daily = api_client.get("/api/analytics/daily/?days=3")
        assert daily.status_code == 200 and daily.data[0]["views"] == 1
        top = api_client.get("/api/analytics/top/")
        assert top.data["top_pastes"][0]["short_code"] == "evt00001"


class TestRateLimitWithoutRedis:
    def test_cache_fallback_limits(self, settings):
        settings.REDIS_URL = ""
        cache.clear()
        mw = RateLimitMiddleware(lambda r: type("R", (), {"status_code": 200})())
        mw.max_requests = 2
        req = RequestFactory().get("/api/stats/")
        assert [mw(req).status_code for _ in range(3)] == [200, 200, 429]
