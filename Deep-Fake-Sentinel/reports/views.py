from django.db.models import Q
from django.http import FileResponse
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import media_queryset_for_user, report_queryset_for_user

from .serializers import ForensicReportSerializer, ReportCreateSerializer
from .services import generate_report


def get_media_for_user(request, media_id):
    media = media_queryset_for_user(request.user).filter(pk=media_id).first()
    if media is None:
        raise NotFound("Media file not found.")
    return media


class ReportListCreateView(generics.ListCreateAPIView):
    def get_serializer_class(self):
        if self.request.method == "POST":
            return ReportCreateSerializer
        return ForensicReportSerializer

    def get_queryset(self):
        queryset = report_queryset_for_user(self.request.user).select_related("media", "investigation", "generated_by")
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(report_id__icontains=search)
                | Q(media__original_name__icontains=search)
                | Q(media__sha256__icontains=search)
                | Q(investigation__case_id__icontains=search)
                | Q(investigation__title__icontains=search)
                | Q(generated_by__username__icontains=search)
            )
        return queryset.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        media = get_media_for_user(request, serializer.validated_data["media"])
        report = generate_report(media, request.user)
        output = ForensicReportSerializer(report, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)


class ReportDetailView(generics.RetrieveAPIView):
    serializer_class = ForensicReportSerializer

    def get_queryset(self):
        return report_queryset_for_user(self.request.user).select_related("media", "investigation", "generated_by")


class ReportGenerateView(APIView):
    def post(self, request, media_id, *args, **kwargs):
        media = get_media_for_user(request, media_id)
        report = generate_report(media, request.user)
        serializer = ForensicReportSerializer(report, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ReportDownloadView(APIView):
    def get(self, request, pk, *args, **kwargs):
        report = report_queryset_for_user(request.user).filter(pk=pk).first()
        if report is None:
            raise NotFound("Report not found.")
        self.check_object_permissions(request, report)
        if not report.pdf:
            raise NotFound("Report PDF not available.")
        try:
            handle = report.pdf.open("rb")
        except OSError:
            raise NotFound("Report PDF not available.")
        return FileResponse(
            handle,
            as_attachment=True,
            filename="%s.pdf" % report.report_id,
            content_type="application/pdf",
        )
