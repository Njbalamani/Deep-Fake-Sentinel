import os
import re

from django.conf import settings
from rest_framework import serializers

from .models import MetadataRecord

REDACTED = "redacted"


def _is_absolute_path(value):
    return os.path.isabs(value) or (len(value) > 1 and value[1] == ":" and value[0].isalpha())


def _redact_paths(value):
    if isinstance(value, dict):
        return {key: _redact_paths(item) for key, item in value.items() if key != "analysis_root"}
    if isinstance(value, (list, tuple)):
        return [_redact_paths(item) for item in value]
    if isinstance(value, str):
        text = value
        media_root = str(getattr(settings, "MEDIA_ROOT", "") or "")
        if media_root:
            text = text.replace(media_root, REDACTED)
        text = re.sub(r"[A-Za-z]:\\[^\s'\"<>|]+", REDACTED, text)
        text = re.sub(r"[A-Za-z]:/[^\s'\"<>|]+", REDACTED, text)
        text = re.sub(r"\\\\[^\s'\"<>|]+", REDACTED, text)
        if _is_absolute_path(text):
            return REDACTED
        return text
    return value


class MetadataRecordSerializer(serializers.ModelSerializer):
    media_name = serializers.SerializerMethodField()

    class Meta:
        model = MetadataRecord
        fields = ("id", "media", "media_id", "media_name", "raw", "exif", "technical", "anomalies", "created_at")
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for field in ("raw", "exif", "technical", "anomalies"):
            if field in data:
                data[field] = _redact_paths(data[field])
        return data

    def get_media_name(self, obj):
        return str(getattr(obj.media, "original_name", "") or "")
