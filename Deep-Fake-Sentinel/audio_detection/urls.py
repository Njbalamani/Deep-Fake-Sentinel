from django.urls import path

from .views import AudioAnalysisDetailView

app_name = "audio_detection"

urlpatterns = [
    path("analyses/audio/<uuid:media_id>/", AudioAnalysisDetailView.as_view(), name="audio-analysis-detail"),
]
