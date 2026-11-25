from django.db import models


class ForensicRecord(models.Model):
    RISK_CHOICES = (
        ("INFO", "INFO"),
        ("LOW", "LOW"),
        ("MEDIUM", "MEDIUM"),
        ("HIGH", "HIGH"),
    )

    media = models.OneToOneField("media_manager.MediaFile", on_delete=models.CASCADE, related_name="forensic_record")
    summary = models.TextField(blank=True)
    anomalies = models.JSONField(default=list)
    evidence = models.JSONField(default=list)
    risk_level = models.CharField(max_length=10, choices=RISK_CHOICES, default="INFO")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "Forensics for media %s" % self.media_id
