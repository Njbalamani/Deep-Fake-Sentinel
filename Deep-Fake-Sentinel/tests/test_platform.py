import io
import json
import shutil
import wave
from pathlib import Path

import numpy as np
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import ActivityLog, Role, UserProfile
from ai_explanations.models import Explanation
from audio_detection.models import AudioAnalysis
from dashboard.models import ModelMetric
from dashboard.services import get_dashboard_metrics
from forensic_analysis.models import ForensicRecord
from image_detection.models import ImageAnalysis
from integrity_verification.models import IntegrityRecord
from investigations.models import EvidenceAccessLog, Investigation, Observation
from media_manager.models import AnalysisEvent, MediaFile, MediaStatus
from media_manager.serializers import MediaFileSerializer
from media_manager.services import compute_sha256, secure_filename, validate_upload
from metadata_extractor.models import MetadataRecord
from reports.models import ForensicReport
from reports.services import generate_report
from video_detection.models import VideoAnalysis

TEST_MEDIA_ROOT = Path(settings.BASE_DIR) / "media" / "tmp" / "test_suite"


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (18, 38, 68)).save(buffer, format="PNG")
    return buffer.getvalue()


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        samples = np.zeros(1600, dtype=np.int16)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


def mp4_bytes():
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2mp41"


class PlatformTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        TEST_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if TEST_MEDIA_ROOT.exists():
            shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(username="analyst", password="StrongPass123!")
        UserProfile.objects.create(user=self.user, role=Role.ANALYST)
        self.admin = User.objects.create_user(username="admin", password="StrongPass123!")
        UserProfile.objects.create(user=self.admin, role=Role.ADMIN)
        self.client = APIClient()

    def authenticate(self, user=None):
        user = user or self.user
        response = self.client.post(
            "/api/auth/login/", {"username": user.username, "password": "StrongPass123!"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        token = response.data.get("token") or response.data.get("key")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        return token

    def upload(self, name, content, content_type, investigation=None):
        payload = {"files": SimpleUploadedFile(name, content, content_type=content_type)}
        if investigation is not None:
            payload["investigation"] = str(investigation.pk)
        return self.client.post("/api/media/", payload, format="multipart")


@override_settings(MEDIA_ROOT=str(TEST_MEDIA_ROOT))
class AuthenticationTests(PlatformTestCase):
    def test_registration_creates_viewer_and_logs_activity(self):
        response = self.client.post(
            "/api/auth/register/",
            {"username": "newuser", "password": "StrongPass123!", "email": "new@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["role"], Role.VIEWER)
        self.assertTrue(ActivityLog.objects.filter(action="USER_REGISTERED").exists())

    def test_login_me_and_logout(self):
        token = self.authenticate()
        self.assertTrue(token)
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["username"], "analyst")
        logout = self.client.post("/api/auth/logout/")
        self.assertEqual(logout.status_code, 200)
        self.assertIn(self.client.get("/api/auth/me/").status_code, [401, 403])

    def test_admin_only_user_management(self):
        self.authenticate()
        self.assertEqual(self.client.get("/api/accounts/users/").status_code, 403)
        self.authenticate(self.admin)
        self.assertEqual(self.client.get("/api/accounts/users/").status_code, 200)


@override_settings(MEDIA_ROOT=str(TEST_MEDIA_ROOT))
class UploadValidationTests(PlatformTestCase):
    def test_secure_filename_strips_traversal(self):
        self.assertEqual(secure_filename("../../evil?.png"), "evil.png")

    def test_validate_upload_accepts_valid_png(self):
        uploaded = SimpleUploadedFile("evidence.png", png_bytes(), content_type="image/png")
        result = validate_upload(uploaded)
        self.assertEqual(result["media_type"], "IMAGE")
        self.assertEqual(len(result["sha256"]), 64)

    def test_validate_upload_rejects_unsupported_signature(self):
        uploaded = SimpleUploadedFile("evil.png", b"MZ\x90\x00not-a-png", content_type="image/png")
        with self.assertRaises(Exception):
            validate_upload(uploaded)

    def test_api_rejects_unsupported_file(self):
        self.authenticate()
        response = self.upload("malware.exe", b"MZ\x90\x00payload", "application/octet-stream")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(MediaFile.objects.count(), 0)

    def test_upload_generates_hash_and_starts_pipeline(self):
        self.authenticate()
        response = self.upload("evidence.png", png_bytes(), "image/png")
        self.assertEqual(response.status_code, 201, response.data)
        media = MediaFile.objects.get()
        self.assertEqual(media.status, MediaStatus.COMPLETED)
        self.assertEqual(len(media.sha256), 64)
        self.assertEqual(compute_sha256(media.file.path), media.sha256)
        self.assertTrue(AnalysisEvent.objects.filter(media=media).exists())


@override_settings(MEDIA_ROOT=str(TEST_MEDIA_ROOT))
class AiPipelineTests(PlatformTestCase):
    def test_image_pipeline_is_honest_without_checkpoint(self):
        self.authenticate()
        response = self.upload("face.png", png_bytes(), "image/png")
        media = MediaFile.objects.get(pk=response.data["created"][0]["id"])
        analysis = ImageAnalysis.objects.get(media=media)
        self.assertIn(analysis.model_status, ["UNTRAINED", "UNAVAILABLE"])
        self.assertEqual(analysis.verdict, "INCONCLUSIVE")
        self.assertIsNone(analysis.confidence)
        self.assertTrue(Explanation.objects.filter(media=media).exists())

    def test_video_pipeline_records_sampled_frames_and_timeline(self):
        self.authenticate()
        response = self.upload("clip.mp4", mp4_bytes(), "video/mp4")
        media = MediaFile.objects.get(pk=response.data["created"][0]["id"])
        analysis = VideoAnalysis.objects.get(media=media)
        self.assertEqual(media.media_type, "VIDEO")
        self.assertEqual(analysis.verdict, "INCONCLUSIVE")
        self.assertIsNone(analysis.confidence)
        self.assertIsInstance(analysis.suspicious_frames, list)

    def test_audio_pipeline_generates_visualizations(self):
        self.authenticate()
        response = self.upload("voice.wav", wav_bytes(), "audio/wav")
        media = MediaFile.objects.get(pk=response.data["created"][0]["id"])
        analysis = AudioAnalysis.objects.get(media=media)
        self.assertEqual(media.media_type, "AUDIO")
        self.assertEqual(analysis.verdict, "INCONCLUSIVE")
        self.assertIsNone(analysis.confidence)
        self.assertTrue(analysis.waveform_path)
        self.assertTrue(analysis.spectrogram_path)

    def test_detection_api_endpoints(self):
        self.authenticate()
        image = self.upload("still.png", png_bytes(), "image/png")
        audio = self.upload("sample.wav", wav_bytes(), "audio/wav")
        video = self.upload("sample.mp4", mp4_bytes(), "video/mp4")
        for media_id in [
            image.data["created"][0]["id"],
            audio.data["created"][0]["id"],
            video.data["created"][0]["id"],
        ]:
            status = self.client.get(f"/api/media/{media_id}/status/")
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.data["status"], MediaStatus.COMPLETED)


@override_settings(MEDIA_ROOT=str(TEST_MEDIA_ROOT))
class ForensicIntegrityReportTests(PlatformTestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()
        response = self.upload("report.png", png_bytes(), "image/png")
        self.media = MediaFile.objects.get(pk=response.data["created"][0]["id"])

    def test_metadata_and_forensics_are_separate_from_manipulation(self):
        metadata = MetadataRecord.objects.get(media=self.media)
        forensics = ForensicRecord.objects.get(media=self.media)
        self.assertTrue(all("not proof" in str(item.get("label", "")).lower() for item in (metadata.anomalies or [])))
        self.assertIn(forensics.risk_level, ["INFO", "LOW", "MEDIUM", "HIGH"])
        self.assertNotIn("CONFIRMED_MANIPULATION", forensics.risk_level)

    def test_integrity_verification(self):
        integrity = IntegrityRecord.objects.get(media=self.media)
        self.assertEqual(integrity.status, "VERIFIED")
        self.assertEqual(integrity.original_hash, self.media.sha256)

    def test_investigation_access_history_and_observations(self):
        case = Investigation.objects.create(title="Case 001", created_by=self.user, assigned_to=self.user)
        case.media.add(self.media)
        self.media.investigation = case
        self.media.save(update_fields=["investigation", "updated_at"])
        self.client.post(f"/api/investigations/{case.pk}/observations/", {"note": "Reviewed file hash."}, format="json")
        self.assertTrue(Observation.objects.filter(investigation=case).exists())
        self.client.get(f"/api/media/{self.media.pk}/")
        self.assertTrue(EvidenceAccessLog.objects.filter(media=self.media).exists())

    def test_pdf_report_generation(self):
        report = generate_report(self.media, self.user)
        self.assertTrue(report.pdf.path)
        with open(report.pdf.path, "rb") as handle:
            self.assertEqual(handle.read(4), b"%PDF")
        response = self.client.post(f"/api/reports/generate/{self.media.pk}/")
        self.assertIn(response.status_code, [200, 201], response.data)
        self.assertTrue(ForensicReport.objects.filter(media=self.media).count() >= 2)

    def test_dashboard_uses_database_values(self):
        metrics = get_dashboard_metrics(self.user)
        self.assertEqual(metrics["total_media"], 1)
        self.assertEqual(metrics["media_counts"]["IMAGE"], 1)
        self.assertEqual(metrics["potentially_manipulated"], 0)
        response = self.client.get("/api/analytics/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_media"], 1)
        for key in ("analyses", "open_cases", "reports"):
            self.assertIn(key, response.data)
        self.assertGreaterEqual(response.data["analyses"], 1)

    def test_metadata_api_does_not_expose_server_root(self):
        response = self.client.get(f"/api/metadata/{self.media.pk}/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn(str(settings.MEDIA_ROOT), str(response.data["raw"]))


@override_settings(MEDIA_ROOT=str(TEST_MEDIA_ROOT))
class MigrationAndQualityTests(TestCase):
    def test_no_missing_migrations(self):
        call_command("makemigrations", check=True, dry_run=True, verbosity=0)

    def test_import_model_metrics_accepts_generated_dict_shape(self):
        TEST_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
        payload = {
            "modality": "image",
            "checkpoint": "image_detector.pt",
            "status": "ok",
            "metrics": {"accuracy": 0.75, "precision": 0.8, "recall": 0.7, "f1": 0.74, "support": 40},
        }
        path = TEST_MEDIA_ROOT / "metrics.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            call_command("import_model_metrics", str(path), verbosity=0)
        finally:
            path.unlink(missing_ok=True)
        metric = ModelMetric.objects.filter(model_name="image_detector").first()
        self.assertIsNotNone(metric)
        self.assertEqual(metric.accuracy, 0.75)

    def test_zip_import_is_not_executed_as_media(self):
        uploaded = SimpleUploadedFile("archive.zip", b"PK\x03\x04not-media", content_type="application/zip")
        with self.assertRaises(Exception):
            validate_upload(uploaded)

    def test_landing_page_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DEEPFAKE SENTINEL")

    def test_dashboard_page_renders(self):
        user = User.objects.create_user(username="workspace-user", password="StrongPass123!")
        self.client.force_login(user)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "upload")


@override_settings(MEDIA_ROOT=str(TEST_MEDIA_ROOT))
class AuthorizationRegressionTests(PlatformTestCase):
    def setUp(self):
        super().setUp()
        self.outsider = User.objects.create_user(username="outsider", password="StrongPass123!")
        UserProfile.objects.create(user=self.outsider, role=Role.VIEWER)

    def test_non_owner_cannot_read_or_generate_another_users_analysis(self):
        self.authenticate()
        upload = self.upload("private.png", png_bytes(), "image/png")
        media_id = upload.data["created"][0]["id"]
        self.assertTrue(ImageAnalysis.objects.filter(media_id=media_id).exists())
        ForensicRecord.objects.filter(media_id=media_id).delete()

        self.authenticate(self.outsider)
        for path in (
            f"/api/analyses/image/{media_id}/",
            f"/api/forensics/{media_id}/",
            f"/api/media/{media_id}/",
        ):
            response = self.client.get(path)
            self.assertIn(response.status_code, (403, 404), (path, response.data))
        self.assertFalse(ForensicRecord.objects.filter(media_id=media_id).exists())

        self.authenticate()
        response = self.client.get(f"/api/forensics/{media_id}/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(ForensicRecord.objects.filter(media_id=media_id).exists())

    def test_workspace_pages_require_login_and_investigations_are_scoped(self):
        for path in ("/dashboard/", "/media/", "/reports/", "/investigations/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertTrue(response.url.startswith("/accounts/login/"), response.url)

        case = Investigation.objects.create(title="Private case", created_by=self.user, assigned_to=self.user)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get("/dashboard/").status_code, 200)
        response = self.client.get(f"/investigations/{case.pk}/")
        self.assertIn(response.status_code, (403, 404), response.status_code)

        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f"/investigations/{case.pk}/").status_code, 200)

    def test_media_api_exposes_only_protected_download_url(self):
        self.authenticate()
        upload = self.upload("evidence.png", png_bytes(), "image/png")
        media_id = upload.data["created"][0]["id"]

        detail = self.client.get(f"/api/media/{media_id}/")
        self.assertEqual(detail.status_code, 200, detail.data)
        for payload in (detail.data, self.client.get("/api/media/").data["results"][0]):
            self.assertIn("download_url", payload)
            self.assertNotIn("file", payload)
            self.assertNotIn("file_url", payload)
        self.assertEqual(detail.data["download_url"], f"http://testserver/api/media/{media_id}/download/")

        media = MediaFile.objects.get(pk=media_id)
        self.assertEqual(MediaFileSerializer(media).data["download_url"], f"/api/media/{media_id}/download/")

    def test_dashboard_metrics_are_scoped_to_current_user(self):
        self.authenticate()
        upload = self.upload("private-metrics.png", png_bytes(), "image/png")
        media_id = upload.data["created"][0]["id"]
        self.assertEqual(get_dashboard_metrics(self.user)["total_media"], 1)
        self.assertEqual(get_dashboard_metrics(self.outsider)["total_media"], 0)

        self.authenticate(self.outsider)
        response = self.client.get("/api/analytics/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_media"], 0)
        self.assertNotIn(media_id, str(response.data["detection_history"]))

        self.authenticate()
        response = self.client.get("/api/analytics/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_media"], 1)

    def test_investigation_form_aliases_and_detail_panels(self):
        self.authenticate()
        response = self.client.post(
            "/api/investigations/",
            {"title": "Alias case", "assignee": "analyst", "priority": "high"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["assigned_to"], self.user.pk)
        self.assertEqual(response.data["priority"], "HIGH")

        detail = self.client.get(f"/api/investigations/{response.data['id']}/")
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertIsInstance(detail.data["observations"], list)
        self.assertIsInstance(detail.data["access_history"], list)

    def test_investigation_cannot_link_unauthorized_media(self):
        self.authenticate(self.outsider)
        upload = self.upload("outsider.png", png_bytes(), "image/png")
        outsider_media_id = upload.data["created"][0]["id"]

        self.authenticate()
        response = self.client.post(
            "/api/investigations/",
            {"title": "Bad link", "media": [outsider_media_id]},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Investigation.objects.filter(title="Bad link").exists())
