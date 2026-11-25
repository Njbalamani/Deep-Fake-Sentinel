from rest_framework import serializers

from .models import AudioAnalysis


class AudioAnalysisSerializer(serializers.ModelSerializer):
    media_name = serializers.SerializerMethodField()

    class Meta:
        model = AudioAnalysis
        fields = (
            "id",
            "media",
            "media_id",
            "media_name",
            "model_version",
            "model_status",
            "verdict",
            "confidence",
            "duration_seconds",
            "sample_rate",
            "waveform_path",
            "spectrogram_path",
            "features",
            "suspicious_segments",
            "indicators",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_media_name(self, obj):
        return str(getattr(obj.media, "original_name", "") or "")
