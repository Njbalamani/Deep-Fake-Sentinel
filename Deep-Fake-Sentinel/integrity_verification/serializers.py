from rest_framework import serializers

from .models import IntegrityRecord


class IntegrityRecordSerializer(serializers.ModelSerializer):
    media_name = serializers.SerializerMethodField()

    class Meta:
        model = IntegrityRecord
        fields = ("id", "media", "media_id", "media_name", "original_hash", "current_hash", "status", "verified_at")
        read_only_fields = fields

    def get_media_name(self, obj):
        return str(getattr(obj.media, "original_name", "") or "")
