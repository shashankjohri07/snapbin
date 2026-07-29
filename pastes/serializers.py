from rest_framework import serializers

from .models import Paste


class PasteCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False, default="")
    content = serializers.CharField()
    language = serializers.CharField(max_length=50, required=False, default="text")
    expires_in = serializers.IntegerField(
        required=False, default=None, allow_null=True, min_value=60
    )


class PasteDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paste
        fields = [
            "short_code",
            "title",
            "content",
            "highlighted_html",
            "language",
            "view_count",
            "created_at",
            "expires_at",
        ]


class PasteListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paste
        fields = [
            "short_code",
            "title",
            "language",
            "created_at",
            "expires_at",
            "view_count",
        ]
