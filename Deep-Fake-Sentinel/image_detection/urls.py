from django.urls import path

from .views import ImageAnalysisDetailView

app_name = "image_detection"

urlpatterns = [
    path("analyses/image/<uuid:media_id>/", ImageAnalysisDetailView.as_view(), name="image-analysis-detail"),
]
