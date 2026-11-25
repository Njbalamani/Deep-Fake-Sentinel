import argparse
import csv
import hashlib
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
SPLIT_ALIASES = {"train": "train", "val": "val", "validation": "val", "test": "test"}
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


def normalize_label(value):
    key = value.strip().lower()
    return LABEL_ALIASES.get(key, key)


def split_from_parts(parts):
    for part in parts:
        alias = SPLIT_ALIASES.get(part.strip().lower())
        if alias:
            return alias
    return None


def hash_split(relative_path, seed, train_frac, val_frac):
    digest = hashlib.sha256(f"{seed}:{relative_path.as_posix()}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") / float(1 << 64)
    if bucket < train_frac:
        return "train"
    if bucket < train_frac + val_frac:
        return "val"
    return "test"


def discover_rows(root, labels, split_mode, seed, train_frac, val_frac):
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        relative = path.relative_to(root)
        label = None
        for part in relative.parts[:-1]:
            candidate = normalize_label(part)
            if candidate in labels:
                label = candidate
                break
        if label is None:
            continue
        if split_mode == "dir":
            split = split_from_parts(relative.parts[:-1]) or hash_split(relative, seed, train_frac, val_frac)
        else:
            split = hash_split(relative, seed, train_frac, val_frac)
        rows.append((relative.as_posix(), label, split))
    return rows


def write_manifest(rows, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "label", "split"])
        writer.writerows(rows)


def build_parser():
    parser = argparse.ArgumentParser(description="Build an image manifest from a local folder.")
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--labels", nargs="+", default=["real", "fake"])
    parser.add_argument("--split-mode", choices=["dir", "hash"], default="dir")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-frac", type=float, default=0.7)
    parser.add_argument("--val-frac", type=float, default=0.15)
    return parser


def main():
    args = build_parser().parse_args()
    if args.train_frac < 0 or args.val_frac < 0 or args.train_frac + args.val_frac > 1:
        raise SystemExit("train-frac and val-frac must be non-negative and sum to at most 1")
    root = Path(args.dataset_root).resolve()
    if not root.is_dir():
        raise SystemExit(f"Dataset root is not a directory: {root}")
    labels = tuple(normalize_label(label) for label in args.labels)
    rows = discover_rows(root, labels, args.split_mode, args.seed, args.train_frac, args.val_frac)
    if not rows:
        raise SystemExit("No supported image files found with a recognized label folder")
    output = Path(args.output).resolve()
    write_manifest(rows, output)
    print(f"Wrote {len(rows)} rows to {output}")


if __name__ == "__main__":
    main()
