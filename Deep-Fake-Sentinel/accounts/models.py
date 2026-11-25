from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    INVESTIGATOR = "INVESTIGATOR", "Investigator"
    ANALYST = "ANALYST", "Analyst"
    VIEWER = "VIEWER", "Viewer"


ROLE_ADMIN = Role.ADMIN
ROLE_INVESTIGATOR = Role.INVESTIGATOR
ROLE_ANALYST = Role.ANALYST
ROLE_VIEWER = Role.VIEWER
ROLE_CHOICES = Role.choices


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
    department = models.CharField(max_length=100, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    is_active_account = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    @property
    def is_investigator(self):
        return self.role == Role.INVESTIGATOR

    @property
    def is_analyst_or_above(self):
        return self.role in (Role.ANALYST, Role.INVESTIGATOR, Role.ADMIN)


class ActivityLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    action = models.CharField(max_length=150)
    model = models.CharField(max_length=100, blank=True, default="")
    object_id = models.CharField(max_length=64, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} by {self.user_id or 'anonymous'}"
