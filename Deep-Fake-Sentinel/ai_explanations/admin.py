from django.contrib import admin

from .models import Explanation


@admin.register(Explanation)
class ExplanationAdmin(admin.ModelAdmin):
    list_display = ("media", "evidence_source", "created_at")
    list_filter = ("evidence_source",)
    search_fields = ("media__original_name",)
    readonly_fields = ("created_at",)
