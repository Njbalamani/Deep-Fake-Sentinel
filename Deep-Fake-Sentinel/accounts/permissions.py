from django.apps import apps
from django.db.models import Q
from rest_framework.permissions import BasePermission

ADMIN = "ADMIN"
INVESTIGATOR = "INVESTIGATOR"
ANALYST = "ANALYST"
VIEWER = "VIEWER"

ALL_ROLES = (ADMIN, INVESTIGATOR, ANALYST, VIEWER)


def get_user_role(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if getattr(user, "is_superuser", False):
        return ADMIN
    profile = getattr(user, "profile", None)
    if profile is None:
        try:
            from .models import UserProfile

            profile = UserProfile.objects.select_related("user").get(user=user)
        except Exception:
            profile = None
    if profile is None:
        return None
    if not getattr(profile, "is_active_account", True):
        return None
    return profile.role


def user_has_role(user, *roles):
    return get_user_role(user) in tuple(str(role).upper() for role in roles)


class RolePermission(BasePermission):
    allowed_roles = ()
    message = "You do not have the required role to perform this action."

    def has_permission(self, request, view):
        return get_user_role(getattr(request, "user", None)) in self.allowed_roles

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsAdmin(RolePermission):
    allowed_roles = (ADMIN,)


class IsInvestigator(RolePermission):
    allowed_roles = (INVESTIGATOR,)


class IsAnalystOrAbove(RolePermission):
    allowed_roles = (ANALYST, INVESTIGATOR, ADMIN)


class IsAdminOrInvestigator(RolePermission):
    allowed_roles = (ADMIN, INVESTIGATOR)


class HasRole(RolePermission):
    allowed_roles = ()

    def __new__(cls, *roles):
        if roles:
            normalized = tuple(str(role).upper() for role in roles)
            return type("HasSpecifiedRole", (cls,), {"allowed_roles": normalized})
        return super().__new__(cls)


def is_privileged(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(
        getattr(user, "is_staff", False) or getattr(user, "is_superuser", False) or get_user_role(user) == ADMIN
    )


def media_queryset_for_user(user):
    queryset = apps.get_model("media_manager", "MediaFile").objects.all()
    if is_privileged(user):
        return queryset
    return queryset.filter(Q(owner=user) | Q(investigation__created_by=user) | Q(investigation__assigned_to=user))


def investigation_queryset_for_user(user):
    queryset = apps.get_model("investigations", "Investigation").objects.all()
    if is_privileged(user):
        return queryset
    return queryset.filter(Q(created_by=user) | Q(assigned_to=user))


def report_queryset_for_user(user):
    queryset = apps.get_model("reports", "ForensicReport").objects.all()
    if is_privileged(user):
        return queryset
    return queryset.filter(
        Q(media__in=media_queryset_for_user(user).values("pk"))
        | Q(generated_by=user)
        | Q(investigation__created_by=user)
        | Q(investigation__assigned_to=user)
    )


def user_owns_object(user, obj):
    if is_privileged(user):
        return True
    if obj is None or not getattr(user, "is_authenticated", False):
        return False
    for field in ("owner", "created_by", "assigned_to", "generated_by", "user", "author", "actor"):
        value = getattr(obj, f"{field}_id", None)
        if value is None:
            value = getattr(getattr(obj, field, None), "pk", None)
        if value is not None and value == user.pk:
            return True
    media_id = getattr(obj, "media_id", None)
    if media_id is None:
        media_id = getattr(getattr(obj, "media", None), "pk", None)
    if media_id is not None and media_queryset_for_user(user).filter(pk=media_id).exists():
        return True
    investigation_id = getattr(obj, "investigation_id", None)
    if investigation_id is None:
        investigation_id = getattr(getattr(obj, "investigation", None), "pk", None)
    return bool(
        investigation_id is not None and investigation_queryset_for_user(user).filter(pk=investigation_id).exists()
    )


class IsOwnerOrStaff(BasePermission):
    message = "You do not have permission to access this object."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return False
        if is_privileged(user):
            return True
        media_id = (getattr(view, "kwargs", None) or {}).get("media_id")
        if media_id is not None:
            return media_queryset_for_user(user).filter(pk=media_id).exists()
        return True

    def has_object_permission(self, request, view, obj):
        return user_owns_object(getattr(request, "user", None), obj)
