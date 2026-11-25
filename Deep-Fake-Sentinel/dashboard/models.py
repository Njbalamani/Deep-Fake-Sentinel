from django.db import models


class ModelMetric(models.Model):
    model_name = models.CharField(max_length=120)
    version = models.CharField(max_length=80)
    accuracy = models.FloatField(null=True, blank=True)
    precision = models.FloatField(null=True, blank=True)
    recall = models.FloatField(null=True, blank=True)
    f1 = models.FloatField(null=True, blank=True)
    sample_count = models.PositiveIntegerField(default=0)
    trained_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=120, default="training")
    is_trained = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("model_name", "version")

    def __str__(self):
        return "%s %s" % (self.model_name, self.version)
