from django.contrib import admin

from .models import AudioAnalysis


@admin.register(AudioAnalysis)
class AudioAnalysisAdmin(admin.ModelAdmin):
    list_display = ("media", "model_status", "verdict", "confidence", "duration_seconds", "sample_rate", "updated_at")
    list_filter = ("model_status", "verdict")
    search_fields = ("media__original_name", "model_version")
    readonly_fields = ("created_at", "updated_at")
