from django.contrib import admin

from .models import ForensicRecord


@admin.register(ForensicRecord)
class ForensicRecordAdmin(admin.ModelAdmin):
    list_display = ("media", "risk_level", "created_at")
    list_filter = ("risk_level",)
    search_fields = ("media__original_name",)
    readonly_fields = ("created_at",)
