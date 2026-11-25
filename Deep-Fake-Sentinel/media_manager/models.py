import uuid

from django.conf import settings
from django.db import models

from .services import build_upload_path


class MediaType(models.TextChoices):
    IMAGE = "IMAGE", "Image"
    VIDEO = "VIDEO", "Video"
    AUDIO = "AUDIO", "Audio"


class MediaStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


TYPE_IMAGE = MediaType.IMAGE
TYPE_VIDEO = MediaType.VIDEO
TYPE_AUDIO = MediaType.AUDIO
STATUS_PENDING = MediaStatus.PENDING
STATUS_PROCESSING = MediaStatus.PROCESSING
STATUS_COMPLETED = MediaStatus.COMPLETED
STATUS_FAILED = MediaStatus.FAILED


class MediaFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="media_files",
    )
    investigation = models.ForeignKey(
        "investigations.Investigation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_files",
    )
    file = models.FileField(upload_to=build_upload_path, max_length=512)
    original_name = models.CharField(max_length=255)
    media_type = models.CharField(max_length=10, choices=MediaType.choices, default=MediaType.IMAGE)
    mime_type = models.CharField(max_length=100, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, db_index=True, blank=True, default="")
    status = models.CharField(max_length=20, choices=MediaStatus.choices, default=MediaStatus.PENDING)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.original_name or str(self.id)

    @property
    def filename(self):
        return self.file.name.rsplit("/", 1)[-1]

    @property
    def is_image(self):
        return self.media_type == MediaType.IMAGE

    @property
    def is_video(self):
        return self.media_type == MediaType.VIDEO

    @property
    def is_audio(self):
        return self.media_type == MediaType.AUDIO


class AnalysisEvent(models.Model):
    media = models.ForeignKey(MediaFile, on_delete=models.CASCADE, related_name="events")
    stage = models.CharField(max_length=100)
    status = models.CharField(max_length=50, default="INFO")
    message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.stage}: {self.status}"
