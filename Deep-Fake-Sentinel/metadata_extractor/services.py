import hashlib
import os
import re
from datetime import datetime, timezone

from django.conf import settings

from .models import MetadataRecord

HEURISTIC_LABEL = "Metadata anomaly only; not proof of manipulation."
FILESYSTEM_LABEL = "Filesystem metadata only; not proof of authenticity."


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _filesystem_metadata(path):
    stat_result = os.stat(path)
    return {
        "size_bytes": stat_result.st_size,
        "modified_at": datetime.fromtimestamp(stat_result.st_mtime, timezone.utc).isoformat(),
        "created_at": datetime.fromtimestamp(stat_result.st_ctime, timezone.utc).isoformat(),
        "accessed_at": datetime.fromtimestamp(stat_result.st_atime, timezone.utc).isoformat(),
        "label": FILESYSTEM_LABEL,
    }


def _sanitize_error_text(value, path=None):
    text = str(value)
    candidates = []
    if path:
        candidates.append(str(path))
    media_root = str(getattr(settings, "MEDIA_ROOT", "") or "")
    if media_root:
        candidates.append(media_root)
    for candidate in sorted(set(candidates), key=len, reverse=True):
        if candidate:
            text = text.replace(candidate, "stored media file")
    text = re.sub(r"[A-Za-z]:\\[^\s'\"<>|]+", "stored media file", text)
    text = re.sub(r"[A-Za-z]:/[^\s'\"<>|]+", "stored media file", text)
    text = re.sub(r"\\\\[^\s'\"<>|]+", "stored media file", text)
    text = re.sub(r"/(?:[^\s'\"<>|]+/)*[^\s'\"<>|]+", "stored media file", text)
    return text


def _anomaly(code, severity, detail, label=HEURISTIC_LABEL):
    return {"code": code, "severity": severity, "detail": detail, "label": label}


def _image_metadata(path, exif, technical, anomalies):
    try:
        from PIL import Image

        with Image.open(path) as image:
            technical.update(
                {
                    "width": image.width,
                    "height": image.height,
                    "format": image.format,
                    "mode": image.mode,
                    "animated": bool(getattr(image, "is_animated", False)),
                }
            )
            exif.update({str(key): _json_safe(value) for key, value in image.getexif().items()})
    except Exception as exc:
        sanitized = _sanitize_error_text(exc, path)
        technical["read_error"] = sanitized
        anomalies.append(_anomaly("image_read_error", "INFO", "Image properties could not be read: %s" % sanitized))

    try:
        import piexif

        loaded = piexif.load(path)
        exif["piexif"] = _json_safe({key: loaded.get(key) for key in ("0th", "Exif", "GPS", "1st") if loaded.get(key)})
    except Exception:
        pass

    if not exif:
        anomalies.append(
            _anomaly("missing_exif", "INFO", "No EXIF tags were found. Absence of EXIF is not proof of manipulation.")
        )

    software = " ".join(
        str(value) for key, value in exif.items() if "software" in str(key).lower() or "artist" in str(key).lower()
    ).lower()
    editor_terms = ("photoshop", "gimp", "lightroom", "_canva", "pixlr", " affinity")
    if any(term in software for term in editor_terms):
        anomalies.append(
            _anomaly(
                "editor_software_tag", "LOW", "EXIF references image editing software. This is heuristic evidence only."
            )
        )


def _video_metadata(path, exif, technical, anomalies):
    technical["container"] = os.path.splitext(path)[1].lower().lstrip(".")
    try:
        import cv2

        capture = cv2.VideoCapture(path)
        try:
            if capture.isOpened():
                width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
                frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                fourcc = int(capture.get(cv2.CAP_PROP_FOURCC) or 0)
                codec = "".join(chr((fourcc >> (8 * index)) & 0xFF) for index in range(4)).strip("\x00")
                technical.update(
                    {"width": width, "height": height, "fps": fps, "frame_count": frame_count, "codec": codec}
                )
                if fps <= 0:
                    anomalies.append(
                        _anomaly("missing_frame_rate", "INFO", "Frame rate could not be determined from the container.")
                    )
                if frame_count <= 0:
                    anomalies.append(
                        _anomaly(
                            "missing_frame_count", "INFO", "Frame count could not be determined from the container."
                        )
                    )
            else:
                technical["open_error"] = "OpenCV could not open the video."
                anomalies.append(
                    _anomaly("video_unreadable", "INFO", "OpenCV could not open the video for property extraction.")
                )
        finally:
            capture.release()
    except Exception as exc:
        sanitized = _sanitize_error_text(exc, path)
        technical["read_error"] = sanitized
        anomalies.append(_anomaly("video_property_error", "INFO", "Video properties could not be read: %s" % sanitized))

    try:
        from mutagen import File as MutagenFile

        info = MutagenFile(path)
        if info is not None:
            exif["mutagen_info"] = _json_safe(dict(getattr(info, "info", {})))
            exif["mutagen_tags"] = _json_safe(dict(getattr(info, "tags", {})))
    except Exception:
        pass


