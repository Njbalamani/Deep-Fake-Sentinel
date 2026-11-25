from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

from .models import ActivityLog, Role, UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "id",
            "user",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "department",
            "phone",
            "is_active_account",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["role", "department", "phone", "is_active_account"]


class UserAdminSerializer(serializers.ModelSerializer):
    profile = UserProfileUpdateSerializer(required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
            "password",
            "profile",
        ]
        read_only_fields = ["id", "date_joined", "last_login"]

    def create(self, validated_data):
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password", None)
        with transaction.atomic():
            user = User(**validated_data)
            if password:
                user.set_password(password)
            else:
                user.set_unusable_password()
            user.save()
            profile, _created = UserProfile.objects.get_or_create(user=user, defaults=profile_data)
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()
        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", None)
        password = validated_data.pop("password", None)
        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            if password:
                instance.set_password(password)
            instance.save()
            profile, _created = UserProfile.objects.get_or_create(user=instance)
            for attr, value in (profile_data or {}).items():
                setattr(profile, attr, value)
            profile.save()
        return instance


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})
    password2 = serializers.CharField(write_only=True, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    department = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    role = serializers.CharField(max_length=20, required=False, allow_blank=True, write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with that username already exists.")
        return value

    def validate(self, attrs):
        confirmation = attrs.get("password2")
        if confirmation and confirmation != attrs["password"]:
            raise serializers.ValidationError({"password2": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2", None)
        validated_data.pop("role", None)
        password = validated_data.pop("password")
        profile_fields = {
            "department": validated_data.pop("department", ""),
            "phone": validated_data.pop("phone", ""),
        }
        with transaction.atomic():
            user = User(**validated_data)
            user.set_password(password)
            user.save()
            profile, _created = UserProfile.objects.get_or_create(
                user=user,
                defaults={"role": Role.VIEWER, **profile_fields},
            )
            for attr, value in profile_fields.items():
                setattr(profile, attr, value)
            profile.role = Role.VIEWER
            profile.save()
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        username = attrs.get("username")
        email = attrs.get("email")
        if not username and email:
            username = User.objects.filter(email__iexact=email).values_list("username", flat=True).first()
        if not username:
            raise serializers.ValidationError("A username or email is required.")
        user = authenticate(
            request=self.context.get("request"),
            username=username,
            password=attrs.get("password", ""),
        )
        if user is None or not user.is_active:
            raise serializers.ValidationError("Invalid credentials.")
        profile = getattr(user, "profile", None)
        if profile is not None and not profile.is_active_account:
            raise serializers.ValidationError("This account is inactive.")
        attrs["user"] = user
        return attrs


class ActivityLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True, allow_null=True)

    class Meta:
        model = ActivityLog
        fields = [
            "id",
            "user",
            "username",
            "action",
            "model",
            "object_id",
            "ip_address",
            "user_agent",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields
