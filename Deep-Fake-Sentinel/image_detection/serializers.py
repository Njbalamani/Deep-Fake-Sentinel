from rest_framework import serializers

from .models import ImageAnalysis


class ImageAnalysisSerializer(serializers.ModelSerializer):
    media_name = serializers.SerializerMethodField()

    class Meta:
        model = ImageAnalysis
        fields = (
            "id",
            "media",
            "media_id",
            "media_name",
            "model_version",
            "model_status",
            "verdict",
            "confidence",
            "indicators",
            "face_count",
            "artifact_score",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_media_name(self, obj):
        return str(getattr(obj.media, "original_name", "") or "")
