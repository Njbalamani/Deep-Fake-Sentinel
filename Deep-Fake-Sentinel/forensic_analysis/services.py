from django.apps import apps

HEURISTIC_NOTE = "Heuristic evidence only; not authenticity proof."
INTEGRITY_NOTE = "Hash verification shows file integrity, not authenticity."


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


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def analyze_forensics(media):
    metadata = _record("metadata_extractor", "MetadataRecord", media)
    integrity = _record("integrity_verification", "IntegrityRecord", media)
    analyses = [
        ("image_detection", "ImageAnalysis", "IMAGE"),
        ("video_detection", "VideoAnalysis", "VIDEO"),
        ("audio_detection", "AudioAnalysis", "AUDIO"),
    ]

    anomalies = []
    evidence = []
    verdicts = []
    statements = []

    if metadata is not None:
        for item in metadata.anomalies or []:
            entry = dict(item) if isinstance(item, dict) else {"detail": str(item), "severity": "INFO"}
            anomalies.append({"source": "metadata_extractor", **entry})
        evidence.append(
            {
                "source": "metadata_extractor",
                "kind": "metadata",
                "label": "Metadata anomaly count",
                "value": len(metadata.anomalies or []),
                "note": "Metadata anomalies are separate from confirmed manipulation.",
            }
        )
        statements.append("%s metadata anomalies recorded." % len(metadata.anomalies or []))
    else:
        statements.append("No metadata record is available.")

    if integrity is not None:
        evidence.append(
            {
                "source": "integrity_verification",
                "kind": "integrity",
                "label": "SHA-256 comparison",
                "value": integrity.status,
                "note": INTEGRITY_NOTE,
            }
        )
        statements.append("Integrity status is %s." % integrity.status)
        if integrity.status == "TAMPERED":
            anomalies.append(
                {
                    "source": "integrity_verification",
                    "severity": "MEDIUM",
                    "code": "hash_mismatch",
                    "detail": "Current SHA-256 differs from the recorded SHA-256.",
                    "note": INTEGRITY_NOTE,
                }
            )
    else:
        statements.append("No integrity record is available.")

    for app_label, model_name, media_type in analyses:
        analysis = _record(app_label, model_name, media)
        if analysis is None:
            statements.append("No %s analysis record is available." % media_type)
            continue
        verdicts.append(analysis.verdict)
        confidence = _safe_float(analysis.confidence)
        evidence.append(
            {
                "source": app_label,
                "kind": "model" if analysis.model_status == "TRAINED" else "unavailable",
                "label": "%s verdict" % media_type,
                "value": analysis.verdict,
                "confidence": confidence,
                "model_status": analysis.model_status,
                "note": "No prediction was produced without a trained checkpoint."
                if analysis.model_status != "TRAINED"
                else None,
            }
        )
        statements.append(
            "%s analysis verdict is %s with model status %s." % (media_type, analysis.verdict, analysis.model_status)
        )
        for item in analysis.indicators or []:
            if isinstance(item, dict) and item.get("severity") in ("LOW", "MEDIUM", "HIGH"):
                anomalies.append(
                    {
                        "source": app_label,
                        "severity": item.get("severity"),
                        "code": item.get("code"),
                        "detail": item.get("detail"),
                        "note": HEURISTIC_NOTE,
                    }
                )
        if media_type == "IMAGE":
            evidence.append(
                {
                    "source": app_label,
                    "kind": "heuristic",
                    "label": "Image artifact score",
                    "value": _safe_float(analysis.artifact_score),
                    "note": HEURISTIC_NOTE,
                }
            )
            evidence.append(
                {
                    "source": app_label,
                    "kind": "heuristic",
                    "label": "Detected faces",
                    "value": analysis.face_count,
                    "note": "Face count is not an authenticity signal.",
                }
            )
        elif media_type == "VIDEO":
            suspicious = analysis.suspicious_frames or []
            evidence.append(
                {
                    "source": app_label,
                    "kind": "heuristic",
                    "label": "Suspicious frame timestamps",
                    "value": [item.get("timestamp_seconds") for item in suspicious if isinstance(item, dict)],
                    "note": "A single flagged frame does not establish that the video is fake.",
                }
            )
            evidence.append(
                {
                    "source": app_label,
                    "kind": "heuristic",
                    "label": "Temporal consistency",
                    "value": _safe_float(analysis.temporal_consistency),
                    "note": HEURISTIC_NOTE,
                }
            )
        elif media_type == "AUDIO":
            evidence.append(
                {
                    "source": app_label,
                    "kind": "heuristic",
                    "label": "Audio suspicious segments",
                    "value": analysis.suspicious_segments or [],
                    "note": HEURISTIC_NOTE,
                }
            )
            evidence.append(
                {
                    "source": app_label,
                    "kind": "heuristic",
                    "label": "Audio duration and sample rate",
                    "value": {
                        "duration_seconds": _safe_float(analysis.duration_seconds),
                        "sample_rate": analysis.sample_rate,
                    },
                    "note": "Signal measurements are not authenticity proof.",
                }
            )

    if "LIKELY_MANIPULATED" in verdicts:
        risk_level = "HIGH"
    elif integrity is not None and integrity.status == "TAMPERED":
        risk_level = "MEDIUM"
    elif "LIKELY_AUTHENTIC" in verdicts or any(item.get("severity") in ("LOW", "MEDIUM", "HIGH") for item in anomalies):
        risk_level = "LOW"
    else:
        risk_level = "INFO"

    if not verdicts:
        statements.append("No trained verdict is available; the overall result remains inconclusive.")
    elif "LIKELY_MANIPULATED" in verdicts:
        statements.append("At least one trained model returned a likely manipulated verdict.")
    else:
        statements.append("No trained model returned a likely manipulated verdict.")

    summary = " ".join(statements)
    record, _ = apps.get_model("forensic_analysis", "ForensicRecord").objects.update_or_create(
        media=media,
        defaults={
            "summary": summary,
            "anomalies": anomalies,
            "evidence": evidence,
            "risk_level": risk_level,
        },
    )
    return record
