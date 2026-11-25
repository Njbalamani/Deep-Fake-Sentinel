import importlib
import inspect
import json
import logging

from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)

STAGES = [
    ("metadata_extraction", "metadata_extractor.services", "extract_metadata"),
    ("integrity_verification", "integrity_verification.services", "verify_integrity"),
]

FORENSIC_STAGE = ("forensic_analysis", "forensic_analysis.services", "analyze_forensics")

DETECTION_STAGES = {
    "IMAGE": ("image_detection", "image_detection.services", "analyze_image"),
    "VIDEO": ("video_detection", "video_detection.services", "analyze_video"),
    "AUDIO": ("audio_detection", "audio_detection.services", "analyze_audio"),
}

EXPLANATION_STAGE = ("ai_explanation", "ai_explanations.services", "generate_explanation")


def log_event(media, stage, status, message=""):
    from .models import AnalysisEvent

    try:
        with transaction.atomic():
            AnalysisEvent.objects.create(
                media=media,
                stage=stage,
                status=status,
                message=str(message or "")[:2000],
            )
    except Exception as exc:
        logger.warning("Unable to log analysis event %s: %s", stage, exc)


def invoke_stage(func, media):
    try:
        signature = inspect.signature(func)
        params = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
            and parameter.name not in ("self", "cls")
        ]
    except (TypeError, ValueError):
        return func(media)
    if not params:
        return func()
    name = params[0].name
    if name in ("media_id", "media_uuid", "media_pk", "pk", "id", "uuid"):
        return func(str(media.pk))
    if name in ("path", "file_path", "filepath", "media_path"):
        return func(media.file.path)
    if name in ("uploaded", "upload", "file", "file_obj"):
        return func(media.file)
    return func(media)


def summarize(result):
    if result is None:
        return "Stage completed."
    if isinstance(result, (dict, list, tuple)):
        try:
            return json.dumps(result, default=str)[:1000]
        except (TypeError, ValueError):
            pass
    return str(result)[:1000]


def run_stage(media, stage):
    stage_name, module_path, function_name = stage
    log_event(media, stage_name, "STARTED", module_path)
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        log_event(media, stage_name, "SKIPPED", f"{module_path} unavailable: {exc}")
        return None
    function = getattr(module, function_name, None)
    if function is None or not callable(function):
        log_event(media, stage_name, "SKIPPED", f"{module_path}.{function_name} is not available.")
        return None
    result = invoke_stage(function, media)
    log_event(media, stage_name, "COMPLETED", summarize(result))
    return result


@shared_task(name="media_manager.tasks.process_media")
def process_media(media_id):
    from .models import MediaFile, MediaStatus
    from .services import refresh_hash

    try:
        media = MediaFile.objects.get(pk=media_id)
    except MediaFile.DoesNotExist:
        logger.error("Cannot process missing media %s", media_id)
        return {"media_id": str(media_id), "status": "FAILED", "error": "Media not found."}

    with transaction.atomic():
        media.status = MediaStatus.PROCESSING
        media.error_message = ""
        media.save(update_fields=["status", "error_message", "updated_at"])
    log_event(media, "pipeline", "PROCESSING", "Analysis started.")

    try:
        try:
            digest = refresh_hash(media)
            log_event(media, "hash_verification", "COMPLETED", f"SHA-256: {digest}")
        except Exception as exc:
            log_event(media, "hash_verification", "SKIPPED", f"Unable to refresh hash: {exc}")

        for stage in STAGES:
            run_stage(media, stage)

        detection = DETECTION_STAGES.get(media.media_type)
        if detection is not None:
            run_stage(media, detection)
        else:
            log_event(media, "detection", "SKIPPED", f"No detector registered for {media.media_type}.")

        run_stage(media, FORENSIC_STAGE)
        run_stage(media, EXPLANATION_STAGE)

        with transaction.atomic():
            media.status = MediaStatus.COMPLETED
            media.error_message = ""
            media.save(update_fields=["status", "error_message", "updated_at"])
        log_event(media, "pipeline", "COMPLETED", "Analysis completed successfully.")
        return {"media_id": str(media.pk), "status": "COMPLETED"}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        with transaction.atomic():
            media.status = MediaStatus.FAILED
            media.error_message = error[:2000]
            media.save(update_fields=["status", "error_message", "updated_at"])
        log_event(media, "pipeline", "FAILED", error)
        logger.exception("Media processing failed for %s", media_id)
        return {"media_id": str(media.pk), "status": "FAILED", "error": error}
