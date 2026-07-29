import uuid

from django.db import models
from django.utils import timezone


class Paste(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    short_code = models.CharField(max_length=8, unique=True, db_index=True)
    title = models.CharField(max_length=200, blank=True, default="")
    content = models.TextField()
    language = models.CharField(max_length=50, default="text")
    highlighted_html = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    view_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.short_code} - {self.title or 'Untitled'}"

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        return timezone.now() >= self.expires_at
