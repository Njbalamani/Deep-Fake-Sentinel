from django.contrib import admin

from .models import IntegrityRecord


@admin.register(IntegrityRecord)
class IntegrityRecordAdmin(admin.ModelAdmin):
    list_display = ("media", "status", "original_hash", "current_hash", "verified_at")
    list_filter = ("status",)
    search_fields = ("media__original_name", "original_hash", "current_hash")
    readonly_fields = ("verified_at",)
