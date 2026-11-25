import importlib
import logging
import sys

from django.urls import include, path
from rest_framework.permissions import AllowAny
from rest_framework.routers import APIRootView, DefaultRouter

logger = logging.getLogger(__name__)

api_router = sys.modules[__name__]


class PublicAPIRootView(APIRootView):
    permission_classes = [AllowAny]


router = DefaultRouter()
router.APIRootView = PublicAPIRootView

api_urlpatterns = [
    path("", include(router.urls)),
    path("api-auth/", include("rest_framework.urls")),
    path("auth/", include("accounts.api_urls")),
    path("accounts/", include("accounts.urls")),
    path("media/", include("media_manager.urls")),
    path("investigations/", include("investigations.urls")),
]

OPTIONAL_APP_URLS = [
    "reports",
    "dashboard",
    "image_detection",
    "video_detection",
    "audio_detection",
    "forensic_analysis",
    "metadata_extractor",
    "integrity_verification",
    "ai_explanations",
]


def module_available(module_name):
    try:
        return importlib.import_module(module_name) is not None
    except Exception as exc:
        logger.warning("Skipping unavailable URL module %s: %s", module_name, exc)
        return False


if module_available("dashboard.urls"):
    if not getattr(api_router, "_deepfake_sentinel_routes", False):
        api_urlpatterns.append(path("", include("dashboard.urls")))
        _deepfake_sentinel_routes = True
else:
    for app_name in OPTIONAL_APP_URLS:
        if module_available(f"{app_name}.urls"):
            api_urlpatterns.append(path("", include(f"{app_name}.urls")))
