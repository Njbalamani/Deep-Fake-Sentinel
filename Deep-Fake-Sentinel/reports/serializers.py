from django.urls import NoReverseMatch, reverse
from rest_framework import serializers

from .models import ForensicReport


class ForensicReportSerializer(serializers.ModelSerializer):
    media_name = serializers.SerializerMethodField()
    investigation_id = serializers.SerializerMethodField()
    generated_by_username = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ForensicReport
        fields = (
            "id",
            "report_id",
            "media",
            "media_id",
            "media_name",
            "investigation",
            "investigation_id",
            "generated_by",
            "generated_by_username",
            "download_url",
            "version",
            "sha256",
            "hash_chain",
            "created_at",
        )
        read_only_fields = fields

    def get_media_name(self, obj):
        return str(getattr(obj.media, "original_name", "") or "")

    def get_investigation_id(self, obj):
        return str(obj.investigation_id) if obj.investigation_id else None

    def get_generated_by_username(self, obj):
        if obj.generated_by_id is None:
            return None
        return str(getattr(obj.generated_by, "username", "") or "")

    def get_download_url(self, obj):
        for name in ("dashboard:reports:report-download", "reports:report-download"):
            try:
                url = reverse(name, kwargs={"pk": obj.pk})
            except NoReverseMatch:
                continue
            request = self.context.get("request")
            return request.build_absolute_uri(url) if request is not None else url
        return None


class ReportCreateSerializer(serializers.Serializer):
    media = serializers.UUIDField()
