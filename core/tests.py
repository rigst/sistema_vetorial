from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from reportlab.pdfgen import canvas

from core.auth import ensure_default_fonts
from core.cleanup import cleanup_expired_records
from core.models import UserProfile
from core.storage import PrivateMediaStorage
from editor.models import DocumentTemplate
from editor.services import update_template_pdf_metadata
from fonts.models import FontAsset
from jobs.models import GenerationJob


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="sistema_vetorial_core_tests_")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class CoreTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def _build_pdf_upload(self, filename: str = "background.pdf") -> SimpleUploadedFile:
        temp_dir = Path(tempfile.mkdtemp(prefix="core-pdf-"))
        pdf_path = temp_dir / filename
        pdf_canvas = canvas.Canvas(str(pdf_path), pagesize=(400, 120))
        pdf_canvas.drawString(24, 100, "Pagina 1")
        pdf_canvas.showPage()
        pdf_canvas.save()
        content = pdf_path.read_bytes()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return SimpleUploadedFile(filename, content, content_type="application/pdf")

    def test_login_required_redirects_home(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_visitor_login_and_logout_cleanup(self):
        response = self.client.post(reverse("login"), {"entrar_visitante": "1"}, follow=True)
        self.assertEqual(response.status_code, 200)
        user = get_user_model().objects.get(username__startswith="visitante_")
        self.assertEqual(user.profile.role, UserProfile.Role.VISITOR)

        response = self.client.post(reverse("logout"), follow=True)
        self.assertContains(response, "dados temporários")
        self.assertFalse(get_user_model().objects.filter(pk=user.pk).exists())

    def test_ensure_default_fonts_creates_builtin_fonts(self):
        user = get_user_model().objects.create_user(username="font-user", password="senha123")
        ensure_default_fonts(user)
        self.assertGreaterEqual(FontAsset.objects.filter(user=user, is_builtin=True).count(), 1)

    def test_cleanup_expired_records_removes_old_files(self):
        user = get_user_model().objects.create_user(username="cleanup-user", password="senha123")
        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        font = FontAsset.objects.create(
            user=user,
            name="Fonte",
            family="Fonte",
            variant=FontAsset.Variant.REGULAR,
            file=SimpleUploadedFile("DejaVuSans.ttf", font_path.read_bytes(), content_type="font/ttf"),
        )
        template = DocumentTemplate.objects.create(
            user=user,
            name="Template",
            slug="template",
            background_pdf=self._build_pdf_upload(),
        )
        update_template_pdf_metadata(template)
        job = GenerationJob.objects.create(
            user=user,
            template=template,
            name="Job",
            source_excel=SimpleUploadedFile("dados.xlsx", b"fake", content_type="application/octet-stream"),
        )
        old_timestamp = timezone.now() - timezone.timedelta(days=10)
        FontAsset.objects.filter(pk=font.pk).update(created_at=old_timestamp)
        DocumentTemplate.objects.filter(pk=template.pk).update(created_at=old_timestamp)
        GenerationJob.objects.filter(pk=job.pk).update(created_at=old_timestamp)

        result = cleanup_expired_records(retention_days=7)

        self.assertEqual(result["deleted_jobs"], 1)
        self.assertEqual(result["deleted_templates"], 1)
        self.assertEqual(result["deleted_fonts"], 1)

    def test_private_storage_has_no_public_url(self):
        storage = PrivateMediaStorage(location=TEST_MEDIA_ROOT)
        with self.assertRaises(ValueError):
            storage.url("arquivo.pdf")
