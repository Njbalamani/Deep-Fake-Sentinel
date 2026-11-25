import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from ml_training.inference.checkpoints import checkpoint_id

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKPOINT = ROOT / "ml_models" / "video" / "weights" / "video_detector.pt"
DISCLAIMER = "Model output is decision support only and is not proof of authenticity or manipulation."


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def emit(payload):
    print(json.dumps(payload, indent=2))


def inconclusive(reason, input_path, checkpoint_path, checkpoint_identifier=None):
    emit(
        {
            "status": "INCONCLUSIVE",
            "verdict": None,
            "reason": reason,
            "input": str(input_path),
            "checkpoint": str(checkpoint_path),
            "checkpoint_id": checkpoint_identifier,
            "generated_at": datetime.now(UTC).isoformat(),
            "disclaimer": DISCLAIMER,
        }
    )
    return 2


def build_model(checkpoint, device):
    from ml_training.inference.architectures import build_video_model

    model = build_video_model(len(checkpoint["labels"]))
    model.load_state_dict(checkpoint["model_state_dict"])
    return model.to(device)


def build_parser():
    parser = argparse.ArgumentParser(description="Standalone video inference from a saved checkpoint.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    parser.add_argument("--device", default="")
    return parser


def run(args):
    input_path = Path(args.input).resolve()
    checkpoint_path = Path(args.checkpoint).resolve()
    checkpoint_hash = sha256_file(checkpoint_path) if checkpoint_path.is_file() else None
    identifier = checkpoint_id(checkpoint_path, checkpoint_hash)
    if not input_path.is_file():
        return inconclusive("input_missing", input_path, checkpoint_path, identifier)
    if not checkpoint_path.is_file():
        return inconclusive("checkpoint_missing", input_path, checkpoint_path)

    import torch

    from ml_training.preprocessing.video_preprocess import preprocess_video

    device_name = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(device_name)
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    labels = checkpoint["labels"]
    config = checkpoint.get("config", {})
    frames = int(config.get("frames", 16))
    image_size = int(config.get("image_size", 224))
    model = build_model(checkpoint, device)
    model.eval()
    tensor = preprocess_video(input_path, num_frames=frames, image_size=image_size).unsqueeze(0).to(device)
    with torch.no_grad():
        logits = model(tensor)
        probabilities = torch.softmax(logits, dim=1)[0].cpu().tolist()
    predicted_index = max(range(len(probabilities)), key=lambda index: probabilities[index])
    if not identifier:
        return inconclusive("checkpoint_id_unavailable", input_path, checkpoint_path)
    verdict = labels[predicted_index].upper()
    emit(
        {
            "status": "ok",
            "verdict": verdict,
            "reason": None,
            "score": float(probabilities[predicted_index]),
            "probabilities": {label: float(value) for label, value in zip(labels, probabilities)},
            "input": str(input_path),
            "input_sha256": sha256_file(input_path),
            "checkpoint": str(checkpoint_path),
            "checkpoint_id": identifier,
            "checkpoint_sha256": checkpoint_hash,
            "preprocessing_config": {"frames": frames, "image_size": image_size},
            "generated_at": datetime.now(UTC).isoformat(),
            "disclaimer": DISCLAIMER,
        }
    )
    return 0


def main():
    raise SystemExit(run(build_parser().parse_args()))


if __name__ == "__main__":
    main()
