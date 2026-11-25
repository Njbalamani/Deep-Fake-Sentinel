from pathlib import Path

from django.conf import settings

from ml_training.inference.architectures import build_image_model
from ml_training.inference.checkpoints import (
    checkpoint_id,
    load_checkpoint,
    summarize_probabilities,
)
from ml_training.inference.checkpoints import (
    find_checkpoint as find_checkpoint_file,
)
from ml_training.preprocessing.image_preprocess import MEAN, STD

MODEL_VERSION = "resnet18-image-1.0.0"
CHECKPOINT_NAME = "image_detector.pt"


def weights_dir():
    return Path(settings.BASE_DIR) / "ml_models" / "image" / "weights"


def find_checkpoint():
    return find_checkpoint_file(weights_dir(), CHECKPOINT_NAME)


def _load_checkpoint():
    path = find_checkpoint()
    if not path:
        return None
    return load_checkpoint(path, "image", build_image_model)


def load_model():
    loaded = _load_checkpoint()
    if loaded is None:
        return None, find_checkpoint()
    return loaded.model, loaded.path


def _preprocessing_config(config):
    image_size = int(config.get("image_size", 224))
    if image_size <= 0:
        raise ValueError("invalid image_size in checkpoint config")
    return {
        "image_size": image_size,
        "mean": list(MEAN),
        "std": list(STD),
        "resize": "torchvision.transforms.functional.resize",
        "center_crop": True,
        "exif_transpose": True,
    }


def predict_image(source):
    loaded = _load_checkpoint()
    if loaded is None:
        return None
    identifier = checkpoint_id(loaded.path, loaded.sha256)
    if not identifier:
        return None
    try:
        import numpy as np
        import torch
        from PIL import Image

        from ml_training.preprocessing.image_preprocess import preprocess_pil_image

        preprocessing = _preprocessing_config(loaded.config)
        image_size = preprocessing["image_size"]
        if isinstance(source, (str, Path)):
            with Image.open(str(source)) as image:
                tensor = preprocess_pil_image(image, image_size=image_size).unsqueeze(0)
        else:
            tensor = preprocess_pil_image(Image.fromarray(np.asarray(source)), image_size=image_size).unsqueeze(0)
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
