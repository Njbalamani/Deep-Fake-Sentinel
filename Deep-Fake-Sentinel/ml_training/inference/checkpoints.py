import hashlib
from dataclasses import dataclass
from pathlib import Path

REAL_LABELS = frozenset({"real", "authentic", "original", "bonafide", "0"})
FAKE_LABELS = frozenset({"fake", "forged", "spoof", "spoofed", "manipulated", "synthetic", "1"})
SUPPORTED_CONFIG_VERSION = "1.0.0"
CHECKPOINT_ID_LENGTH = 16


@dataclass(frozen=True)
class LoadedCheckpoint:
    model: object
    path: str
    sha256: str
    labels: tuple
    verdicts: tuple
    config: dict


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint_id(path, sha256=None):
    value = sha256
    if value is None and path and Path(path).is_file():
        value = sha256_file(path)
    if value is None:
        return None
    identifier = str(value).strip()
    return identifier[:CHECKPOINT_ID_LENGTH] or None


def find_checkpoint(directory, preferred_name):
    directory = Path(directory)
    preferred = directory / preferred_name
    if preferred.is_file():
        return str(preferred)
    candidates = sorted(item for item in directory.glob("*.pt") if item.is_file())
    return str(candidates[0]) if candidates else None


def resolve_verdicts(labels):
    verdicts = []
    for label in labels:
        key = str(label).strip().lower()
        if key in REAL_LABELS:
            verdicts.append("LIKELY_AUTHENTIC")
        elif key in FAKE_LABELS:
            verdicts.append("LIKELY_MANIPULATED")
        else:
            return None
    if len(set(verdicts)) != 2:
        return None
    return tuple(verdicts)


def _read_payload(path):
    import torch

    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:
        return torch.load(path, map_location="cpu")


def load_checkpoint(path, modality, build_model):
    if not path or not Path(path).is_file():
        return None
    try:
        payload = _read_payload(path)
        if not isinstance(payload, dict):
            return None
        labels = payload.get("labels")
        state = payload.get("model_state_dict")
        config = payload.get("config", {})
        if not isinstance(labels, (list, tuple)) or len(labels) < 2 or not isinstance(state, dict):
            return None
        if not isinstance(config, dict) or config.get("modality", modality) != modality:
            return None
        if str(config.get("version", SUPPORTED_CONFIG_VERSION)) != SUPPORTED_CONFIG_VERSION:
            return None
        labels = tuple(str(label) for label in labels)
        verdicts = resolve_verdicts(labels)
        if verdicts is None:
            return None
        model = build_model(len(labels))
        model.load_state_dict(state)
        model.eval()
        return LoadedCheckpoint(
            model=model,
            path=str(Path(path).resolve()),
            sha256=sha256_file(path),
            labels=labels,
            verdicts=verdicts,
            config=config,
        )
    except Exception:
        return None


def summarize_probabilities(probabilities, verdicts):
    manipulation_probability = sum(
        float(value) for value, verdict in zip(probabilities, verdicts) if verdict == "LIKELY_MANIPULATED"
    )
    manipulation_probability = min(1.0, max(0.0, manipulation_probability))
    verdict = "LIKELY_MANIPULATED" if manipulation_probability >= 0.5 else "LIKELY_AUTHENTIC"
    return verdict, manipulation_probability, max(manipulation_probability, 1.0 - manipulation_probability)
