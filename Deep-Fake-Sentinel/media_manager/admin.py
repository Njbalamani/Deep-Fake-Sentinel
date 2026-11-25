from django.contrib import admin

from .models import AnalysisEvent, MediaFile


@admin.register(MediaFile)
class MediaFileAdmin(admin.ModelAdmin):
    list_display = ("original_name", "media_type", "status", "owner", "investigation", "sha256", "uploaded_at")
    list_filter = ("media_type", "status")
    search_fields = ("original_name", "sha256", "mime_type")
    date_hierarchy = "uploaded_at"
    readonly_fields = ("uploaded_at", "updated_at")


@admin.register(AnalysisEvent)
class AnalysisEventAdmin(admin.ModelAdmin):
    list_display = ("media", "stage", "status", "created_at")
    list_filter = ("stage", "status")
    search_fields = ("media__original_name", "stage", "message")
    date_hierarchy = "created_at"
