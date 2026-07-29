from django.contrib import admin
from django.shortcuts import render
from django.urls import include, path
from django.utils import timezone
from django.views.generic import TemplateView

from pastes.models import Paste


def paste_page_view(request, short_code):
    try:
        paste = Paste.objects.get(short_code=short_code, is_active=True)
    except Paste.DoesNotExist:
        return render(request, "paste_view.html", {"paste": None})

    if paste.is_expired:
        return render(request, "paste_view.html", {"paste": None})

    paste.view_count += 1
    paste.save(update_fields=["view_count"])

    return render(request, "paste_view.html", {"paste": paste})


urlpatterns = [
    path("", TemplateView.as_view(template_name="index.html"), name="root"),
    path("p/<str:short_code>/", paste_page_view, name="paste-page"),
    path("admin/", admin.site.urls),
    path("api/", include("pastes.urls")),
]
