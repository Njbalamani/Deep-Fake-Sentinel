from django.contrib import admin

from .models import ModelMetric


@admin.register(ModelMetric)
class ModelMetricAdmin(admin.ModelAdmin):
    list_display = ("model_name", "version", "accuracy", "f1", "sample_count", "is_trained", "trained_at", "source")
    list_filter = ("is_trained", "source")
    search_fields = ("model_name", "version")
    readonly_fields = ("created_at",)
