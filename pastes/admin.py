from django.contrib import admin

from .models import Paste


@admin.register(Paste)
class PasteAdmin(admin.ModelAdmin):
    list_display = ["short_code", "title", "language", "is_active", "created_at", "expires_at"]
    list_filter = ["is_active", "language"]
    search_fields = ["short_code", "title", "content"]
    readonly_fields = ["id", "short_code", "created_at", "view_count"]
