from django.urls import path

from .views import ExplanationDetailView

app_name = "ai_explanations"

urlpatterns = [
    path("explanations/<uuid:media_id>/", ExplanationDetailView.as_view(), name="explanation-detail"),
]
