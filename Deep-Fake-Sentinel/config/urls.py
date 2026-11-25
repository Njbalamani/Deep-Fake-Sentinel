from django.contrib import admin
from django.urls import include, path

from accounts.views import login_page, logout_page, register_page
from config import views as site_views
from config.api_router import api_urlpatterns
from investigations.views import investigation_detail, investigation_list

admin.site.site_header = "DEEPFAKE SENTINEL"
admin.site.site_title = "DEEPFAKE SENTINEL"
admin.site.index_title = "Administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", site_views.landing, name="landing"),
    path("dashboard/", site_views.dashboard_home, name="dashboard_home"),
    path("media/", site_views.media_list, name="media_list"),
    path("investigations/", investigation_list, name="investigation_list"),
    path("investigations/<uuid:pk>/", investigation_detail, name="investigation_detail"),
    path("reports/", site_views.report_list, name="report_list"),
    path("accounts/login/", login_page, name="login"),
    path("accounts/register/", register_page, name="register"),
    path("accounts/logout/", logout_page, name="logout"),
    path("api/", include(api_urlpatterns)),
]
