from django.db import models


class IntegrityRecord(models.Model):
    STATUS_CHOICES = (
        ("VERIFIED", "VERIFIED"),
        ("TAMPERED", "TAMPERED"),
        ("UNAVAILABLE", "UNAVAILABLE"),
    )

    media = models.OneToOneField("media_manager.MediaFile", on_delete=models.CASCADE, related_name="integrity_record")
    original_hash = models.CharField(max_length=64, blank=True)
    current_hash = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="UNAVAILABLE")
    verified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Integrity for media %s" % self.media_id
