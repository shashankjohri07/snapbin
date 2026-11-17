from django.urls import path

from . import views

urlpatterns = [
    path("pastes/", views.CreatePasteView.as_view(), name="paste-create"),
    path("pastes/list/", views.ListPastesView.as_view(), name="paste-list"),
    path("pastes/<str:short_code>/", views.RetrievePasteView.as_view(), name="paste-detail"),
    path("pastes/<str:short_code>/delete/", views.DeletePasteView.as_view(), name="paste-delete"),
    path("languages/", views.LanguageListView.as_view(), name="language-list"),
    path("stats/", views.StatsView.as_view(), name="stats"),
    path("analytics/daily/", views.DailyAnalyticsView.as_view(), name="analytics-daily"),
    path("pipeline/health/", views.PipelineHealthView.as_view(), name="pipeline-health"),
    path("analytics/hourly/", views.HourlyPatternView.as_view(), name="analytics-hourly"),
    path("analytics/top/", views.TopPastesView.as_view(), name="analytics-top"),
]
