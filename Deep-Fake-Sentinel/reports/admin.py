from django.contrib import admin

from .models import ForensicReport


@admin.register(ForensicReport)
class ForensicReportAdmin(admin.ModelAdmin):
    list_display = ("report_id", "media", "investigation", "generated_by", "version", "created_at")
    list_filter = ("version",)
    search_fields = ("report_id", "media__original_name")
    readonly_fields = ("created_at",)
