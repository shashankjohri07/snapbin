import pytest
from django.utils import timezone
from datetime import timedelta

from pastes.models import Paste
from pastes.utils import get_unique_short_code


@pytest.mark.django_db
class TestPasteModel:
    def test_paste_creation(self):
        paste = Paste.objects.create(
            short_code="abcd1234",
            title="Test Paste",
            content="print('hello')",
            language="python",
        )
        assert paste.short_code == "abcd1234"
        assert paste.title == "Test Paste"
        assert paste.content == "print('hello')"
        assert paste.is_active is True
        assert paste.view_count == 0
        assert paste.id is not None

    def test_short_code_uniqueness(self):
        codes = set()
        for i in range(100):
            code = get_unique_short_code(Paste)
            assert code not in codes
            codes.add(code)
            Paste.objects.create(short_code=code, content=f"content {i}")

    def test_soft_delete(self):
        paste = Paste.objects.create(short_code="del12345", content="delete me")
        paste.is_active = False
        paste.save()
        assert Paste.objects.filter(short_code="del12345").exists()
        assert Paste.objects.get(short_code="del12345").is_active is False

    def test_expired_paste(self):
        paste = Paste.objects.create(
            short_code="exp12345",
            content="expired",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        assert paste.is_expired is True

    def test_non_expired_paste(self):
        paste = Paste.objects.create(
            short_code="nexp1234",
            content="not expired",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert paste.is_expired is False
