from rest_framework import generics
from rest_framework.exceptions import NotFound

from accounts.permissions import IsOwnerOrStaff, media_queryset_for_user

from .models import IntegrityRecord
from .serializers import IntegrityRecordSerializer
from .services import verify_integrity


class IntegrityRecordDetailView(generics.RetrieveAPIView):
    queryset = IntegrityRecord.objects.select_related("media").all()
    serializer_class = IntegrityRecordSerializer
    permission_classes = [IsOwnerOrStaff]
    lookup_field = "media_id"
    lookup_url_kwarg = "media_id"

    def get_queryset(self):
        return super().get_queryset().filter(media_id__in=media_queryset_for_user(self.request.user).values("pk"))

    def get_object(self):
        media_id = self.kwargs["media_id"]
        try:
            record = self.get_queryset().get(media_id=media_id)
        except IntegrityRecord.DoesNotExist:
            media = media_queryset_for_user(self.request.user).filter(pk=media_id).first()
            if media is None:
                raise NotFound("Media file not found.")
            record = verify_integrity(media)
        self.check_object_permissions(self.request, record)
        return record
