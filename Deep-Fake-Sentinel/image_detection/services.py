import os
from pathlib import Path

from django.conf import settings

from .inference import MODEL_VERSION, predict_image
from .models import ImageAnalysis

HEURISTIC_NOTE = "Heuristic evidence only; not authenticity proof."


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


def _indicator(code, severity, detail, value=None, kind="heuristic"):
    return {
        "code": code,
        "kind": kind,
        "severity": severity,
        "detail": detail,
        "value": value,
        "note": HEURISTIC_NOTE if kind == "heuristic" else "Derived from the configured model checkpoint.",
    }


def _cascade_classifier():
    import cv2

    candidates = []
    cascade_data = getattr(cv2, "data", None)
    if cascade_data is not None:
        candidates.append(os.path.join(cascade_data.haarcascades, "haarcascade_frontalface_default.xml"))
    candidates.append("haarcascade_frontalface_default.xml")
    for candidate in candidates:
        try:
            cascade = cv2.CascadeClassifier(candidate)
            if not cascade.empty():
                return cascade
        except Exception:
            continue
    return None


def _mediapipe_model_path():
    configured = os.environ.get("MEDIAPIPE_FACE_MODEL")
    if configured:
        return configured if os.path.isfile(configured) else None
    default = Path(settings.BASE_DIR) / "ml_models" / "mediapipe" / "blaze_face_short_range.tflite"
    return str(default) if default.is_file() else None


def _mediapipe_face_count(rgb_image):
    try:
        import mediapipe as mp
        import numpy as np
        from mediapipe.tasks import python as mediapipe_tasks
        from mediapipe.tasks.python import vision
    except Exception:
        return None
    model_path = _mediapipe_model_path()
    if not model_path:
        return None
    try:
        options = vision.FaceDetectorOptions(
            base_options=mediapipe_tasks.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.IMAGE,
            min_detection_confidence=0.5,
        )
        with vision.FaceDetector.create_from_options(options) as detector:
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb_image))
            result = detector.detect(image)
            return len(result.detections or [])
    except Exception:
        return None


def _detect_faces(image_bgr):
    import cv2

    rgb_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    faces = _mediapipe_face_count(rgb_image)
    if faces is not None:
        return faces, "mediapipe"
    cascade = _cascade_classifier()
    if cascade is None:
        return 0, "unavailable"
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    detected = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    return len(detected), "haar_cascade"


def _artifact_metrics(image_bgr):
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    encoded, buffer = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    ela_mean = 0.0
    if encoded:
        reloaded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if reloaded is not None and reloaded.shape == image_bgr.shape:
            ela_mean = float(np.mean(cv2.absdiff(image_bgr, reloaded)))
    laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    artifact_score = min(1.0, max(0.0, ela_mean / 20.0))
    return artifact_score, {
        "ela_mean_absolute_difference": ela_mean,
        "laplacian_variance": laplacian_variance,
    }


def analyze_frame(image_bgr):
    face_count, face_backend = _detect_faces(image_bgr)
    artifact_score, metrics = _artifact_metrics(image_bgr)
    indicators = [
        _indicator("face_count", "INFO", "Faces detected with %s." % face_backend, face_count),
        _indicator(
            "compression_inconsistency",
            "INFO" if artifact_score < 0.5 else "LOW",
            "JPEG recompression difference and sharpness measured deterministically.",
            artifact_score,
        ),
        _indicator("artifact_measurements", "INFO", "Raw heuristic measurements.", metrics),
    ]
    if artifact_score >= 0.5:
        indicators.append(
            _indicator(
                "elevated_artifact_score",
                "LOW",
                "Elevated compression inconsistency observed; heuristic evidence only.",
                artifact_score,
            )
        )
    return {
        "face_count": face_count,
        "face_backend": face_backend,
        "artifact_score": artifact_score,
        "metrics": metrics,
        "indicators": indicators,
        "prediction": None,
    }


def analyze_image(media):
    path = _media_path(media)
    face_count = 0
    artifact_score = 0.0
    indicators = []
    prediction = None

    if path is None:
        indicators.append(
            _indicator(
                "media_unavailable", "INFO", "The stored image file is not readable at its current path.", kind="model"
            )
        )
    else:
        try:
            import cv2

            image = cv2.imread(path)
        except Exception:
            image = None
        if image is None:
            indicators.append(
                _indicator(
                    "image_decode_failed",
                    "INFO",
                    "The image could not be decoded for heuristic analysis.",
                    kind="model",
                )
            )
        else:
            result = analyze_frame(image)
            face_count = result["face_count"]
            artifact_score = result["artifact_score"]
            indicators = result["indicators"]
            prediction = predict_image(path)
            if prediction is not None and not prediction.get("checkpoint_id"):
                prediction = None

    checkpoint_name = ""
    checkpoint_path = ""
    checkpoint_id = ""
    checkpoint_sha256 = ""
    preprocessing_config = {}
    if prediction is None:
        model_status = "UNTRAINED" if path is not None else "UNAVAILABLE"
        verdict = "INCONCLUSIVE"
        confidence = None
        model_version = "untrained"
    else:
        model_status = "TRAINED"
        verdict = prediction["verdict"]
        confidence = prediction["confidence"]
        model_version = prediction.get("model_version", MODEL_VERSION)
        checkpoint_name = prediction.get("checkpoint", "")
        checkpoint_path = prediction.get("checkpoint_path", "")
        checkpoint_id = prediction.get("checkpoint_id", "")
        checkpoint_sha256 = prediction.get("checkpoint_sha256", "")
        preprocessing_config = prediction.get("preprocessing_config", {})
        indicators.append(
            _indicator(
                "model_prediction",
                "INFO",
                "Prediction produced by the configured image checkpoint.",
                checkpoint_name,
                kind="model",
            )
        )
        indicators.append(
            _indicator(
                "checkpoint_id",
                "INFO",
                "Stable identifier of the applied image checkpoint.",
                checkpoint_id,
                kind="model",
            )
        )

    record, _ = ImageAnalysis.objects.update_or_create(
        media=media,
        defaults={
            "model_version": model_version,
            "model_status": model_status,
            "verdict": verdict,
            "confidence": confidence,
            "checkpoint_name": checkpoint_name,
            "checkpoint_path": checkpoint_path,
            "checkpoint_id": checkpoint_id,
            "checkpoint_sha256": checkpoint_sha256,
            "preprocessing_config": preprocessing_config,
            "indicators": indicators,
            "face_count": face_count,
            "artifact_score": artifact_score,
        },
    )
    return record
