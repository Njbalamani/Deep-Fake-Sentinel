from django.contrib import admin

from .models import EvidenceAccessLog, Investigation, Observation, TimelineEvent


@admin.register(Investigation)
class InvestigationAdmin(admin.ModelAdmin):
    list_display = ("case_id", "title", "status", "priority", "created_by", "assigned_to", "created_at")
    list_filter = ("status", "priority")
    search_fields = ("case_id", "title", "description")
    filter_horizontal = ("media",)
    readonly_fields = ("case_id", "created_at", "updated_at")
    raw_id_fields = ("created_by", "assigned_to")


@admin.register(Observation)
class ObservationAdmin(admin.ModelAdmin):
    list_display = ("investigation", "author", "created_at")
    search_fields = ("note", "investigation__case_id")
    raw_id_fields = ("investigation", "author")


@admin.register(TimelineEvent)
class TimelineEventAdmin(admin.ModelAdmin):
    list_display = ("investigation", "event", "actor", "created_at")
    search_fields = ("event", "investigation__case_id")
    raw_id_fields = ("investigation", "actor")


@admin.register(EvidenceAccessLog)
class EvidenceAccessLogAdmin(admin.ModelAdmin):
    list_display = ("media", "user", "action", "ip_address", "created_at")
    list_filter = ("action",)
    search_fields = ("media__original_name", "user__username", "ip_address")
    raw_id_fields = ("media", "user")
