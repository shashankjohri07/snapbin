import logging

from django.core.cache import cache
from django.db import models as db_models
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from pygments.lexers import get_all_lexers

from .models import Paste
from .serializers import PasteCreateSerializer, PasteDetailSerializer, PasteListSerializer
from .utils import get_unique_short_code, highlight_code

logger = logging.getLogger(__name__)


class CreatePasteView(APIView):
    def post(self, request):
        serializer = PasteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        short_code = get_unique_short_code(Paste)
        highlighted_html = highlight_code(data["content"], data["language"])

        expires_at = None
        cache_ttl = 3600
        if data.get("expires_in"):
            expires_at = timezone.now() + timezone.timedelta(seconds=data["expires_in"])
            cache_ttl = data["expires_in"]

        paste = Paste.objects.create(
            short_code=short_code,
            title=data.get("title", ""),
            content=data["content"],
            language=data["language"],
            highlighted_html=highlighted_html,
            expires_at=expires_at,
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
            Paste.objects.filter(short_code=short_code, is_active=True).update(
                view_count=db_models.F("view_count") + 1
            )
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

        paste.view_count += 1
        paste.save(update_fields=["view_count"])

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
