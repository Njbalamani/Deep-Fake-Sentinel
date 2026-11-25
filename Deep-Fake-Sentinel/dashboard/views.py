from rest_framework.response import Response
from rest_framework.views import APIView

from .services import get_dashboard_metrics


class DashboardMetricsView(APIView):
    def get(self, request, *args, **kwargs):
        return Response(get_dashboard_metrics(request.user))