def _audio_metadata(path, exif, technical, anomalies):
    technical["container"] = os.path.splitext(path)[1].lower().lstrip(".")
    try:
        import soundfile

        info = soundfile.info(path)
        technical.update(
            {
                "sample_rate": int(info.samplerate),
                "channels": int(info.channels),
                "frames": int(info.frames),
                "duration_seconds": float(info.duration),
                "format": info.format,
                "subtype": info.subtype,
            }
        )
    except Exception as exc:
        technical["soundfile_error"] = _sanitize_error_text(exc, path)
        try:
            from mutagen import File as MutagenFile

            info = MutagenFile(path)
            if info is not None:
                info_data = getattr(info, "info", {})
                technical["duration_seconds"] = float(getattr(info_data, "length", 0) or 0)
                technical["bitrate"] = getattr(info_data, "bitrate", None)
                exif["mutagen_tags"] = _json_safe(dict(getattr(info, "tags", {})))
        except Exception:
            pass
        if "duration_seconds" not in technical:
            anomalies.append(
                _anomaly(
                    "audio_properties_unavailable",
                    "INFO",
                    "Audio properties could not be read by soundfile or mutagen.",
                )
            )

    if not technical.get("sample_rate"):
        anomalies.append(
            _anomaly("missing_sample_rate", "INFO", "Sample rate could not be determined from the audio container.")
        )


def extract_metadata(media):
    path = _media_path(media)
    exif = {}
    technical = {}
    anomalies = []

    raw = {
        "media_id": str(media.pk),
        "original_name": str(getattr(media, "original_name", "") or ""),
        "media_type": str(getattr(media, "media_type", "") or ""),
        "mime_type": str(getattr(media, "mime_type", "") or ""),
        "declared_size_bytes": getattr(media, "size_bytes", None),
        "declared_sha256": str(getattr(media, "sha256", "") or ""),
        "file_available": path is not None,
    }

    if path is None:
        anomalies.append(
            _anomaly("media_file_unavailable", "INFO", "The stored media file is not readable at its current path.")
        )
    else:
        raw["filesystem"] = _filesystem_metadata(path)
        raw["computed_sha256"] = _sha256(path)
        actual_size = raw["filesystem"]["size_bytes"]
        declared_size = getattr(media, "size_bytes", None)
        if declared_size is not None and int(declared_size) != actual_size:
            anomalies.append(
                _anomaly(
                    "size_mismatch",
                    "INFO",
                    "Recorded size differs from the current file size. %s" % FILESYSTEM_LABEL,
                    FILESYSTEM_LABEL,
                )
            )

        uploaded_at = getattr(media, "uploaded_at", None)
        if uploaded_at is not None:
            modified_at = datetime.fromisoformat(raw["filesystem"]["modified_at"])
            if modified_at.date() != uploaded_at.date():
                anomalies.append(
                    _anomaly(
                        "filesystem_timestamp_differs_from_upload",
                        "INFO",
                        "Filesystem modification date differs from the recorded upload date. %s" % FILESYSTEM_LABEL,
                        FILESYSTEM_LABEL,
                    )
                )

        media_type = str(getattr(media, "media_type", "") or "").upper()
        mime_type = str(getattr(media, "mime_type", "") or "").lower()
        if media_type == "IMAGE" or mime_type.startswith("image/"):
            _image_metadata(path, exif, technical, anomalies)
        elif media_type == "VIDEO" or mime_type.startswith("video/"):
            _video_metadata(path, exif, technical, anomalies)
        elif media_type == "AUDIO" or mime_type.startswith("audio/"):
            _audio_metadata(path, exif, technical, anomalies)
        else:
            anomalies.append(
                _anomaly("unknown_media_type", "INFO", "Media type could not be classified for property extraction.")
            )

    record, _ = MetadataRecord.objects.update_or_create(
        media=media,
        defaults={
            "raw": _json_safe(raw),
            "exif": _json_safe(exif),
            "technical": _json_safe(technical),
            "anomalies": _json_safe(anomalies),
        },
    )
    return record
