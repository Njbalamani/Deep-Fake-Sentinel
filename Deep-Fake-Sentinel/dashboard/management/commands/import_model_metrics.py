import json
import math
from pathlib import PurePath

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from dashboard.models import ModelMetric

MODEL_NAME_KEYS = (
    "model_name",
    "model",
    "name",
    "checkpoint_name",
    "checkpoint",
    "checkpoint_path",
    "checkpoint_file",
    "model_file",
)
VERSION_KEYS = ("version", "model_version", "checkpoint_version")
NESTED_METRIC_KEYS = ("macro", "weighted", "mean", "overall", "aggregate")
SAMPLE_COUNT_KEYS = ("sample_count", "num_samples", "samples", "n_samples")
METRIC_MAP_KEYS = frozenset(
    {
        "accuracy",
        "precision",
        "recall",
        "f1",
        "f1_score",
        "sample_count",
        "num_samples",
        "confusion_matrix",
        "status",
        *NESTED_METRIC_KEYS,
    }
)


def _path_stem(value):
    text = str(value).strip()
    if not text:
        return ""
    return PurePath(text.replace("\\", "/")).stem or text


def _model_name(entry):
    for key in MODEL_NAME_KEYS:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            name = _path_stem(value)
            if name:
                return name
    return None


def _version(entry):
    for key in VERSION_KEYS:
        value = entry.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    checksum = entry.get("checkpoint_sha256")
    if isinstance(checksum, str) and checksum.strip():
        return checksum.strip()[:16]
    return ""


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _metric_value(entry, keys):
    for key in keys:
        number = _number(entry.get(key))
        if number is not None:
            return number
        for nested_key in NESTED_METRIC_KEYS:
            nested = entry.get(nested_key)
            if not isinstance(nested, dict):
                continue
            for alias in keys:
                number = _number(nested.get(alias))
                if number is not None:
                    return number
    return None


def _sample_count(entry):
    for key in SAMPLE_COUNT_KEYS:
        number = _number(entry.get(key))
        if number is None or number < 0 or number != int(number):
            continue
        return int(number)
    return None


def _is_metric_mapping(value):
    return isinstance(value, dict) and any(key in value for key in METRIC_MAP_KEYS)


def _entries(payload):
    if isinstance(payload, list):
        entries = []
        for item in payload:
            entries.extend(_entries(item))
        return entries
    if not isinstance(payload, dict):
        return []
    metrics = payload.get("metrics")
    base = {key: value for key, value in payload.items() if key != "metrics"}
    if isinstance(metrics, list):
        return [{**base, **item} for item in metrics if isinstance(item, dict)]
    if isinstance(metrics, dict):
        if _is_metric_mapping(metrics):
            return [{**base, **metrics}]
        entries = []
        for name, item in metrics.items():
            if not isinstance(item, dict):
                continue
            entry = dict(base)
            entry.update(item)
            entry.setdefault("model_name", str(name))
            entries.append(entry)
        return entries
    return [payload]


class Command(BaseCommand):
    help = "Import model metrics from JSON produced by training scripts."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", help="Path to a JSON metrics file.")
        parser.add_argument("--file", dest="file_path", help="Path to a JSON metrics file.")
        parser.add_argument("--source", dest="source", help="Override the source value.")

    def handle(self, *args, **options):
        path = options.get("file_path") or options.get("path")
        if not path:
            raise CommandError("Provide a JSON metrics file path.")

        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as exc:
            raise CommandError("Unable to read metrics JSON: %s" % exc)

        entries = _entries(payload)
        imported = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            model_name = _model_name(entry)
            if not model_name:
                continue
            defaults = {}
            accuracy = _metric_value(entry, ("accuracy",))
            precision = _metric_value(entry, ("precision",))
            recall = _metric_value(entry, ("recall",))
            f1 = _metric_value(entry, ("f1", "f1_score"))
            for key, value in (("accuracy", accuracy), ("precision", precision), ("recall", recall), ("f1", f1)):
                if value is not None:
                    defaults[key] = value
            sample_count = _sample_count(entry)
            if sample_count is not None:
                defaults["sample_count"] = sample_count
            trained_at = entry.get("trained_at")
            if isinstance(trained_at, str):
                parsed_at = parse_datetime(trained_at)
                if parsed_at is not None:
                    defaults["trained_at"] = parsed_at
            source = options.get("source") or entry.get("source")
            if source:
                defaults["source"] = str(source)
            trained = entry.get("is_trained", entry.get("trained"))
            if isinstance(trained, bool):
                defaults["is_trained"] = trained
            elif isinstance(trained, str) and trained.strip().lower() in ("true", "false"):
                defaults["is_trained"] = trained.strip().lower() == "true"
            elif "status" in entry:
                defaults["is_trained"] = str(entry["status"]).strip().lower() == "ok"
            else:
                defaults["is_trained"] = any(value is not None for value in (accuracy, precision, recall, f1))
            ModelMetric.objects.update_or_create(
                model_name=str(model_name),
                version=_version(entry),
                defaults=defaults,
            )
            imported += 1

        self.stdout.write(self.style.SUCCESS("Imported %d model metric record(s)." % imported))
