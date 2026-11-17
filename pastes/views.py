import logging
import secrets
from datetime import timedelta

from django.core.cache import cache
from django.db import models as db_models
from django.db.models import Count, Sum
from django.db.models.functions import ExtractHour
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from pygments.lexers import get_all_lexers

from .models import DailyStats, HourlyFact, Paste, PasteViewEvent, PipelineRun
from .quality import run_all_checks
from .scheduler import ensure_fresh_jobs
from .serializers import PasteCreateSerializer, PasteDetailSerializer, PasteListSerializer
from .utils import (
    generate_delete_token,
    get_unique_short_code,
    highlight_code,
    normalize_language,
    record_view,
)

logger = logging.getLogger(__name__)


class CreatePasteView(APIView):
    def post(self, request):
        serializer = PasteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        short_code = get_unique_short_code(Paste)
        language = normalize_language(data["language"])
        highlighted_html = highlight_code(data["content"], language)

        expires_at = None
        cache_ttl = 3600
        if data.get("expires_in"):
            expires_at = timezone.now() + timedelta(seconds=data["expires_in"])
            cache_ttl = data["expires_in"]

        paste = Paste.objects.create(
            short_code=short_code,
            title=data.get("title", ""),
            content=data["content"],
            language=language,
            highlighted_html=highlighted_html,
            expires_at=expires_at,
            delete_token=generate_delete_token(),
        )

        try:
            cache.set(f"paste:{short_code}", PasteDetailSerializer(paste).data, cache_ttl)
        except Exception:
            logger.warning("Failed to cache paste %s", short_code)

        return Response(
            {
                "short_code": paste.short_code,
                "title": paste.title,
                "language": paste.language,
                "url": request.build_absolute_uri(f"/p/{paste.short_code}/"),
                "expires_at": paste.expires_at,
                "created_at": paste.created_at,
                "delete_token": paste.delete_token,
            },
            status=status.HTTP_201_CREATED,
        )


class RetrievePasteView(APIView):
    def get(self, request, short_code):
        try:
            cached = cache.get(f"paste:{short_code}")
        except Exception:
            cached = None

        if cached:
            record_view(short_code, cached.get("language", "text"))
            return Response(cached)

        try:
            paste = Paste.objects.get(short_code=short_code, is_active=True)
        except Paste.DoesNotExist:
            return Response(
                {"detail": "Paste not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if paste.is_expired:
            return Response(
                {"detail": "Paste not found."}, status=status.HTTP_404_NOT_FOUND
            )

        record_view(paste)
        paste.refresh_from_db(fields=["view_count"])

        data = PasteDetailSerializer(paste).data

        try:
            ttl = 3600
            if paste.expires_at:
                remaining = (paste.expires_at - timezone.now()).total_seconds()
                ttl = max(int(remaining), 1)
            cache.set(f"paste:{short_code}", data, ttl)
        except Exception:
            logger.warning("Failed to cache paste %s", short_code)

        return Response(data)


class DeletePasteView(APIView):
    def delete(self, request, short_code):
        try:
            paste = Paste.objects.get(short_code=short_code, is_active=True)
        except Paste.DoesNotExist:
            return Response(
                {"detail": "Paste not found."}, status=status.HTTP_404_NOT_FOUND
            )

        token = request.headers.get("X-Delete-Token") or request.data.get("delete_token", "")
        if not paste.delete_token or not secrets.compare_digest(str(token), paste.delete_token):
            return Response(
                {"detail": "A valid delete token is required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        paste.is_active = False
        paste.save(update_fields=["is_active"])

        try:
            cache.delete(f"paste:{short_code}")
        except Exception:
            pass

        return Response(status=status.HTTP_204_NO_CONTENT)


class ListPastesView(APIView):
    def get(self, request):
        pastes = Paste.objects.filter(is_active=True).exclude(
            expires_at__lte=timezone.now()
        )
        from rest_framework.pagination import LimitOffsetPagination

        paginator = LimitOffsetPagination()
        page = paginator.paginate_queryset(pastes, request)
        serializer = PasteListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class LanguageListView(APIView):
    def get(self, request):
        languages = sorted(
            {alias for _, aliases, _, _ in get_all_lexers() for alias in aliases}
        )
        return Response(languages)


class StatsView(APIView):
    def get(self, request):
        total = Paste.objects.count()
        active = Paste.objects.filter(is_active=True).exclude(
            expires_at__lte=timezone.now()
        ).count()
        total_views = Paste.objects.aggregate(
            total=db_models.Sum("view_count")
        )["total"] or 0
        return Response({
            "total_pastes": total,
            "active_pastes": active,
            "total_views": total_views,
        })


class DailyAnalyticsView(APIView):
    """Daily totals from the rollup table plus a 3-day moving average.

    Also runs overdue maintenance jobs inline (see scheduler.py), so the data
    stays fresh on hosts that have no Celery worker.
    """

    def get(self, request):
        ensure_fresh_jobs()
        try:
            days = min(max(int(request.query_params.get("days", 7)), 1), 90)
        except ValueError:
            days = 7
        since = timezone.now().date() - timedelta(days=days - 1)
        # fetch 2 extra days so the moving average is correct on the first day
        rows = list(
            DailyStats.objects.filter(date__gte=since - timedelta(days=2))
            .values("date")
            .annotate(views=Sum("views"), pastes_created=Sum("pastes_created"))
            .order_by("date")
        )
        result = []
        for i, row in enumerate(rows):
            if row["date"] < since:
                continue
            window = [r["views"] for r in rows[max(i - 2, 0): i + 1]]
            result.append(
                {
                    "date": row["date"],
                    "views": row["views"],
                    "pastes_created": row["pastes_created"],
                    "views_3d_avg": round(sum(window) / len(window), 2),
                }
            )
        return Response(result)


class TopPastesView(APIView):
    """Most viewed pastes and language breakdown over the last N days (from raw events)."""

    def get(self, request):
        try:
            days = min(max(int(request.query_params.get("days", 7)), 1), 90)
        except ValueError:
            days = 7
        since = timezone.now() - timedelta(days=days)
        events = PasteViewEvent.objects.filter(viewed_at__gte=since)
        top = list(
            events.values("short_code", "language")
            .annotate(views=Count("id"))
            .order_by("-views")[:10]
        )
        by_language = list(
            events.values("language").annotate(views=Count("id")).order_by("-views")
        )
        return Response({"days": days, "top_pastes": top, "by_language": by_language})


class PipelineHealthView(APIView):
    """Recent job runs plus current data quality check results."""

    def get(self, request):
        runs = [
            {
                "name": r.name,
                "status": r.status,
                "started_at": r.started_at,
                "duration_seconds": r.duration_seconds,
                "rows_processed": r.rows_processed,
                "error": r.error,
            }
            for r in PipelineRun.objects.all()[:20]
        ]
        checks = run_all_checks()
        return Response(
            {"healthy": all(c["passed"] for c in checks), "checks": checks, "recent_runs": runs}
        )


class HourlyPatternView(APIView):
    """Views by hour of day (UTC) from the incrementally loaded fact table."""

    def get(self, request):
        ensure_fresh_jobs()
        rows = (
            HourlyFact.objects.annotate(h=ExtractHour("hour"))
            .values("h")
            .annotate(views=Sum("views"))
            .order_by("h")
        )
        by_hour = {r["h"]: r["views"] for r in rows}
        return Response([{"hour": h, "views": by_hour.get(h, 0)} for h in range(24)])
