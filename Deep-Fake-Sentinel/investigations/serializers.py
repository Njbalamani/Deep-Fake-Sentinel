from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers

from accounts.permissions import media_queryset_for_user
from media_manager.models import MediaFile

from .models import EvidenceAccessLog, Investigation, Observation, TimelineEvent


def scoped_media_queryset(request):
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        return media_queryset_for_user(user)
    return MediaFile.objects.none()


def resolve_user_id(value, field_name):
    text = str(value).strip()
    if not text:
        return None
    user_model = get_user_model()
    if text.isdigit():
        user = user_model.objects.filter(pk=text).first()
        if user is not None:
            return user.pk
    user = user_model.objects.filter(Q(username__iexact=text) | Q(email__iexact=text)).first()
    if user is None:
        raise serializers.ValidationError({field_name: "Assignee must be a valid user ID or username."})
    return user.pk


class InvestigationSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    assigned_to_username = serializers.CharField(source="assigned_to.username", read_only=True, allow_null=True)
    media = serializers.PrimaryKeyRelatedField(queryset=MediaFile.objects.none(), many=True, required=False)
    media_count = serializers.IntegerField(source="media.count", read_only=True)
    observations = serializers.SerializerMethodField()
    access_history = serializers.SerializerMethodField()

    class Meta:
        model = Investigation
        fields = [
            "id",
            "case_id",
            "title",
            "description",
            "status",
            "priority",
            "created_by",
            "created_by_username",
            "assigned_to",
            "assigned_to_username",
            "media",
            "media_count",
            "observations",
            "access_history",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "case_id",
            "created_by",
            "created_at",
            "updated_at",
            "media_count",
            "observations",
            "access_history",
        ]

    def get_fields(self):
        fields = super().get_fields()
        fields["media"].queryset = scoped_media_queryset(self.context.get("request"))
        return fields

    def to_internal_value(self, data):
        mutable = data.copy()
        alias = "assignee" if "assigned_to" not in mutable and "assignee" in mutable else "assigned_to"
        if alias == "assignee":
            mutable["assigned_to"] = mutable["assignee"]
        if "assigned_to" in mutable:
            mutable["assigned_to"] = resolve_user_id(mutable["assigned_to"], alias)
        priority = mutable.get("priority")
        if isinstance(priority, str):
            normalized = priority.upper()
            mutable["priority"] = "MEDIUM" if normalized == "NORMAL" else normalized
        return super().to_internal_value(mutable)

    def validate_media(self, value):
        allowed_ids = set(
            scoped_media_queryset(self.context.get("request"))
            .filter(pk__in=[item.pk for item in value])
            .values_list("pk", flat=True)
        )
        if any(item.pk not in allowed_ids for item in value):
            raise serializers.ValidationError("You cannot link media you cannot access.")
        return value

    def get_observations(self, obj):
        queryset = obj.observations.select_related("author").order_by("-created_at", "-id")[:10]
        return ObservationSerializer(queryset, many=True, context=self.context).data

    def get_access_history(self, obj):
        media_ids = list(obj.media.values_list("pk", flat=True))
        if not media_ids:
            return []
        request = self.context.get("request")
        if getattr(getattr(request, "user", None), "is_authenticated", False):
            media_ids = list(scoped_media_queryset(request).filter(pk__in=media_ids).values_list("pk", flat=True))
        if not media_ids:
            return []
        queryset = (
            EvidenceAccessLog.objects.filter(media_id__in=media_ids)
            .select_related("user")
            .order_by("-created_at", "-id")[:10]
        )
        return EvidenceAccessLogSerializer(queryset, many=True, context=self.context).data


class ObservationSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = Observation
        fields = ["id", "investigation", "author", "author_username", "note", "created_at"]
        read_only_fields = ["id", "investigation", "author", "author_username", "created_at"]


class TimelineEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, allow_null=True)

    class Meta:
        model = TimelineEvent
        fields = ["id", "investigation", "event", "actor", "actor_username", "created_at"]
        read_only_fields = fields


class EvidenceAccessLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True, allow_null=True)

    class Meta:
        model = EvidenceAccessLog
        fields = ["id", "media", "user", "username", "action", "ip_address", "user_agent", "created_at"]
        read_only_fields = fields
