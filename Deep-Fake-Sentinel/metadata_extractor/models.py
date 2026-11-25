from django.db import models


class MetadataRecord(models.Model):
    media = models.OneToOneField("media_manager.MediaFile", on_delete=models.CASCADE, related_name="metadata_record")
    raw = models.JSONField(default=dict)
    exif = models.JSONField(default=dict)
    technical = models.JSONField(default=dict)
    anomalies = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "Metadata for media %s" % self.media_id
