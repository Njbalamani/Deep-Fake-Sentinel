import http.client
import json
import urllib.parse

from django.apps import apps
from django.conf import settings

HEURISTIC_NOTE = "Heuristic evidence only; not authenticity proof."


def _record(app_label, model_name, media):
    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        return None
    if model is None:
        return None
    try:
        return model.objects.get(media=media)
    except model.DoesNotExist:
        return None


def _add(indicators, source, label, value, kind="heuristic", note=None):
    indicators.append(
        {
            "source": source,
            "label": label,
            "value": value,
            "kind": kind,
            "note": note or (HEURISTIC_NOTE if kind == "heuristic" else "Taken directly from an analysis record."),
        }
    )


def _sentences(summary):
    return [part.strip() for part in summary.replace("!", ".").split(".") if part.strip()]


def _llm_settings():
    try:
        timeout = float(getattr(settings, "LLM_TIMEOUT_SECONDS", 30) or 30)
    except (TypeError, ValueError):
        timeout = 30.0
    return {
        "provider": str(getattr(settings, "LLM_PROVIDER", "") or "").strip().lower(),
        "model": str(getattr(settings, "LLM_MODEL", "") or "").strip(),
        "api_key": str(getattr(settings, "LLM_API_KEY", "") or "").strip(),
        "base_url": str(getattr(settings, "LLM_BASE_URL", "") or "").strip().rstrip("/"),
        "timeout": timeout,
    }


def _accepted_summary(candidate, statements):
    if not isinstance(candidate, str):
        return None
    sentences = _sentences(candidate)
    allowed = set(statements)
    if sentences and all(item in allowed for item in sentences):
        return " ".join(sentences)
    return None


