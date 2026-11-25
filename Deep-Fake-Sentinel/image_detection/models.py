from django.db import models


class ImageAnalysis(models.Model):
    MODEL_STATUS_CHOICES = (
        ("UNTRAINED", "UNTRAINED"),
        ("TRAINED", "TRAINED"),
        ("UNAVAILABLE", "UNAVAILABLE"),
    )
    VERDICT_CHOICES = (
        ("INCONCLUSIVE", "INCONCLUSIVE"),
        ("LIKELY_MANIPULATED", "LIKELY_MANIPULATED"),
        ("LIKELY_AUTHENTIC", "LIKELY_AUTHENTIC"),
    )

    media = models.OneToOneField("media_manager.MediaFile", on_delete=models.CASCADE, related_name="image_analysis")
    model_version = models.CharField(max_length=100, default="untrained")
    model_status = models.CharField(max_length=20, choices=MODEL_STATUS_CHOICES, default="UNTRAINED")
    verdict = models.CharField(max_length=30, choices=VERDICT_CHOICES, default="INCONCLUSIVE")
    confidence = models.FloatField(null=True, blank=True)
    checkpoint_name = models.CharField(max_length=255, blank=True)
    checkpoint_path = models.CharField(max_length=1024, blank=True)
    checkpoint_id = models.CharField(max_length=64, blank=True)
    checkpoint_sha256 = models.CharField(max_length=64, blank=True)
    preprocessing_config = models.JSONField(default=dict)
    indicators = models.JSONField(default=list)
    face_count = models.IntegerField(default=0)
    artifact_score = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Image analysis for media %s" % self.media_id
