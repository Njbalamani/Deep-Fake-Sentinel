from django.contrib import admin

from .models import ImageAnalysis


@admin.register(ImageAnalysis)
class ImageAnalysisAdmin(admin.ModelAdmin):
    list_display = ("media", "model_status", "verdict", "confidence", "face_count", "artifact_score", "updated_at")
    list_filter = ("model_status", "verdict")
    search_fields = ("media__original_name", "model_version")
    readonly_fields = ("created_at", "updated_at")
