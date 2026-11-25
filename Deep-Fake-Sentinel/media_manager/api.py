import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import investigation_queryset_for_user, media_queryset_for_user
from accounts.utils import get_client_ip

from .models import AnalysisEvent, MediaStatus
from .serializers import AnalysisEventSerializer, MediaFileSerializer, MediaStatusSerializer
from .services import create_media_from_upload, secure_filename
from .tasks import process_media

logger = logging.getLogger(__name__)


def log_evidence_access(request, media, action="VIEW"):
    try:
        from investigations.models import EvidenceAccessLog
    except (ImportError, LookupError):
        return None
    user = getattr(request, "user", None)
    if user is not None and not getattr(user, "is_authenticated", False):
        user = None
    try:
        return EvidenceAccessLog.objects.create(
            media=media,
            user=user,
            action=action,
            ip_address=get_client_ip(request),
            user_agent=(getattr(request, "META", None) or {}).get("HTTP_USER_AGENT", ""),
        )
    except Exception as exc:
        logger.warning("Unable to log evidence access for %s: %s", media.pk, exc)
        return None


def get_media_for_user(request, pk, view=None):
    media = (
        media_queryset_for_user(request.user)
        .select_related("owner", "investigation")
        .prefetch_related("events")
        .filter(pk=pk)
        .first()
    )
    if media is None:
        raise NotFound("Media not found.")
    if view is not None:
        view.check_object_permissions(request, media)
    return media


class MediaListAPIView(generics.GenericAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        queryset = (
            media_queryset_for_user(request.user).select_related("owner", "investigation").prefetch_related("events")
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())
        type_filter = request.query_params.get("media_type")
        if type_filter:
            queryset = queryset.filter(media_type=type_filter.upper())
        investigation = request.query_params.get("investigation")
        if investigation:
            queryset = queryset.filter(investigation_id=investigation)
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(original_name__icontains=search) | Q(sha256__icontains=search))
        page = self.paginate_queryset(queryset.order_by("-uploaded_at"))
        serializer = MediaFileSerializer(
            page if page is not None else queryset, many=True, context={"request": request}
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def post(self, request):
        uploads = request.FILES.getlist("files") or request.FILES.getlist("file")
        if not uploads:
            uploads = [value for value in request.FILES.values()]
        if not uploads:
            raise ValidationError({"files": "At least one file is required."})

        investigation = None
        investigation_id = request.data.get("investigation")
        if investigation_id:
            try:
                investigation = investigation_queryset_for_user(request.user).filter(pk=investigation_id).first()
            except (ValueError, DjangoValidationError):
                investigation = None
            if investigation is None:
                raise ValidationError({"investigation": "Investigation not found."})

        created_objects = []
        errors = []
        for uploaded in uploads:
            try:
                media = create_media_from_upload(uploaded, request.user, investigation=investigation)
                created_objects.append(media)
            except Exception as exc:
                errors.append({"file": getattr(uploaded, "name", ""), "error": str(exc)})
        if not created_objects:
            raise ValidationError({"files": errors})
        created = []
        for media in created_objects:
            created.append(MediaFileSerializer(media, context={"request": request}).data)
            result = process_media.delay(str(media.pk))
            AnalysisEvent.objects.create(
                media=media,
                stage="pipeline",
                status="QUEUED",
                message=f"Analysis task queued: {getattr(result, 'id', str(media.pk))}.",
            )
        payload = {"created": created, "count": len(created)}
        if errors:
            payload["errors"] = errors
        return Response(payload, status=status.HTTP_201_CREATED)


class MediaDetailAPIView(APIView):
    def get(self, request, pk):
        media = get_media_for_user(request, pk, view=self)
        log_evidence_access(request, media, action="VIEW")
        return Response(MediaFileSerializer(media, context={"request": request}).data)


class MediaDownloadAPIView(APIView):
    def get(self, request, pk):
        media = get_media_for_user(request, pk, view=self)
        if not media.file:
            raise NotFound("File not available.")
        try:
            handle = media.file.open("rb")
        except OSError:
            raise NotFound("File not available.")
        log_evidence_access(request, media, action="DOWNLOAD")
        return FileResponse(
            handle,
            as_attachment=True,
            filename=secure_filename(media.original_name or media.filename),
            content_type=media.mime_type or "application/octet-stream",
        )


class MediaStatusAPIView(APIView):
    def get(self, request, pk):
        media = get_media_for_user(request, pk, view=self)
        return Response(MediaStatusSerializer(media).data)


class MediaReprocessAPIView(APIView):
    def post(self, request, pk):
        media = get_media_for_user(request, pk, view=self)
        with transaction.atomic():
            media.status = MediaStatus.PENDING
            media.error_message = ""
            media.save(update_fields=["status", "error_message", "updated_at"])
        AnalysisEvent.objects.create(media=media, stage="pipeline", status="QUEUED", message="Reprocessing requested.")
        log_evidence_access(request, media, action="REPROCESS")
        result = process_media.delay(str(media.pk))
        media.refresh_from_db()
        payload = MediaStatusSerializer(media).data
        payload["detail"] = "Processing requested."
        payload["task"] = getattr(result, "id", str(media.pk))
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class MediaHistoryAPIView(generics.GenericAPIView):
    def get(self, request, pk):
        get_media_for_user(request, pk, view=self)
        events = AnalysisEvent.objects.filter(media_id=pk).order_by("created_at", "id")
        page = self.paginate_queryset(events)
        serializer = AnalysisEventSerializer(page if page is not None else events, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
