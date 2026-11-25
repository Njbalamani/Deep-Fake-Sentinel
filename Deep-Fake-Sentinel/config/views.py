from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def landing(request):
    return render(request, "index.html", {"title": "DEEPFAKE SENTINEL"})


@login_required
def dashboard_home(request):
    return render(request, "dashboard/home.html", {"title": "Forensic Command Center"})


@login_required
def media_list(request):
    return render(request, "media/list.html", {"title": "Media Evidence Library"})


@login_required
def report_list(request):
    return render(request, "reports/list.html", {"title": "Forensic Reports"})
