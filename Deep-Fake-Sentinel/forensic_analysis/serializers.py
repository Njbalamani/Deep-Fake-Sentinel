from rest_framework import serializers

from .models import ForensicRecord


class ForensicRecordSerializer(serializers.ModelSerializer):
    media_name = serializers.SerializerMethodField()

    class Meta:
        model = ForensicRecord
        fields = (
            "id",
            "media",
            "media_id",
            "media_name",
            "summary",
            "anomalies",
            "evidence",
            "risk_level",
            "created_at",
        )
        read_only_fields = fields

    def get_media_name(self, obj):
        return str(getattr(obj.media, "original_name", "") or "")
