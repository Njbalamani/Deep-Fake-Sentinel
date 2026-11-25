from django.contrib import admin

from .models import VideoAnalysis


@admin.register(VideoAnalysis)
class VideoAnalysisAdmin(admin.ModelAdmin):
    list_display = ("media", "model_status", "verdict", "confidence", "frame_count", "sampled_frames", "updated_at")
    list_filter = ("model_status", "verdict")
    search_fields = ("media__original_name", "model_version")
    readonly_fields = ("created_at", "updated_at")
