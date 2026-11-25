import argparse
import csv
import hashlib
import json
import random
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "ml_models" / "video" / "weights"
LABEL_ALIASES = {
    "real": "real",
    "authentic": "real",
    "original": "real",
    "0": "real",
    "fake": "fake",
    "forged": "fake",
    "manipulated": "fake",
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


def load_manifest(manifest, data_root):
    required = {"path", "label", "split"}
    rows = []
    with Path(manifest).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise SystemExit("Manifest must contain path,label,split columns")
        for number, raw in enumerate(reader, start=2):
            relative = raw.get("path", "").strip()
            split = raw.get("split", "").strip().lower()
            if not relative or not split:
                raise SystemExit(f"Invalid manifest row {number}")
            path = (data_root / relative).resolve()
            if not path.is_file():
                raise SystemExit(f"Manifest file is missing: {path}")
            rows.append((path, normalize_label(raw.get("label", "")), split))
    if not rows:
        raise SystemExit("Manifest contains no rows")
    return rows


def compute_metrics(label_names, true_values, predicted_values):
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        precision_recall_fscore_support,
    )

    if not true_values:
        return None
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


def build_model(label_count):
    from ml_training.inference.architectures import build_video_model

    return build_video_model(label_count)


def evaluate(model, loader, device, criterion, label_count, label_names):
    import torch

    model.eval()
    total_loss = 0.0
    count = 0
    true_values = []
    predicted_values = []
    with torch.no_grad():
        for inputs, targets in loader:
            inputs = inputs.to(device)
            targets = targets.to(device)
            outputs = model(inputs)
            loss = criterion(outputs, targets)
            total_loss += float(loss.item()) * inputs.size(0)
            count += inputs.size(0)
            true_values.extend(targets.cpu().tolist())
            predicted_values.extend(outputs.argmax(dim=1).cpu().tolist())
    if count == 0:
        return None, None
    return compute_metrics(label_names, true_values, predicted_values), total_loss / count


def build_parser():
    parser = argparse.ArgumentParser(description="Train a video deepfake detector from a local manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="")
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--split", default="val")
    return parser


def run(args):
    import numpy as np
    import torch
    from torch.utils.data import DataLoader

    from ml_training.preprocessing.video_preprocess import preprocess_video

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    device_name = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(device_name)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)

    manifest = Path(args.manifest).resolve()
    data_root = Path(args.data_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    rows = load_manifest(manifest, data_root)
    labels = sorted({label for _, label, _ in rows})
    label_to_index = {label: index for index, label in enumerate(labels)}
    train_rows = [(path, label) for path, label, split in rows if split == "train"]
    val_rows = [(path, label) for path, label, split in rows if split == args.split]
    if not train_rows:
        raise SystemExit("Manifest has no train rows")
    if args.batch_size <= 0 or args.epochs <= 0 or args.frames <= 0 or args.image_size <= 0:
        raise SystemExit("batch-size, epochs, frames, and image-size must be positive")

    transform = lambda path: preprocess_video(path, num_frames=args.frames, image_size=args.image_size)
    train_dataset = MediaDataset(train_rows, label_to_index, transform)
    val_dataset = MediaDataset(val_rows, label_to_index, transform)
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)

    model = build_model(len(labels)).to(device)
    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    train_loss = 0.0
    for epoch in range(args.epochs):
        model.train()
        running_loss = 0.0
        for inputs, targets in train_loader:
            inputs = inputs.to(device)
            targets = targets.to(device)
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item()) * inputs.size(0)
        train_loss = running_loss / max(1, len(train_dataset))
        if val_loader:
            val_metrics, val_loss = evaluate(model, val_loader, device, criterion, len(labels), labels)
            print(f"epoch {epoch + 1}/{args.epochs} train_loss={train_loss:.6f} val_loss={val_loss:.6f}")
        else:
            print(f"epoch {epoch + 1}/{args.epochs} train_loss={train_loss:.6f} val=unavailable")

    val_metrics, val_loss = (None, None)
    if val_loader:
        val_metrics, val_loss = evaluate(model, val_loader, device, criterion, len(labels), labels)

    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "video_detector.pt"
    config = {
        "version": "1.0.0",
        "modality": "video",
        "frames": args.frames,
        "image_size": args.image_size,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "seed": args.seed,
        "epochs": args.epochs,
        "device": str(device),
    }
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "labels": labels,
            "config": config,
            "epoch": args.epochs,
            "source_manifest": str(manifest),
        },
        checkpoint_path,
    )
    with (output_dir / "labels.json").open("w", encoding="utf-8") as handle:
        json.dump({"labels": labels}, handle, indent=2)

    metrics_payload = {
        "status": "ok" if val_metrics else "no_validation_data",
        "generated_at": datetime.now(UTC).isoformat(),
        "manifest": str(manifest),
        "manifest_sha256": sha256_file(manifest),
        "data_root": str(data_root),
        "split": args.split,
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "labels": labels,
        "num_train_samples": len(train_dataset),
        "num_samples": len(val_dataset),
        "accuracy": val_metrics["accuracy"] if val_metrics else None,
        "precision": val_metrics["precision"] if val_metrics else None,
        "recall": val_metrics["recall"] if val_metrics else None,
        "f1": val_metrics["f1"] if val_metrics else None,
        "confusion_matrix": val_metrics["confusion_matrix"] if val_metrics else None,
        "train_loss": float(train_loss),
        "validation_loss": float(val_loss) if val_loss is not None else None,
        "metrics": val_metrics,
    }
    with (output_dir / "metrics.json").open("w", encoding="utf-8") as handle:
        json.dump(metrics_payload, handle, indent=2)
    print(f"Saved checkpoint to {checkpoint_path}")
    print(f"Saved metrics to {output_dir / 'metrics.json'}")


def main():
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
