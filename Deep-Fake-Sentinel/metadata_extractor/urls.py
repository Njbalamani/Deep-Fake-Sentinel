from django.urls import path

from .views import MetadataDetailView

app_name = "metadata_extractor"

urlpatterns = [
    path("metadata/<uuid:media_id>/", MetadataDetailView.as_view(), name="metadata-detail"),
]
