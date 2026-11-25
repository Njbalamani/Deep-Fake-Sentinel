import os
import shutil
import subprocess
import uuid

from django.conf import settings

from image_detection.services import analyze_frame

from .inference import MODEL_VERSION, predict_video
from .models import VideoAnalysis

MAX_SAMPLED_FRAMES = 16
SUSPICIOUS_THRESHOLD = 0.6
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


def _ffmpeg_executable():
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _video_properties(path):
    import cv2

    capture = cv2.VideoCapture(path)
    try:
        opened = bool(capture.isOpened())
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0) if opened else 0.0
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0) if opened else 0
    finally:
        capture.release()
    return fps, frame_count


def _frames_with_ffmpeg(path, fps, frame_count):
    executable = _ffmpeg_executable()
    if not executable or fps <= 0:
        return []
    duration = frame_count / fps if frame_count > 0 else 0.0
    interval = max(1.0, duration / MAX_SAMPLED_FRAMES) if duration > 0 else 1.0
    root = os.path.join(str(getattr(settings, "MEDIA_ROOT", "")), "analysis", "video_frames")
    try:
        os.makedirs(root, exist_ok=True)
        directory = os.path.join(root, uuid.uuid4().hex)
        os.makedirs(directory, exist_ok=True)
    except OSError:
        return []
    try:
        pattern = os.path.join(directory, "frame_%04d.png")
        command = [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            path,
            "-vf",
            "fps=1/%.6f" % interval,
            "-frames:v",
            str(MAX_SAMPLED_FRAMES),
            pattern,
        ]
        subprocess.run(command, check=True, capture_output=True, timeout=120)
        import cv2

        frames = []
        for index, name in enumerate(sorted(os.listdir(directory))):
            if not name.endswith(".png"):
                continue
            frame = cv2.imread(os.path.join(directory, name))
            if frame is not None:
                frames.append((round(index * interval, 3), frame))
        return frames[:MAX_SAMPLED_FRAMES]
    except Exception:
        return []
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _frames_with_cv2(path, fps, frame_count):
    import cv2

    capture = cv2.VideoCapture(path)
    frames = []
    try:
        if not capture.isOpened():
            return frames
        if frame_count > 0:
            target = min(MAX_SAMPLED_FRAMES, frame_count)
            indexes = sorted(set(int(round(index * (frame_count - 1) / max(1, target - 1))) for index in range(target)))
        else:
            indexes = list(range(MAX_SAMPLED_FRAMES))
        for index in indexes:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            success, frame = capture.read()
            if not success:
                continue
            timestamp = round(index / fps, 3) if fps > 0 else round(float(index), 3)
            frames.append((timestamp, frame))
            if len(frames) >= MAX_SAMPLED_FRAMES:
                break
    finally:
        capture.release()
    return frames


def _temporal_consistency(frames):
    if len(frames) < 2:
        return None
    import cv2
    import numpy as np

    reduced = []
    for _, frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        reduced.append(cv2.resize(gray, (64, 64)).astype(np.float32))
    differences = [
        float(np.mean(np.abs(reduced[index] - reduced[index + 1]))) / 255.0 for index in range(len(reduced) - 1)
    ]
    return min(1.0, max(0.0, 1.0 - float(np.mean(differences))))


def analyze_video(media):
    path = _media_path(media)
    fps = 0.0
    frame_count = 0
    frames = []
    suspicious_frames = []
    indicators = []
    prediction = None
    temporal_consistency = None
    backend = "unavailable"

    if path is None:
        indicators.append(
            _indicator(
                "media_unavailable", "INFO", "The stored video file is not readable at its current path.", kind="model"
            )
        )
    else:
        fps, frame_count = _video_properties(path)
        frames = _frames_with_ffmpeg(path, fps, frame_count)
        backend = "ffmpeg" if frames else "cv2"
        if not frames:
            frames = _frames_with_cv2(path, fps, frame_count)
        temporal_consistency = _temporal_consistency(frames)

        for index, (timestamp, frame) in enumerate(frames):
            result = analyze_frame(frame)
            if result["artifact_score"] >= SUSPICIOUS_THRESHOLD:
                suspicious_frames.append(
                    {
                        "index": index,
                        "timestamp_seconds": timestamp,
                        "artifact_score": result["artifact_score"],
                        "basis": "heuristic",
                        "note": HEURISTIC_NOTE,
                    }
                )
        indicators.extend(
            [
                _indicator("frame_extraction_backend", "INFO", "Frame extraction backend used.", backend),
                _indicator(
                    "sampled_frames", "INFO", "Number of bounded frames sampled deterministically.", len(frames)
                ),
                _indicator(
                    "suspicious_frames",
                    "LOW" if suspicious_frames else "INFO",
                    "Frames above the heuristic artifact threshold. A single frame does not establish a video verdict.",
                    len(suspicious_frames),
                ),
                _indicator(
                    "temporal_consistency", "INFO", "Deterministic frame-to-frame similarity.", temporal_consistency
                ),
            ]
        )
        prediction = predict_video(path)
        if prediction is not None and not prediction.get("checkpoint_id"):
            prediction = None

    checkpoint_name = ""
    checkpoint_path = ""
    checkpoint_id = ""
    checkpoint_sha256 = ""
    preprocessing_config = {}
    if prediction is not None:
        verdict = prediction["verdict"]
        confidence = prediction["confidence"]
        model_status = "TRAINED"
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
                "Prediction produced by the configured video checkpoint.",
                checkpoint_name,
                kind="model",
            )
        )
        indicators.append(
            _indicator(
                "checkpoint_id",
                "INFO",
                "Stable identifier of the applied video checkpoint.",
                checkpoint_id,
                kind="model",
            )
        )
    else:
        verdict = "INCONCLUSIVE"
        confidence = None
        model_status = "UNTRAINED" if path is not None else "UNAVAILABLE"
        model_version = "untrained"
        indicators.append(
            _indicator(
                "model_unavailable",
                "INFO",
                "No trained video checkpoint was applied to the video; verdict is inconclusive.",
                kind="model",
            )
        )

    record, _ = VideoAnalysis.objects.update_or_create(
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
            "frame_count": frame_count,
            "sampled_frames": len(frames),
            "suspicious_frames": suspicious_frames,
            "temporal_consistency": temporal_consistency,
            "indicators": indicators,
        },
    )
    return record
