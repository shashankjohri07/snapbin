import logging

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
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
