import logging

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """IP-based fixed-window rate limiter for API calls.

    Uses Redis INCR when REDIS_URL is configured, otherwise falls back to the
    Django cache so the limiter still works without Redis (e.g. free hosting).
    Fails open if the backing store is unavailable.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.max_requests = getattr(settings, "RATE_LIMIT_MAX_REQUESTS", 30)
        self.window = getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)

    def __call__(self, request):
        if request.path.startswith("/api/"):
            try:
                if self._count(self._get_client_ip(request)) > self.max_requests:
                    return JsonResponse(
                        {"detail": "Rate limit exceeded. Try again later."},
                        status=429,
                    )
            except Exception:
                logger.warning("Rate limiter unavailable, failing open")
        return self.get_response(request)

    def _count(self, ip):
        key = f"ratelimit:{ip}"
        redis_url = getattr(settings, "REDIS_URL", "")
        if redis_url:
            import redis as _redis

            r = _redis.from_url(redis_url)
            count = r.incr(key)
            if count == 1:
                r.expire(key, self.window)
            return count
        cache.add(key, 0, self.window)
        return cache.incr(key)

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")
