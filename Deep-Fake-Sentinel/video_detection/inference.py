from pathlib import Path

from django.conf import settings

from ml_training.inference.architectures import build_video_model
from ml_training.inference.checkpoints import (
    checkpoint_id,
    load_checkpoint,
    summarize_probabilities,
)
from ml_training.inference.checkpoints import (
    find_checkpoint as find_checkpoint_file,
)
from ml_training.preprocessing.image_preprocess import MEAN, STD

MODEL_VERSION = "r3d18-video-1.0.0"
CHECKPOINT_NAME = "video_detector.pt"


def weights_dir():
    return Path(settings.BASE_DIR) / "ml_models" / "video" / "weights"


def find_checkpoint():
    return find_checkpoint_file(weights_dir(), CHECKPOINT_NAME)


def _load_checkpoint():
    path = find_checkpoint()
    if not path:
        return None
    return load_checkpoint(path, "video", build_video_model)


def load_model():
    loaded = _load_checkpoint()
    if loaded is None:
        return None, find_checkpoint()
    return loaded.model, loaded.path


def _preprocessing_config(config):
    frames = int(config.get("frames", 16))
    image_size = int(config.get("image_size", 224))
    if frames <= 0 or image_size <= 0:
        raise ValueError("invalid frames or image_size in checkpoint config")
    return {
        "frames": frames,
        "image_size": image_size,
        "mean": list(MEAN),
        "std": list(STD),
        "frame_sampling": "sample_video_indices",
        "resize": "torchvision.transforms.functional.resize",
        "center_crop": True,
    }


def predict_video(source):
    loaded = _load_checkpoint()
    if loaded is None or not isinstance(source, (str, Path)):
        return None
    identifier = checkpoint_id(loaded.path, loaded.sha256)
    if not identifier:
        return None
    try:
        import torch

        from ml_training.preprocessing.video_preprocess import preprocess_video

        preprocessing = _preprocessing_config(loaded.config)
        tensor = preprocess_video(
            str(source), num_frames=preprocessing["frames"], image_size=preprocessing["image_size"]
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
