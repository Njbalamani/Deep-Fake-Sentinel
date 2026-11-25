from django.urls import reverse
from rest_framework import serializers

from .models import AnalysisEvent, MediaFile


class AnalysisEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisEvent
        fields = ["id", "stage", "status", "message", "created_at"]
        read_only_fields = fields


class MediaFileSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    investigation_title = serializers.CharField(source="investigation.title", read_only=True, allow_null=True)
    events = AnalysisEventSerializer(many=True, read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaFile
        fields = [
            "id",
            "owner",
            "owner_username",
            "investigation",
            "investigation_title",
            "download_url",
            "original_name",
            "media_type",
            "mime_type",
            "size_bytes",
            "sha256",
            "status",
            "uploaded_at",
            "updated_at",
            "error_message",
            "events",
        ]
        read_only_fields = [
            "id",
            "owner",
            "original_name",
            "media_type",
            "mime_type",
            "size_bytes",
            "sha256",
            "status",
            "uploaded_at",
            "updated_at",
            "error_message",
        ]

    def get_download_url(self, obj):
        url = reverse("media_api:media-download", kwargs={"pk": obj.pk})
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request is not None else url


class MediaStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaFile
        fields = ["id", "status", "sha256", "error_message", "updated_at"]
        read_only_fields = fields
