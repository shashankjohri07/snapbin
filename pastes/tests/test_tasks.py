import pytest
from datetime import timedelta

from django.utils import timezone

from pastes.models import Paste
from pastes.tasks import cleanup_expired_pastes


@pytest.mark.django_db
class TestCleanupTask:
    def test_cleanup_deletes_expired(self):
        Paste.objects.create(
            short_code="cexp1234",
            content="expired",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        count = cleanup_expired_pastes()
        assert count == 1
        assert Paste.objects.get(short_code="cexp1234").is_active is False

    def test_cleanup_keeps_active(self):
        Paste.objects.create(
            short_code="cact1234",
            content="active",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        cleanup_expired_pastes()
        assert Paste.objects.get(short_code="cact1234").is_active is True

    def test_cleanup_handles_no_expiry(self):
        Paste.objects.create(
            short_code="cnoe1234",
            content="permanent",
            expires_at=None,
        )
        cleanup_expired_pastes()
        assert Paste.objects.get(short_code="cnoe1234").is_active is True
