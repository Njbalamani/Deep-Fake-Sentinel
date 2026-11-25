from django.urls import path

from .api import ActivityLogListAPIView, UserDetailAPIView, UserListAPIView

app_name = "accounts_api"

urlpatterns = [
    path("users/", UserListAPIView.as_view(), name="user-list"),
    path("users/<int:pk>/", UserDetailAPIView.as_view(), name="user-detail"),
    path("activity/", ActivityLogListAPIView.as_view(), name="activity-log-list"),
]
