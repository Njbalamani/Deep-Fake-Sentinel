import sys

from django.urls import include, path

from .views import DashboardMetricsView

app_name = "dashboard"

urlpatterns = [
    path("analytics/dashboard/", DashboardMetricsView.as_view(), name="dashboard-metrics"),
    path("", include("image_detection.urls")),
    path("", include("video_detection.urls")),
    path("", include("audio_detection.urls")),
    path("", include("forensic_analysis.urls")),
    path("", include("metadata_extractor.urls")),
    path("", include("integrity_verification.urls")),
    path("", include("ai_explanations.urls")),
    path("", include("reports.urls")),
]

try:
    api_router = sys.modules["config.api_router"]
except KeyError:
    import config.api_router as api_router

if not getattr(api_router, "_deepfake_sentinel_routes", False):
    api_router.api_urlpatterns.append(path("", include("dashboard.urls")))
    api_router._deepfake_sentinel_routes = True
