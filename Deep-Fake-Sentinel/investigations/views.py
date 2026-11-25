from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from accounts.permissions import investigation_queryset_for_user


@login_required
def investigation_list(request):
    return render(request, "investigations/list.html", {"title": "Investigation Cases"})


@login_required
def investigation_detail(request, pk):
    investigation = get_object_or_404(
        investigation_queryset_for_user(request.user).prefetch_related("media", "observations", "timeline_events"),
        pk=pk,
    )
    return render(
        request,
        "investigations/detail.html",
        {"title": investigation.case_id, "investigation": investigation},
    )
