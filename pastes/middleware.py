import logging

from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.max_requests = getattr(settings, "RATE_LIMIT_MAX_REQUESTS", 30)
        self.window = getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)

    def __call__(self, request):
        ip = self._get_client_ip(request)
        try:
            import redis as _redis
            from django.conf import settings as s

            redis_url = getattr(s, "REDIS_URL", "redis://localhost:6379/0")
            r = _redis.from_url(redis_url)
            key = f"ratelimit:{ip}"
            count = r.incr(key)
            if count == 1:
                r.expire(key, self.window)
            if count > self.max_requests:
                return JsonResponse(
                    {"detail": "Rate limit exceeded. Try again later."},
                    status=429,
                )
        except Exception:
            # fail open
            pass

        return self.get_response(request)

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")
