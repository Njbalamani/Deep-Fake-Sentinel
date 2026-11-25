from rest_framework import generics
from rest_framework.exceptions import NotFound

from accounts.permissions import IsOwnerOrStaff, media_queryset_for_user

from .models import AudioAnalysis
from .serializers import AudioAnalysisSerializer
from .services import analyze_audio


class AudioAnalysisDetailView(generics.RetrieveAPIView):
    queryset = AudioAnalysis.objects.select_related("media").all()
    serializer_class = AudioAnalysisSerializer
    permission_classes = [IsOwnerOrStaff]
    lookup_field = "media_id"
    lookup_url_kwarg = "media_id"

    def get_queryset(self):
        return super().get_queryset().filter(media_id__in=media_queryset_for_user(self.request.user).values("pk"))

    def get_object(self):
        media_id = self.kwargs["media_id"]
        try:
            analysis = self.get_queryset().get(media_id=media_id)
        except AudioAnalysis.DoesNotExist:
            media = media_queryset_for_user(self.request.user).filter(pk=media_id).first()
            if media is None:
                raise NotFound("Media file not found.")
            analysis = analyze_audio(media)
        self.check_object_permissions(self.request, analysis)
        return analysis
