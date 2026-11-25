from django.urls import path

from .views import ForensicRecordDetailView

app_name = "forensic_analysis"

urlpatterns = [
    path("forensics/<uuid:media_id>/", ForensicRecordDetailView.as_view(), name="forensics-detail"),
]
