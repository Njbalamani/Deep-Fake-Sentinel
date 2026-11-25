from django.urls import path

from .views import ReportDetailView, ReportDownloadView, ReportGenerateView, ReportListCreateView

app_name = "reports"

urlpatterns = [
    path("reports/", ReportListCreateView.as_view(), name="report-list-create"),
    path("reports/generate/<uuid:media_id>/", ReportGenerateView.as_view(), name="report-generate"),
    path("reports/<uuid:pk>/download/", ReportDownloadView.as_view(), name="report-download"),
    path("reports/<uuid:pk>/", ReportDetailView.as_view(), name="report-detail"),
]
