from datetime import datetime

from django.apps import apps
from django.db.models import Count

from accounts.permissions import investigation_queryset_for_user, media_queryset_for_user, report_queryset_for_user

from .models import ModelMetric

ANALYSES = (
    ("image_detection", "ImageAnalysis", "IMAGE"),
    ("video_detection", "VideoAnalysis", "VIDEO"),
    ("audio_detection", "AudioAnalysis", "AUDIO"),
)
CONFIDENCE_BUCKETS = (
    ("0-20", 0.0, 20.0),
    ("20-40", 20.0, 40.0),
    ("40-60", 40.0, 60.0),
    ("60-80", 60.0, 80.0),
    ("80-100", 80.0, 100.0),
)


def _model(app_label, model_name):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def _field(obj, names):
    for name in names:
        value = getattr(obj, name, None)
        if value is not None and value != "":
            return value.isoformat() if isinstance(value, datetime) else str(value)
    return "not available"


def _bucket(confidence):
    numeric = confidence * 100.0
    for label, lower, upper in CONFIDENCE_BUCKETS:
        if lower <= numeric < upper or (label == "80-100" and numeric <= 100.0):
            return label
    return "out_of_range"


def _empty_metrics():
    confidence_distribution = {label: 0 for label, _, _ in CONFIDENCE_BUCKETS}
    confidence_distribution["not_available"] = 0
    return {
        "total_media": 0,
        "analyses": 0,
        "open_cases": 0,
        "reports": 0,
        "media_counts": {"IMAGE": 0, "VIDEO": 0, "AUDIO": 0, "UNKNOWN": 0},
        "potentially_manipulated": 0,
        "status_counts": {},
        "confidence_distribution": confidence_distribution,
        "recent_investigations": [],
        "detection_history": [],
        "model_metrics": [],
    }


def get_dashboard_metrics(user=None):
    if not getattr(user, "is_authenticated", False):
        return _empty_metrics()

    total_media = 0
    media_counts = {"IMAGE": 0, "VIDEO": 0, "AUDIO": 0, "UNKNOWN": 0}
    status_counts = {}
    scoped_media = media_queryset_for_user(user)

    media_model = _model("media_manager", "MediaFile")
    if media_model is not None:
        total_media = scoped_media.count()
        for row in scoped_media.values("media_type").annotate(total=Count("id")):
            key = str(row.get("media_type") or "UNKNOWN").upper()
            media_counts[key] = media_counts.get(key, 0) + int(row["total"])
        for row in scoped_media.values("status").annotate(total=Count("id")):
            key = str(row.get("status") or "UNKNOWN")
            status_counts[key] = int(row["total"])

    analyses = 0
    potentially_manipulated = set()
    confidence_distribution = {label: 0 for label, _, _ in CONFIDENCE_BUCKETS}
    confidence_distribution["not_available"] = 0
    detection_history = []

    for app_label, model_name, media_type in ANALYSES:
        model = _model(app_label, model_name)
        if model is None:
            continue
        analysis_queryset = model.objects.filter(media_id__in=scoped_media.values("pk"))
        analyses += analysis_queryset.count()
        for media_id in analysis_queryset.filter(verdict="LIKELY_MANIPULATED").values_list("media_id", flat=True):
            potentially_manipulated.add(str(media_id))
        for confidence in analysis_queryset.exclude(confidence__isnull=True).values_list("confidence", flat=True):
            label = _bucket(float(confidence))
            confidence_distribution[label] = confidence_distribution.get(label, 0) + 1
        confidence_distribution["not_available"] += analysis_queryset.filter(confidence__isnull=True).count()
        for row in analysis_queryset.values("media_id", "verdict", "confidence", "created_at").order_by("-created_at")[
            :10
        ]:
            created_at = row["created_at"]
            detection_history.append(
                {
                    "media_type": media_type,
                    "media_id": str(row["media_id"]),
                    "verdict": row["verdict"],
                    "confidence": row["confidence"],
                    "created_at": created_at.isoformat() if created_at else None,
                }
            )

    detection_history.sort(key=lambda item: item["created_at"] or "", reverse=True)
    detection_history = detection_history[:10]

    recent_investigations = []
    open_cases = 0
    investigation_model = _model("investigations", "Investigation")
    if investigation_model is not None:
        queryset = investigation_queryset_for_user(user)
        open_cases = queryset.exclude(status__in=["CLOSED", "RESOLVED"]).count()
        try:
            queryset = queryset.order_by("-created_at")
        except Exception:
            queryset = queryset.order_by("-id")
        for investigation in queryset[:5]:
            try:
                media_count = investigation.media.count()
            except Exception:
                media_count = 0
            recent_investigations.append(
                {
                    "id": str(investigation.pk),
                    "title": _field(investigation, ("title", "name", "reference")),
                    "status": _field(investigation, ("status",)),
                    "created_at": _field(investigation, ("created_at", "created")),
                    "media_count": media_count,
                }
            )

    model_metrics = []
    for row in ModelMetric.objects.values(
        "model_name",
        "version",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "sample_count",
        "trained_at",
        "source",
        "is_trained",
        "created_at",
    ).order_by("-created_at")[:20]:
        trained_at = row["trained_at"]
        created_at = row["created_at"]
        row["trained_at"] = trained_at.isoformat() if trained_at else None
        row["created_at"] = created_at.isoformat() if created_at else None
        model_metrics.append(row)

    return {
        "total_media": total_media,
        "analyses": analyses,
        "open_cases": open_cases,
        "reports": report_queryset_for_user(user).count(),
        "media_counts": media_counts,
        "potentially_manipulated": len(potentially_manipulated),
        "status_counts": status_counts,
        "confidence_distribution": confidence_distribution,
        "recent_investigations": recent_investigations,
        "detection_history": detection_history,
        "model_metrics": model_metrics,
    }
