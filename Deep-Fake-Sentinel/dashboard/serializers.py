from rest_framework import serializers

from .models import ModelMetric


class ModelMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelMetric
        fields = (
            "id",
            "model_name",
            "version",
            "accuracy",
            "precision",
            "recall",
            "f1",
            "sample_count",
            "trained_at",
            "source",
            "is_trained",
            "created_at",
        )
        read_only_fields = fields
