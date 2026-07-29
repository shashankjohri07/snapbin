from django.urls import path

from . import views

urlpatterns = [
    path("pastes/", views.CreatePasteView.as_view(), name="paste-create"),
    path("pastes/list/", views.ListPastesView.as_view(), name="paste-list"),
    path("pastes/<str:short_code>/", views.RetrievePasteView.as_view(), name="paste-detail"),
    path("pastes/<str:short_code>/delete/", views.DeletePasteView.as_view(), name="paste-delete"),
    path("languages/", views.LanguageListView.as_view(), name="language-list"),
]
