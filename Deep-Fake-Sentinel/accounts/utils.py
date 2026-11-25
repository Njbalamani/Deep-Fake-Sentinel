import json
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request):
    meta = getattr(request, "META", None) or {}
    forwarded = meta.get("HTTP_X_FORWARDED_FOR") or meta.get("HTTP_X_REAL_IP")
    if forwarded:
        return str(forwarded).split(",")[0].strip() or None
    return meta.get("REMOTE_ADDR") or None


def normalize_metadata(metadata):
    if not metadata:
        return {}
    try:
        return json.loads(json.dumps(metadata, default=str))
    except (TypeError, ValueError):
        return {str(key): str(value) for key, value in metadata.items()}


def log_activity(request, action, **metadata):
    from .models import ActivityLog

    data = dict(metadata)
    model = data.pop("model", "")
    if not model:
        model = data.pop("model_name", "")
    if not model:
        model = data.pop("app_label", "")
    object_id = data.pop("object_id", "")
    if object_id is None:
        object_id = ""
    ip_address = data.pop("ip_address", None) or get_client_ip(request)
    user_agent = data.pop("user_agent", None) or (getattr(request, "META", None) or {}).get("HTTP_USER_AGENT", "")

    user = getattr(request, "user", None)
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None

    try:
        return ActivityLog.objects.create(
            user=user,
            action=str(action),
            model=str(model or ""),
            object_id=str(object_id),
            ip_address=ip_address,
            user_agent=str(user_agent or ""),
            metadata=normalize_metadata(data),
        )
    except Exception as exc:
        logger.warning("Unable to record activity %s: %s", action, exc)
        return None


def log_model_activity(request, action, instance, **metadata):
    metadata.setdefault("model", instance._meta.label_lower if hasattr(instance, "_meta") else type(instance).__name__)
    metadata.setdefault("object_id", getattr(instance, "pk", ""))
    return log_activity(request, action, **metadata)
