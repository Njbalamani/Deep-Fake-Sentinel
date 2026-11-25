from rest_framework import generics
from rest_framework.exceptions import NotFound

from accounts.permissions import IsOwnerOrStaff, media_queryset_for_user

from .models import ImageAnalysis
from .serializers import ImageAnalysisSerializer
from .services import analyze_image


class ImageAnalysisDetailView(generics.RetrieveAPIView):
    queryset = ImageAnalysis.objects.select_related("media").all()
    serializer_class = ImageAnalysisSerializer
    permission_classes = [IsOwnerOrStaff]
    lookup_field = "media_id"
    lookup_url_kwarg = "media_id"

    def get_queryset(self):
        return super().get_queryset().filter(media_id__in=media_queryset_for_user(self.request.user).values("pk"))

    def get_object(self):
        media_id = self.kwargs["media_id"]
        try:
            analysis = self.get_queryset().get(media_id=media_id)
        except ImageAnalysis.DoesNotExist:
            media = media_queryset_for_user(self.request.user).filter(pk=media_id).first()
            if media is None:
                raise NotFound("Media file not found.")
            analysis = analyze_image(media)
        self.check_object_permissions(self.request, analysis)
        return analysis