def _remote_llm_summary(statements, indicators, config):
    base_url = config["base_url"]
    if not config["provider"] or not config["model"] or not base_url:
        return None
    endpoint = base_url if base_url.endswith("/chat/completions") else base_url + "/chat/completions"
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    prompt = (
        "Reorder only the verified statements below; do not add, reword, or invent claims. "
        "Return the selected statements as plain sentences separated by periods.\n"
        + "\n".join("- %s" % item for item in statements)
        + "\nIndicators: "
        + json.dumps(indicators, ensure_ascii=False, default=str)
    )
    payload = {
        "model": config["model"],
        "messages": [
            {
                "role": "system",
                "content": "Repeat only the verified statements verbatim; never invent or reword facts.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    headers = {"Content-Type": "application/json"}
    if config["api_key"]:
        headers["Authorization"] = "Bearer %s" % config["api_key"]
    connection_class = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    path = parsed.path or "/"
    if parsed.query:
        path = "%s?%s" % (path, parsed.query)
    try:
        with connection_class(parsed.hostname, parsed.port, timeout=config["timeout"]) as connection:
            connection.request("POST", path, body=json.dumps(payload).encode(), headers=headers)
            response_body = connection.getresponse().read()
        data = json.loads(response_body.decode("utf-8", "replace"))
        choices = data.get("choices") or []
        content = choices[0].get("message", {}).get("content") if choices else None
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None
    return content


def generate_explanation(media):
    statements = []
    indicators = []
    recommendations = []
    limitations = [
        "Heuristic indicators are not proof of manipulation or authenticity.",
        "A verified SHA-256 hash establishes file integrity since upload only, not authenticity.",
        "Without a trained checkpoint no prediction or confidence value is available.",
        "A single suspicious frame or audio segment does not establish that the whole file is fake.",
        "Metadata can be absent, removed, or altered without proving manipulation.",
    ]

    metadata = _record("metadata_extractor", "MetadataRecord", media)
    if metadata is not None:
        count = len(metadata.anomalies or [])
        statements.append("%s metadata anomalies were recorded." % count)
        _add(indicators, "metadata_extractor", "Metadata anomalies", count)
        if count:
            recommendations.append("Review the recorded metadata anomalies as leads for manual provenance review.")

    integrity = _record("integrity_verification", "IntegrityRecord", media)
    if integrity is not None:
        statements.append("Integrity verification status is %s." % integrity.status)
        _add(indicators, "integrity_verification", "Integrity status", integrity.status, kind="integrity")
        if integrity.status == "TAMPERED":
            recommendations.append(
                "Investigate chain of custody because the current hash differs from the recorded hash."
            )
        elif integrity.status == "UNAVAILABLE":
            recommendations.append("Obtain a readable file and recorded hash before relying on integrity verification.")

    analyses = (
        ("image_detection", "ImageAnalysis", "image"),
        ("video_detection", "VideoAnalysis", "video"),
        ("audio_detection", "AudioAnalysis", "audio"),
    )
    verdicts = []
    for app_label, model_name, label in analyses:
        analysis = _record(app_label, model_name, media)
        if analysis is None:
            statements.append("No %s analysis record is available." % label)
            continue
        verdicts.append(analysis.verdict)
        statements.append("%s model status is %s and verdict is %s." % (label, analysis.model_status, analysis.verdict))
        _add(indicators, app_label, "%s model status" % label, analysis.model_status, kind="model")
        _add(indicators, app_label, "%s verdict" % label, analysis.verdict, kind="model")
        _add(
            indicators,
            app_label,
            "%s confidence" % label,
            analysis.confidence,
            kind="model",
            note="No confidence value is available when the model is untrained.",
        )
        if analysis.model_status != "TRAINED":
            limitations.append(
                "The %s detector did not produce a verdict because no trained checkpoint was applied." % label
            )
        if label == "image":
            _add(indicators, app_label, "Face count", analysis.face_count)
            _add(indicators, app_label, "Artifact score", analysis.artifact_score)
        elif label == "video":
            times = [
                item.get("timestamp_seconds") for item in (analysis.suspicious_frames or []) if isinstance(item, dict)
            ]
            _add(indicators, app_label, "Suspicious frame timestamps", times)
            _add(indicators, app_label, "Temporal consistency", analysis.temporal_consistency)
            if times:
                recommendations.append("Manually review the flagged video timestamps before drawing conclusions.")
        elif label == "audio":
            _add(indicators, app_label, "Audio duration seconds", analysis.duration_seconds)
            _add(indicators, app_label, "Audio sample rate", analysis.sample_rate)
            _add(indicators, app_label, "Suspicious audio segments", analysis.suspicious_segments or [])
            if analysis.suspicious_segments:
                recommendations.append(
                    "Listen to the flagged audio segments and compare them with the waveform and spectrogram."
                )

    if verdicts:
        if "LIKELY_MANIPULATED" in verdicts:
            statements.append("At least one trained detector reported likely manipulation.")
            recommendations.append("Escalate the media for expert review and preserve the original evidence.")
        else:
            statements.append("No trained detector reported likely manipulation.")
    else:
        statements.append("All detection results remain inconclusive.")
        recommendations.append(
            "Install a trained checkpoint through the training pipeline before relying on a detection verdict."
        )

    summary = " ".join(statements) if statements else "No analysis fields are available for this media."
    hook = getattr(settings, "AI_EXPLANATION_LLM_HOOK", None)
    if callable(hook):
        try:
            result = hook({"summary_sentences": list(statements), "indicators": indicators})
            candidate = _accepted_summary(result.get("summary") if isinstance(result, dict) else None, statements)
            if candidate is not None:
                summary = candidate
        except Exception:
            pass
    config = _llm_settings()
    if config["provider"]:
        candidate = _accepted_summary(_remote_llm_summary(statements, indicators, config), statements)
        if candidate is not None:
            summary = candidate

    record, _ = apps.get_model("ai_explanations", "Explanation").objects.update_or_create(
        media=media,
        defaults={
            "summary": summary,
            "indicators": indicators,
            "recommendations": recommendations,
            "limitations": limitations,
            "evidence_source": "deterministic",
        },
    )
    return record
