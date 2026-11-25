import hashlib
import os

from .models import IntegrityRecord


def _media_path(media):
    field = getattr(media, "file", None)
    if not field:
        return None
    try:
        path = field.path
    except (ValueError, OSError, NotImplementedError):
        return None
    if not path or not os.path.isfile(path):
        return None
    return path


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_integrity(media):
    original_hash = str(getattr(media, "sha256", "") or "").strip().lower()
    path = _media_path(media)

    if not path:
        current_hash = ""
        status = "UNAVAILABLE"
    else:
        try:
            current_hash = _sha256(path)
        except OSError:
            current_hash = ""
            status = "UNAVAILABLE"
        else:
            if not original_hash:
                status = "UNAVAILABLE"
            elif current_hash == original_hash:
                status = "VERIFIED"
            else:
                status = "TAMPERED"

    record, _ = IntegrityRecord.objects.update_or_create(
        media=media,
        defaults={
            "original_hash": original_hash,
            "current_hash": current_hash,
            "status": status,
        },
    )
    return record
