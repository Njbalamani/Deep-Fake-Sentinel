from django.urls import path

from .views import VideoAnalysisDetailView

app_name = "video_detection"

urlpatterns = [
    path("analyses/video/<uuid:media_id>/", VideoAnalysisDetailView.as_view(), name="video-analysis-detail"),
]
