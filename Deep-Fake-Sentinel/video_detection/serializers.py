from rest_framework import serializers

from .models import VideoAnalysis


class VideoAnalysisSerializer(serializers.ModelSerializer):
    media_name = serializers.SerializerMethodField()

    class Meta:
        model = VideoAnalysis
        fields = (
            "id",
            "media",
            "media_id",
            "media_name",
            "model_version",
            "model_status",
            "verdict",
            "confidence",
            "frame_count",
            "sampled_frames",
            "suspicious_frames",
            "temporal_consistency",
            "indicators",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_media_name(self, obj):
        return str(getattr(obj.media, "original_name", "") or "")
