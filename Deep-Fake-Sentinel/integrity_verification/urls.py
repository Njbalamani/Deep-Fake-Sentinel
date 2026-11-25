from django.urls import path

from .views import IntegrityRecordDetailView

app_name = "integrity_verification"

urlpatterns = [
    path("integrity/<uuid:media_id>/", IntegrityRecordDetailView.as_view(), name="integrity-detail"),
]
