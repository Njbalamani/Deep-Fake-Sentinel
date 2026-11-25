from django.contrib import admin

from .models import ActivityLog, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "department", "phone", "is_active_account", "created_at")
    list_filter = ("role", "is_active_account")
    search_fields = ("user__username", "user__email", "department", "phone")
    raw_id_fields = ("user",)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "user", "model", "object_id", "ip_address")
    list_filter = ("action", "model")
    search_fields = ("action", "model", "object_id", "user__username")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)
