import uuid

from django.conf import settings
from django.db import models


class ForensicReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_id = models.CharField(max_length=64, unique=True)
    media = models.ForeignKey("media_manager.MediaFile", on_delete=models.CASCADE, related_name="reports")
    investigation = models.ForeignKey(
        "investigations.Investigation", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports"
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="generated_reports"
    )
    pdf = models.FileField(upload_to="reports/", max_length=512)
    version = models.CharField(max_length=20, default="1")
    sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    hash_chain = models.CharField(max_length=64, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.report_id
