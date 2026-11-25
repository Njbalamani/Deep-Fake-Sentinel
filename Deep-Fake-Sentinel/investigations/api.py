from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import investigation_queryset_for_user, media_queryset_for_user
from accounts.utils import get_client_ip, log_model_activity

from .models import EvidenceAccessLog, TimelineEvent
from .serializers import InvestigationSerializer, ObservationSerializer, TimelineEventSerializer


def validate_linked_media(request):
    raw = request.data.get("media")
    if raw in (None, ""):
        return
    if hasattr(request.data, "getlist"):
        media_ids = request.data.getlist("media")
    elif isinstance(raw, (list, tuple)):
        media_ids = list(raw)
    else:
        media_ids = [raw]
    for media_id in media_ids:
        try:
            authorized = media_queryset_for_user(request.user).filter(pk=media_id).exists()
        except (DjangoValidationError, TypeError, ValueError):
            authorized = False
        if not authorized:
            raise serializers.ValidationError({"media": "You cannot link media you cannot access."})


def get_investigation_or_404(request, pk, view=None):
    investigation = (
        investigation_queryset_for_user(request.user).select_related("created_by", "assigned_to").filter(pk=pk).first()
    )
    if investigation is None:
        raise NotFound("Investigation not found.")
    if view is not None:
        view.check_object_permissions(request, investigation)
    return investigation


class InvestigationListAPIView(generics.GenericAPIView):
    def get(self, request):
        queryset = (
            investigation_queryset_for_user(request.user)
            .select_related("created_by", "assigned_to")
            .prefetch_related("media")
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())
        priority_filter = request.query_params.get("priority")
        if priority_filter:
            queryset = queryset.filter(priority=priority_filter.upper())
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(case_id__icontains=search)
                | Q(assigned_to__username__icontains=search)
                | Q(assigned_to__email__icontains=search)
            )
        page = self.paginate_queryset(queryset.order_by("-created_at"))
        serializer = InvestigationSerializer(
            page if page is not None else queryset, many=True, context=self.get_serializer_context()
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def post(self, request):
        validate_linked_media(request)
        serializer = InvestigationSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            investigation = serializer.save(created_by=request.user)
            TimelineEvent.objects.create(
                investigation=investigation,
                actor=request.user,
                event=f"Investigation {investigation.case_id} was created.",
            )
        log_model_activity(
            request,
            "INVESTIGATION_CREATED",
            investigation,
            model="investigations.Investigation",
            ip_address=get_client_ip(request),
        )
        return Response(
            InvestigationSerializer(investigation, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class InvestigationDetailAPIView(APIView):
    def get(self, request, pk):
        investigation = get_investigation_or_404(request, pk, self)
        return Response(InvestigationSerializer(investigation, context={"request": request}).data)

    def patch(self, request, pk):
        investigation = get_investigation_or_404(request, pk, self)
        validate_linked_media(request)
        previous_status = investigation.status
        serializer = InvestigationSerializer(
            investigation, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            updated = serializer.save()
            if updated.status != previous_status:
                TimelineEvent.objects.create(
                    investigation=updated,
                    actor=request.user,
                    event=f"Status changed from {previous_status} to {updated.status}.",
                )
        log_model_activity(request, "INVESTIGATION_UPDATED", updated)
        return Response(InvestigationSerializer(updated, context={"request": request}).data)


class ObservationCreateAPIView(APIView):
    def post(self, request, pk):
        investigation = get_investigation_or_404(request, pk, self)
        serializer = ObservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            observation = serializer.save(investigation=investigation, author=request.user)
            TimelineEvent.objects.create(
                investigation=investigation,
                actor=request.user,
                event="Observation added.",
            )
        log_model_activity(request, "OBSERVATION_CREATED", observation)
        payload = ObservationSerializer(observation).data
        payload["investigation_id"] = str(investigation.pk)
        return Response(payload, status=status.HTTP_201_CREATED)


class TimelineAPIView(generics.GenericAPIView):
    def get(self, request, pk):
        investigation = get_investigation_or_404(request, pk, self)
        events = investigation.timeline_events.select_related("actor").order_by("created_at", "id")
        page = self.paginate_queryset(events)
        serializer = TimelineEventSerializer(page if page is not None else events, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class InvestigationSummaryAPIView(APIView):
    def get(self, request, pk):
        investigation = get_investigation_or_404(request, pk, self)
        media = investigation.media.all()
        observations = investigation.observations.select_related("author").order_by("-created_at")
        timeline = investigation.timeline_events.select_related("actor").order_by("-created_at")
        media_by_type = {
            item["media_type"]: item["total"] for item in media.values("media_type").annotate(total=Count("id"))
        }
        media_by_status = {item["status"]: item["total"] for item in media.values("status").annotate(total=Count("id"))}
        media_ids = list(media.values_list("id", flat=True))
        access_count = EvidenceAccessLog.objects.filter(media_id__in=media_ids).count() if media_ids else 0
        payload = {
            "investigation": InvestigationSerializer(investigation, context={"request": request}).data,
            "case_id": investigation.case_id,
            "title": investigation.title,
            "status": investigation.status,
            "priority": investigation.priority,
            "media_count": media.count(),
            "observation_count": observations.count(),
            "timeline_event_count": timeline.count(),
            "evidence_access_count": access_count,
            "media_by_type": media_by_type,
            "media_by_status": media_by_status,
            "recent_events": TimelineEventSerializer(timeline[:10], many=True).data,
            "recent_observations": ObservationSerializer(observations[:10], many=True).data,
        }
        return Response(payload)
