import hashlib
import json
import os
import re
import uuid
from io import BytesIO
from xml.sax.saxutils import escape as xml_escape

from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ai_explanations.services import generate_explanation
from forensic_analysis.services import analyze_forensics
from integrity_verification.services import verify_integrity
from metadata_extractor.services import extract_metadata

from .models import ForensicReport

METHODOLOGY = (
    "Metadata was read from the stored file with Pillow, OpenCV, soundfile, mutagen, and filesystem statistics; "
    "filesystem timestamps are identified separately from embedded metadata.",
    "Integrity was evaluated by recomputing SHA-256 and comparing it with the recorded MediaFile.sha256 value.",
    "Detection verdicts and confidence values are used only from a trained checkpoint present in the configured weights directory.",
    "Heuristic indicators such as compression differences, face counts, flagged frame timestamps, and audio energy outliers "
    "are deterministic observations and are not authenticity proof.",
    "Explanations were assembled only from stored analysis fields; optional language-model hooks cannot change verdicts, "
    "confidence values, or evidence.",
)


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


REDACTED = "redacted"


def _redact_paths(value):
    if isinstance(value, dict):
        return {key: _redact_paths(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_paths(item) for item in value]
    if isinstance(value, str):
        text = value
        media_root = str(getattr(settings, "MEDIA_ROOT", "") or "")
        if media_root:
            text = text.replace(media_root, REDACTED)
        text = re.sub(r"[A-Za-z]:\\[^\s'\"<>|]+", REDACTED, text)
        text = re.sub(r"[A-Za-z]:/[^\s'\"<>|]+", REDACTED, text)
        text = re.sub(r"\\\\[^\s'\"<>|]+", REDACTED, text)
        if os.path.isabs(text) or (len(text) > 1 and text[1] == ":" and text[0].isalpha()):
            return REDACTED
        return text
    return value


def _text(value):
    value = _redact_paths(value)
    if value is None or value == "":
        return "not available"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _investigation(media):
    try:
        investigation = media.investigation
        if investigation is not None:
            return investigation
    except Exception:
        pass
    try:
        manager = getattr(media, "investigation_set", None)
        if manager is not None:
            return manager.first()
    except Exception:
        pass
    try:
        model = apps.get_model("investigations", "Investigation")
        return model.objects.filter(media=media).first()
    except Exception:
        return None


def _field(obj, names, default="not available"):
    for name in names:
        value = getattr(obj, name, None)
        if value is not None and value != "":
            return value
    return default


def _confidence_row(label, analysis):
    value = getattr(analysis, "confidence", None) if analysis is not None else None
    return (label, "not available" if value is None else value)


def _build_sections(media, investigation, metadata, integrity, forensics, explanation):
    sections = []

    media_rows = [
        ("Investigation ID", str(investigation.pk) if investigation is not None else "not available"),
        (
            "Investigation reference",
            _field(investigation, ("title", "name", "reference")) if investigation is not None else "not available",
        ),
        ("Investigation status", _field(investigation, ("status",)) if investigation is not None else "not available"),
        ("Media ID", str(media.pk)),
        ("Media name", _field(media, ("original_name", "file"))),
        ("Media type", _field(media, ("media_type",))),
        ("MIME type", _field(media, ("mime_type",))),
        ("Size (bytes)", _field(media, ("size_bytes",))),
        ("Recorded SHA-256", _field(media, ("sha256",))),
    ]
    sections.append(("Investigation and media", media_rows))

    metadata_rows = []
    if metadata is not None:
        metadata_rows = [
            ("Raw metadata", metadata.raw),
            ("EXIF and container tags", metadata.exif),
            ("Technical properties", metadata.technical),
            ("Metadata anomalies", metadata.anomalies),
        ]
    else:
        metadata_rows = [("Raw metadata", "not available")]
    sections.append(("Metadata", metadata_rows))

    integrity_rows = [
        ("Integrity status", integrity.status if integrity is not None else "not available"),
        ("Original hash", integrity.original_hash if integrity is not None else "not available"),
        ("Current hash", integrity.current_hash if integrity is not None else "not available"),
        ("Integrity note", "A matching hash shows file integrity, not authenticity."),
    ]
    sections.append(("Integrity verification", integrity_rows))

    image = _record("image_detection", "ImageAnalysis", media)
    video = _record("video_detection", "VideoAnalysis", media)
    audio = _record("audio_detection", "AudioAnalysis", media)

    detection_rows = []
    if image is not None:
        detection_rows.extend(
            [
                ("Image model status", image.model_status),
                ("Image model version", image.model_version),
                ("Image verdict", image.verdict),
                _confidence_row("Image confidence", image),
                ("Image artifact score (heuristic)", image.artifact_score),
                ("Image face count (heuristic)", image.face_count),
                ("Image indicators", image.indicators),
            ]
        )
    else:
        detection_rows.append(("Image analysis", "not available"))
    if video is not None:
        detection_rows.extend(
            [
                ("Video model status", video.model_status),
                ("Video model version", video.model_version),
                ("Video verdict", video.verdict),
                _confidence_row("Video confidence", video),
                ("Video frame count", video.frame_count),
                ("Video sampled frames", video.sampled_frames),
                (
                    "Suspicious frame timestamps (heuristic)",
                    [
                        item.get("timestamp_seconds")
                        for item in (video.suspicious_frames or [])
                        if isinstance(item, dict)
                    ],
                ),
                ("Video temporal consistency (heuristic)", video.temporal_consistency),
                ("Video indicators", video.indicators),
            ]
        )
    else:
        detection_rows.append(("Video analysis", "not available"))
    if audio is not None:
        detection_rows.extend(
            [
                ("Audio model status", audio.model_status),
                ("Audio model version", audio.model_version),
                ("Audio verdict", audio.verdict),
                _confidence_row("Audio confidence", audio),
                ("Audio duration seconds", audio.duration_seconds),
                ("Audio sample rate", audio.sample_rate),
                ("Audio waveform", audio.waveform_path),
                ("Audio spectrogram", audio.spectrogram_path),
                ("Audio features", audio.features),
                ("Suspicious audio segments (heuristic)", audio.suspicious_segments or []),
                ("Audio indicators", audio.indicators),
            ]
        )
    else:
        detection_rows.append(("Audio analysis", "not available"))
    sections.append(("Detection results", detection_rows))

    observation_rows = [
        ("Risk level", forensics.risk_level if forensics is not None else "not available"),
        ("Forensic summary", forensics.summary if forensics is not None else "not available"),
        ("Forensic anomalies", forensics.anomalies if forensics is not None else []),
        ("Forensic evidence", forensics.evidence if forensics is not None else []),
    ]
    sections.append(("Observations", observation_rows))

    sections.append(("Methodology", [("Method %d" % index, text) for index, text in enumerate(METHODOLOGY, start=1)]))
    sections.append(
        (
            "Limitations",
            [("Limitation %d" % index, text) for index, text in enumerate(explanation.limitations or [], start=1)],
        )
    )
    sections.append(
        (
            "Recommendations",
            [
                ("Recommendation %d" % index, text)
                for index, text in enumerate(explanation.recommendations or [], start=1)
            ],
        )
    )
    return sections


def build_report_pdf(report_id, sections, generated_by=None):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title="DEEPFAKE SENTINEL Forensic Report %s" % report_id,
        author="DEEPFAKE SENTINEL",
        leftMargin=45,
        rightMargin=45,
        topMargin=45,
        bottomMargin=45,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=18, alignment=TA_LEFT)
    heading_style = ParagraphStyle(
        "ReportHeading", parent=styles["Heading2"], textColor=colors.HexColor("#14375e"), fontSize=12
    )
    key_style = ParagraphStyle("ReportKey", parent=styles["BodyText"], fontSize=8, leading=10)
    value_style = ParagraphStyle("ReportValue", parent=styles["BodyText"], fontSize=8, leading=10)

    story = [
        Paragraph("DEEPFAKE SENTINEL Forensic Report", title_style),
        Paragraph("Report ID: %s" % xml_escape(report_id), styles["Normal"]),
        Paragraph("Generated by: %s" % xml_escape(str(generated_by or "not available")), styles["Normal"]),
        Spacer(1, 12),
    ]

    for heading, rows in sections:
        story.append(Paragraph(xml_escape(heading), heading_style))
        table_data = []
        for key, value in rows:
            left = Paragraph(xml_escape(_text(key)), key_style)
            right = Paragraph(xml_escape(_text(value)).replace("\n", "<br/>"), value_style)
            table_data.append([left, right])
        table = Table(table_data, colWidths=[150, 360])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f8")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c6d4")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 10))

    document.build(story)
    return buffer.getvalue()


def generate_report(media, user):
    metadata = extract_metadata(media)
    integrity = verify_integrity(media)
    forensics = analyze_forensics(media)
    explanation = generate_explanation(media)
    investigation = _investigation(media)

    while True:
        report_id = "DFS-%s" % uuid.uuid4().hex[:16].upper()
        if not ForensicReport.objects.filter(report_id=report_id).exists():
            break

    version = str(ForensicReport.objects.filter(media=media).count() + 1)
    sections = _build_sections(media, investigation, metadata, integrity, forensics, explanation)
    pdf_bytes = build_report_pdf(report_id, sections, generated_by=user)
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    previous_chain = ForensicReport.objects.order_by("-created_at").values_list("hash_chain", flat=True).first()
    hash_chain = hashlib.sha256(f"{previous_chain or ''}{digest}".encode()).hexdigest()

    report = ForensicReport(
        report_id=report_id,
        media=media,
        investigation=investigation,
        generated_by=user if getattr(user, "pk", None) is not None else None,
        version=version,
        sha256=digest,
        hash_chain=hash_chain,
    )
    report.pdf.save("%s.pdf" % report_id, ContentFile(pdf_bytes), save=True)
    return report
