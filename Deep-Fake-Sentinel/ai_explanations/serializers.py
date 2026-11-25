from rest_framework import serializers

from .models import Explanation


class ExplanationSerializer(serializers.ModelSerializer):
    media_name = serializers.SerializerMethodField()

    class Meta:
        model = Explanation
        fields = (
            "id",
            "media",
            "media_id",
            "media_name",
            "summary",
            "indicators",
            "recommendations",
            "limitations",
            "evidence_source",
            "created_at",
        )
        read_only_fields = fields

    def get_media_name(self, obj):
        return str(getattr(obj.media, "original_name", "") or "")
