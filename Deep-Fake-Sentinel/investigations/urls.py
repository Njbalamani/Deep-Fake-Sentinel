from django.urls import path

from .api import (
    InvestigationDetailAPIView,
    InvestigationListAPIView,
    InvestigationSummaryAPIView,
    ObservationCreateAPIView,
    TimelineAPIView,
)

app_name = "investigations_api"

urlpatterns = [
    path("", InvestigationListAPIView.as_view(), name="investigation-list"),
    path("<uuid:pk>/", InvestigationDetailAPIView.as_view(), name="investigation-detail"),
    path("<uuid:pk>/observations/", ObservationCreateAPIView.as_view(), name="investigation-observations"),
    path("<uuid:pk>/timeline/", TimelineAPIView.as_view(), name="investigation-timeline"),
    path("<uuid:pk>/summary/", InvestigationSummaryAPIView.as_view(), name="investigation-summary"),
]
