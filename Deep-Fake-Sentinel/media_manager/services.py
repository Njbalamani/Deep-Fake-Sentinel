import hashlib
import os
import re
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

MEDIA_TYPES = {
    "IMAGE": "IMAGE",
    "VIDEO": "VIDEO",
    "AUDIO": "AUDIO",
}

EXTENSION_INFO = {
    ".jpg": ("IMAGE", "image/jpeg"),
    ".jpeg": ("IMAGE", "image/jpeg"),
    ".png": ("IMAGE", "image/png"),
    ".webp": ("IMAGE", "image/webp"),
    ".mp4": ("VIDEO", "video/mp4"),
    ".mov": ("VIDEO", "video/quicktime"),
    ".avi": ("VIDEO", "video/x-msvideo"),
    ".wav": ("AUDIO", "audio/wav"),
    ".mp3": ("AUDIO", "audio/mpeg"),
    ".m4a": ("AUDIO", "audio/mp4"),
}


class InvalidUpload(ValidationError, ValueError):
    pass


def secure_filename(name):
    value = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    if not value or value in (".", ".."):
        value = "file"
    stem, extension = os.path.splitext(value)
    extension = extension.lower()
    if len(extension) > 10:
        extension = ""
    stem = re.sub(r"_+", "_", stem)[:120].strip("_") or "file"
    return stem + extension


def compute_sha256(path):
    digest = hashlib.sha256()
    if hasattr(path, "chunks") and callable(path.chunks):
        for chunk in path.chunks():
            digest.update(chunk)
        return digest.hexdigest()
    if hasattr(path, "read") and callable(path.read):
        try:
            path.seek(0)
        except (AttributeError, OSError, ValueError):
            pass
        for chunk in iter(lambda: path.read(1024 * 1024), b""):
            digest.update(chunk)
        try:
            path.seek(0)
        except (AttributeError, OSError, ValueError):
            pass
        return digest.hexdigest()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_header(uploaded):
    try:
        uploaded.seek(0)
        header = uploaded.read(64) or b""
        uploaded.seek(0)
        return header
    except (AttributeError, OSError, ValueError):
        return b""


def _matches_magic(header, extension):
    if not header:
        return False
    if extension in (".jpg", ".jpeg"):
        return header.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".webp":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    if extension in (".mp4", ".mov", ".m4a"):
        if header[:4] in (b"ftyp", b"styp"):
            return True
        return len(header) >= 12 and header[4:8] in (b"ftyp", b"styp", b"moov", b"mdat")
    if extension == ".avi":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI "
    if extension == ".wav":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    if extension == ".mp3":
        return header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0)
    return False


def validate_upload(uploaded):
    if uploaded is None or not hasattr(uploaded, "name") or not hasattr(uploaded, "read"):
        raise InvalidUpload("No valid uploaded file was provided.")

    original_name = os.path.basename(str(getattr(uploaded, "name", "") or "").replace("\\", "/"))
    safe_name = secure_filename(original_name or "file")
    extension = os.path.splitext(safe_name)[1].lower()

    allowed = [str(item).lower() for item in getattr(settings, "ALLOWED_MEDIA_EXTENSIONS", EXTENSION_INFO.keys())]
    if extension not in allowed or extension not in EXTENSION_INFO:
        raise InvalidUpload(f'Unsupported file extension "{extension}".')

    size = int(getattr(uploaded, "size", 0) or 0)
    max_bytes = int(getattr(settings, "MAX_UPLOAD_SIZE_MB", 100)) * 1024 * 1024
    if size <= 0:
        raise InvalidUpload("The uploaded file is empty.")
    if size > max_bytes:
        raise InvalidUpload(
            f"File exceeds the maximum allowed size of {getattr(settings, 'MAX_UPLOAD_SIZE_MB', 100)} MB."
        )

    media_type, mime_type = EXTENSION_INFO[extension]
    header = _read_header(uploaded)
    if not _matches_magic(header, extension):
        raise InvalidUpload("File content does not match its extension or is not a supported format.")

    declared = str(getattr(uploaded, "content_type", "") or "").lower()
    if declared and declared not in ("application/octet-stream", "binary/octet-stream"):
        if declared.split("/")[0] not in (mime_type.split("/")[0], "application"):
            raise InvalidUpload("Declared content type does not match the file format.")

    try:
        uploaded.seek(0)
    except (AttributeError, OSError, ValueError):
        pass

    return {
        "file": uploaded,
        "original_name": original_name or safe_name,
        "secure_name": safe_name,
        "extension": extension,
        "media_type": media_type,
        "mime_type": mime_type,
        "size_bytes": size,
        "sha256": compute_sha256(uploaded),
    }


def build_upload_path(instance, filename):
    now = timezone.now()
    return f"uploads/{now:%Y/%m}/{secure_filename(filename)}"


def create_media_from_upload(uploaded, user, investigation=None):
    from accounts.models import ActivityLog

    from .models import AnalysisEvent, MediaFile

    normalized = validate_upload(uploaded)
    uploaded.name = normalized["secure_name"]

    media = MediaFile(
        owner=user,
        investigation=investigation,
        original_name=normalized["original_name"],
        media_type=normalized["media_type"],
        mime_type=normalized["mime_type"],
        size_bytes=normalized["size_bytes"],
        sha256=normalized["sha256"],
    )
    media.file.save(normalized["secure_name"], uploaded, save=False)
    media.save()
    AnalysisEvent.objects.create(
        media=media,
        stage="upload",
        status="COMPLETED",
        message=f"Stored {normalized['secure_name']} ({normalized['size_bytes']} bytes).",
    )
    try:
        ActivityLog.objects.create(
            user=user,
            action="MEDIA_UPLOADED",
            model="media_manager.MediaFile",
            object_id=str(media.pk),
            metadata={"original_name": normalized["original_name"], "media_type": normalized["media_type"]},
        )
    except Exception:
        pass
    return media


def refresh_hash(media):
    digest = None
    try:
        digest = compute_sha256(media.file.path)
    except (AttributeError, OSError, ValueError):
        try:
            media.file.open("rb")
            digest = compute_sha256(media.file)
        except Exception:
            digest = None
    if digest and media.sha256 != digest:
        media.sha256 = digest
        media.save(update_fields=["sha256", "updated_at"])
    return digest or media.sha256
