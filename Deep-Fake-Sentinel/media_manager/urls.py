from django.urls import path

from .api import (
    MediaDetailAPIView,
    MediaDownloadAPIView,
    MediaHistoryAPIView,
    MediaListAPIView,
    MediaReprocessAPIView,
    MediaStatusAPIView,
)

app_name = "media_api"

urlpatterns = [
    path("", MediaListAPIView.as_view(), name="media-list"),
    path("<uuid:pk>/", MediaDetailAPIView.as_view(), name="media-detail"),
    path("<uuid:pk>/download/", MediaDownloadAPIView.as_view(), name="media-download"),
    path("<uuid:pk>/status/", MediaStatusAPIView.as_view(), name="media-status"),
    path("<uuid:pk>/reprocess/", MediaReprocessAPIView.as_view(), name="media-reprocess"),
    path("<uuid:pk>/history/", MediaHistoryAPIView.as_view(), name="media-history"),
]
