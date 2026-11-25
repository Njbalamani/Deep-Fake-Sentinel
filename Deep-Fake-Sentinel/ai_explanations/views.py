from rest_framework import generics
from rest_framework.exceptions import NotFound

from accounts.permissions import media_queryset_for_user

from .models import Explanation
from .serializers import ExplanationSerializer
from .services import generate_explanation


class ExplanationDetailView(generics.RetrieveAPIView):
    serializer_class = ExplanationSerializer
    lookup_field = "media_id"
    lookup_url_kwarg = "media_id"

    def get_queryset(self):
        return Explanation.objects.select_related("media").filter(
            media__in=media_queryset_for_user(self.request.user).values("pk")
        )

    def get_object(self):
        media_id = self.kwargs["media_id"]
        try:
            explanation = self.get_queryset().get(media_id=media_id)
        except Explanation.DoesNotExist:
            media = media_queryset_for_user(self.request.user).filter(pk=media_id).first()
            if media is None:
                raise NotFound("Media file not found.")
            explanation = generate_explanation(media)
        self.check_object_permissions(self.request, explanation)
        return explanation
