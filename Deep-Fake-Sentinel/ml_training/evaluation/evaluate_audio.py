import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKPOINT = ROOT / "ml_models" / "audio" / "weights" / "audio_detector.pt"
LABEL_ALIASES = {
    "real": "real",
    "authentic": "real",
    "original": "real",
    "bonafide": "real",
    "0": "real",
    "fake": "fake",
    "forged": "fake",
    "spoof": "fake",
    "spoofed": "fake",
    "synthetic": "fake",
    "1": "fake",
}


class MediaDataset:
    def __init__(self, rows, label_to_index, transform):
        self.rows = rows
        self.label_to_index = label_to_index
        self.transform = transform

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        path, label = self.rows[index]
        return self.transform(path), self.label_to_index[label]


def normalize_label(value):
    key = value.strip().lower()
    if key not in LABEL_ALIASES:
        raise SystemExit(f"Unknown label in manifest: {value}")
    return LABEL_ALIASES[key]


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_checkpoint(path, device):
    checkpoint_path = Path(path).resolve()
    if not checkpoint_path.is_file():
        raise SystemExit(f"Checkpoint missing: {checkpoint_path}")
    import torch

    return torch.load(checkpoint_path, map_location=device, weights_only=False)


def load_rows(manifest, data_root, split, labels):
    label_to_index = {label: index for index, label in enumerate(labels)}
    rows = []
    with Path(manifest).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"path", "label", "split"}.issubset(reader.fieldnames):
            raise SystemExit("Manifest must contain path,label,split columns")
        for raw in reader:
            if raw.get("split", "").strip().lower() != split:
                continue
            relative = raw.get("path", "").strip()
            label = normalize_label(raw.get("label", ""))
            if label not in label_to_index:
                raise SystemExit(f"Manifest label not present in checkpoint: {label}")
            path = (data_root / relative).resolve()
            if not path.is_file():
                raise SystemExit(f"Manifest file is missing: {path}")
            rows.append((path, label))
    if not rows:
        raise SystemExit(f"Manifest has no rows for split: {split}")
    return rows, label_to_index


def build_model(checkpoint, device):
    import torch

    labels = checkpoint["labels"]

    class AudioClassifier(torch.nn.Module):
        def __init__(self, num_labels):
            super().__init__()
            self.features = torch.nn.Sequential(
                torch.nn.Conv2d(1, 16, kernel_size=3, padding=1),
                torch.nn.ReLU(),
                torch.nn.MaxPool2d(2),
                torch.nn.Conv2d(16, 32, kernel_size=3, padding=1),
                torch.nn.ReLU(),
                torch.nn.MaxPool2d(2),
                torch.nn.Conv2d(32, 64, kernel_size=3, padding=1),
                torch.nn.ReLU(),
                torch.nn.AdaptiveAvgPool2d((1, 1)),
            )
            self.classifier = torch.nn.Linear(64, num_labels)

        def forward(self, inputs):
            features = self.features(inputs)
            flattened = torch.flatten(features, 1)
            return self.classifier(flattened)

    model = AudioClassifier(len(labels))
    model.load_state_dict(checkpoint["model_state_dict"])
    return model.to(device)


def compute_metrics(label_names, true_values, predicted_values):
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        precision_recall_fscore_support,
    )

    indices = list(range(len(label_names)))
    precision, recall, f1, support = precision_recall_fscore_support(
        true_values, predicted_values, labels=indices, zero_division=0
    )
    macro = precision_recall_fscore_support(
        true_values, predicted_values, labels=indices, average="macro", zero_division=0
    )
    weighted = precision_recall_fscore_support(
        true_values, predicted_values, labels=indices, average="weighted", zero_division=0
    )
    return {
        "accuracy": float(accuracy_score(true_values, predicted_values)),
        "precision": {name: float(value) for name, value in zip(label_names, precision)},
        "recall": {name: float(value) for name, value in zip(label_names, recall)},
        "f1": {name: float(value) for name, value in zip(label_names, f1)},
        "support": {name: int(value) for name, value in zip(label_names, support)},
        "macro": {
            "precision": float(macro[0]),
            "recall": float(macro[1]),
            "f1": float(macro[2]),
        },
        "weighted": {
            "precision": float(weighted[0]),
            "recall": float(weighted[1]),
            "f1": float(weighted[2]),
        },
        "confusion_matrix": confusion_matrix(true_values, predicted_values, labels=indices).tolist(),
    }


def build_parser():
    parser = argparse.ArgumentParser(description="Evaluate an audio checkpoint from a local manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    parser.add_argument("--output", default="")
    parser.add_argument("--split", default="test")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", default="")
    return parser


def run(args):
    import torch
    from torch.utils.data import DataLoader

    from ml_training.preprocessing.audio_preprocess import preprocess_audio

    device_name = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(device_name)
    checkpoint_path = Path(args.checkpoint).resolve()
    checkpoint = load_checkpoint(checkpoint_path, device)
    labels = checkpoint["labels"]
    config = checkpoint.get("config", {})
    sample_rate = int(config.get("sample_rate", 16000))
    duration_seconds = float(config.get("duration_seconds", 3.0))
    n_mels = int(config.get("n_mels", 64))
    max_frames = int(config.get("max_frames", 128))

    manifest = Path(args.manifest).resolve()
    data_root = Path(args.data_root).resolve()
    rows, label_to_index = load_rows(manifest, data_root, args.split, labels)
    transform = lambda path: preprocess_audio(
        path,
        sample_rate=sample_rate,
        duration_seconds=duration_seconds,
        n_mels=n_mels,
        max_frames=max_frames,
    )
    dataset = MediaDataset(rows, label_to_index, transform)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)
    model = build_model(checkpoint, device)
    model.eval()

    true_values = []
    predicted_values = []
    with torch.no_grad():
        for inputs, targets in loader:
            outputs = model(inputs.to(device))
            predicted_values.extend(outputs.argmax(dim=1).cpu().tolist())
            true_values.extend(targets.tolist())

    metrics = compute_metrics(labels, true_values, predicted_values)
    output_path = Path(args.output).resolve() if args.output else checkpoint_path.parent / "evaluation.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "ok",
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest": str(manifest),
        "manifest_sha256": sha256_file(manifest),
        "data_root": str(data_root),
        "split": args.split,
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "labels": labels,
        "num_samples": len(dataset),
        "accuracy": metrics["accuracy"],
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "f1": metrics["f1"],
        "confusion_matrix": metrics["confusion_matrix"],
        "metrics": metrics,
    }
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(f"Saved evaluation to {output_path}")


def main():
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
