from django.contrib import admin

from .models import MetadataRecord


@admin.register(MetadataRecord)
class MetadataRecordAdmin(admin.ModelAdmin):
    list_display = ("media", "created_at")
    search_fields = ("media__original_name",)
    readonly_fields = ("created_at",)
