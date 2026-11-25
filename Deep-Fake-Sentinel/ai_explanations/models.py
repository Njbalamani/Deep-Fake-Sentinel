from django.db import models


class Explanation(models.Model):
    media = models.OneToOneField("media_manager.MediaFile", on_delete=models.CASCADE, related_name="explanation")
    summary = models.TextField(blank=True)
    indicators = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)
    limitations = models.JSONField(default=list)
    evidence_source = models.CharField(max_length=50, default="deterministic")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "Explanation for media %s" % self.media_id
