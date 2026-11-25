from pathlib import Path

from django.conf import settings

from ml_training.inference.architectures import build_audio_model
from ml_training.inference.checkpoints import (
    checkpoint_id,
    load_checkpoint,
    summarize_probabilities,
)
from ml_training.inference.checkpoints import (
    find_checkpoint as find_checkpoint_file,
)

MODEL_VERSION = "logmel-cnn-audio-1.0.0"
CHECKPOINT_NAME = "audio_detector.pt"


def weights_dir():
    return Path(settings.BASE_DIR) / "ml_models" / "audio" / "weights"


def find_checkpoint():
    return find_checkpoint_file(weights_dir(), CHECKPOINT_NAME)


def _load_checkpoint():
    path = find_checkpoint()
    if not path:
        return None
    return load_checkpoint(path, "audio", build_audio_model)


def load_model():
    loaded = _load_checkpoint()
    if loaded is None:
        return None, find_checkpoint()
    return loaded.model, loaded.path


def _source_path(source):
    if isinstance(source, (str, Path)):
        return str(source)
    if isinstance(source, dict) and isinstance(source.get("path"), (str, Path)):
        return str(source["path"])
    return None


def _preprocessing_config(config):
    sample_rate = int(config.get("sample_rate", 16000))
    duration_seconds = float(config.get("duration_seconds", 3.0))
    n_mels = int(config.get("n_mels", 64))
    max_frames = int(config.get("max_frames", 128))
    if sample_rate <= 0 or duration_seconds <= 0 or n_mels <= 0 or max_frames <= 0:
        raise ValueError("invalid log-mel preprocessing values in checkpoint config")
    return {
        "sample_rate": sample_rate,
        "duration_seconds": duration_seconds,
        "n_mels": n_mels,
        "max_frames": max_frames,
        "feature": "librosa.feature.melspectrogram",
        "scale": "librosa.power_to_db",
        "normalization": "per-sample mean and standard deviation",
    }


def predict_audio(source):
    path = _source_path(source)
    if not path:
        return None
    loaded = _load_checkpoint()
    if loaded is None:
        return None
    identifier = checkpoint_id(loaded.path, loaded.sha256)
    if not identifier:
        return None
    try:
        import torch

        from ml_training.preprocessing.audio_preprocess import preprocess_audio

        preprocessing = _preprocessing_config(loaded.config)
        tensor = preprocess_audio(
            path,
            sample_rate=preprocessing["sample_rate"],
            duration_seconds=preprocessing["duration_seconds"],
            n_mels=preprocessing["n_mels"],
            max_frames=preprocessing["max_frames"],
        ).unsqueeze(0)
        with torch.no_grad():
            logits = loaded.model(tensor)
        probabilities = torch.softmax(logits, dim=1)[0].cpu().tolist()
        verdict, manipulation_probability, confidence = summarize_probabilities(probabilities, loaded.verdicts)
        return {
            "verdict": verdict,
            "confidence": confidence,
            "manipulation_probability": manipulation_probability,
            "model_version": MODEL_VERSION,
            "labels": list(loaded.labels),
            "checkpoint": Path(loaded.path).name,
            "checkpoint_path": loaded.path,
            "checkpoint_id": identifier,
            "checkpoint_sha256": loaded.sha256,
            "preprocessing_config": preprocessing,
        }
    except Exception:
        return None
