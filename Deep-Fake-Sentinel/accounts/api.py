from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserProfile
from .permissions import IsAdmin
from .serializers import (
    ActivityLogSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserAdminSerializer,
    UserProfileSerializer,
)
from .utils import log_activity, log_model_activity


def get_token_model():
    model_path = getattr(settings, "AUTH_TOKEN_MODEL", "authtoken.Token")
    try:
        return apps.get_model(model_path)
    except (LookupError, ValueError):
        from rest_framework.authtoken.models import Token

        return Token


def build_auth_payload(user, token=None):
    profile, _created = UserProfile.objects.get_or_create(user=user)
    profile_data = UserProfileSerializer(profile).data
    user_data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "role": profile.role,
        "profile": profile_data,
    }
    payload = {
        "user": user_data,
        "profile": profile_data,
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": profile.role,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }
    if token is not None:
        payload["token"] = token.key
        payload["key"] = token.key
    return payload


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _created = get_token_model().objects.get_or_create(user=user)
        log_activity(
            request,
            "USER_REGISTERED",
            model="accounts.UserProfile",
            object_id=user.pk,
            username=user.username,
        )
        return Response(build_auth_payload(user, token), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _created = get_token_model().objects.get_or_create(user=user)
        log_model_activity(request, "USER_LOGGED_IN", user)
        return Response(build_auth_payload(user, token), status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        get_token_model().objects.filter(user=user).delete()
        log_model_activity(request, "USER_LOGGED_OUT", user)
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(build_auth_payload(request.user), status=status.HTTP_200_OK)


class UserListAPIView(generics.GenericAPIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        users = User.objects.all().select_related("profile").order_by("id")
        search = request.query_params.get("search")
        if search:
            users = users.filter(username__icontains=search) | users.filter(email__icontains=search)
        page = self.paginate_queryset(users)
        serializer = UserAdminSerializer(page if page is not None else users, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        payload = request.data
        if isinstance(payload, list):
            results = []
            for item in payload:
                results.append(self._update_one(request, item))
            return Response(results, status=status.HTTP_200_OK)
        return Response(self._update_one(request, payload), status=status.HTTP_200_OK)

    def put(self, request):
        return self.patch(request)

    def _update_one(self, request, payload):
        if not isinstance(payload, dict):
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"detail": "Expected an object with a user id."})
        user_id = payload.get("id") or payload.get("user_id") or payload.get("pk") or payload.get("username")
        if user_id is None:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"id": "This field is required to update a user."})
        queryset = User.objects.all()
        if str(user_id).isdigit():
            user = queryset.filter(pk=int(user_id)).first()
        else:
            user = queryset.filter(username=str(user_id)).first()
        if user is None:
            from rest_framework.exceptions import NotFound

            raise NotFound("User not found.")
        data = dict(payload)
        data.pop("id", None)
        data.pop("user_id", None)
        data.pop("pk", None)
        serializer = UserAdminSerializer(user, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        log_model_activity(request, "USER_UPDATED", updated, changes=list(data.keys()))
        return UserAdminSerializer(updated).data


class UserDetailAPIView(APIView):
    permission_classes = [IsAdmin]

    def get_object(self, pk):
        from rest_framework.exceptions import NotFound

        try:
            return User.objects.select_related("profile").get(pk=pk)
        except User.DoesNotExist:
            raise NotFound("User not found.")

    def get(self, request, pk):
        return Response(UserAdminSerializer(self.get_object(pk)).data)

    def patch(self, request, pk):
        user = self.get_object(pk)
        serializer = UserAdminSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        log_model_activity(request, "USER_UPDATED", updated, changes=list(request.data.keys()))
        return Response(UserAdminSerializer(updated).data)

    def delete(self, request, pk):
        user = self.get_object(pk)
        log_model_activity(request, "USER_DELETED", user)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivityLogListAPIView(generics.GenericAPIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        logs = ActivityLogSerializer.Meta.model.objects.all().select_related("user").order_by("-created_at")
        page = self.paginate_queryset(logs)
        serializer = ActivityLogSerializer(page if page is not None else logs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
