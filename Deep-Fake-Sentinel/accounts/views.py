from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from .models import Role, UserProfile
from .utils import log_activity


def _safe_redirect(request):
    target = request.POST.get("next") or request.GET.get("next") or request.META.get("HTTP_REFERER")
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(target)
    return redirect("landing")


@require_http_methods(["GET", "POST"])
def login_page(request):
    error = ""
    if request.method == "POST":
        username = request.POST.get("username") or request.POST.get("email") or ""
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is None and "@" in username:
            matched = User.objects.filter(email__iexact=username).values_list("username", flat=True).first()
            if matched:
                user = authenticate(request, username=matched, password=password)
        profile = getattr(user, "profile", None) if user else None
        if user is not None and (profile is None or profile.is_active_account):
            django_login(request, user)
            log_activity(request, "USER_LOGGED_IN", model="auth.User", object_id=user.pk)
            return _safe_redirect(request)
        error = "Invalid credentials or inactive account."
    return render(request, "accounts/login.html", {"title": "Secure Sign In", "error": error})


@require_http_methods(["GET", "POST"])
def register_page(request):
    error = ""
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password") or ""
        confirmation = request.POST.get("password2") or request.POST.get("confirm_password") or ""
        if not username or not password:
            error = "Username and password are required."
        elif password != confirmation:
            error = "Passwords do not match."
        elif len(password) < 8:
            error = "Password must be at least 8 characters long."
        elif User.objects.filter(username__iexact=username).exists():
            error = "That username is already taken."
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=request.POST.get("first_name") or "",
                last_name=request.POST.get("last_name") or "",
            )
            UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    "role": Role.VIEWER,
                    "department": request.POST.get("department") or "",
                    "phone": request.POST.get("phone") or "",
                },
            )
            log_activity(request, "USER_REGISTERED", model="accounts.UserProfile", object_id=user.pk)
            django_login(request, user)
            return redirect("landing")
    return render(request, "accounts/register.html", {"title": "Create Analyst Account", "error": error})


@require_http_methods(["GET", "POST"])
def logout_page(request):
    log_activity(request, "USER_LOGGED_OUT", model="auth.User", object_id=getattr(request.user, "pk", None))
    django_logout(request)
    return redirect("login")
