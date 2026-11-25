import uuid

from django.conf import settings
from django.db import models


class InvestigationStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    CLOSED = "CLOSED", "Closed"
    ARCHIVED = "ARCHIVED", "Archived"


class InvestigationPriority(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"
    CRITICAL = "CRITICAL", "Critical"


STATUS_OPEN = InvestigationStatus.OPEN
STATUS_IN_PROGRESS = InvestigationStatus.IN_PROGRESS
STATUS_CLOSED = InvestigationStatus.CLOSED
STATUS_ARCHIVED = InvestigationStatus.ARCHIVED
PRIORITY_LOW = InvestigationPriority.LOW
PRIORITY_MEDIUM = InvestigationPriority.MEDIUM
PRIORITY_HIGH = InvestigationPriority.HIGH
PRIORITY_CRITICAL = InvestigationPriority.CRITICAL


def generate_case_id():
    while True:
        candidate = uuid.uuid4().hex[:8].upper()
        if not Investigation.objects.filter(case_id=candidate).exists():
            return candidate


class Investigation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_id = models.CharField(max_length=16, unique=True, default=generate_case_id, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=InvestigationStatus.choices, default=InvestigationStatus.OPEN)
    priority = models.CharField(
        max_length=20, choices=InvestigationPriority.choices, default=InvestigationPriority.MEDIUM
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="investigations_created",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="investigations_assigned",
    )
    media = models.ManyToManyField("media_manager.MediaFile", blank=True, related_name="investigations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.case_id} - {self.title}"


class Observation(models.Model):
    investigation = models.ForeignKey(Investigation, on_delete=models.CASCADE, related_name="observations")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="observations")
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Observation by {self.author} on {self.investigation.case_id}"


class TimelineEvent(models.Model):
    investigation = models.ForeignKey(Investigation, on_delete=models.CASCADE, related_name="timeline_events")
    event = models.TextField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timeline_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.investigation.case_id}: {self.event[:60]}"


class EvidenceAccessLog(models.Model):
    media = models.ForeignKey("media_manager.MediaFile", on_delete=models.CASCADE, related_name="access_logs")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_access_logs",
    )
    action = models.CharField(max_length=50, default="VIEW")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} on {self.media_id} by {self.user_id or 'anonymous'}"
