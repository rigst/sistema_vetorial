from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook
from reportlab.pdfgen import canvas

from core.cleanup import cleanup_expired_records
from core.storage import PrivateMediaStorage
from editor.models import DocumentTemplate
from editor.services import update_template_pdf_metadata
from fonts.models import FontAsset
from jobs.models import GenerationJob


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="sistema_vetorial_core_tests_")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class AuthFlowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def test_login_required_redirects_home(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_password_reset_form_renders(self):
        user = get_user_model().objects.create_user(
            username="auth-user",
            email="auth@example.com",
            password="senha123",
        )
        response = self.client.get(reverse("password_reset"))
        self.assertEqual(response.status_code, 200)

    def _build_pdf_upload(self, filename: str = "background.pdf") -> SimpleUploadedFile:
        temp_dir = Path(tempfile.mkdtemp(prefix="core-pdf-"))
        pdf_path = temp_dir / filename
        pdf_canvas = canvas.Canvas(str(pdf_path), pagesize=(300, 200))
        pdf_canvas.drawString(24, 180, "Pagina 1")
        pdf_canvas.showPage()
        pdf_canvas.save()
        content = pdf_path.read_bytes()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return SimpleUploadedFile(filename, content, content_type="application/pdf")

    def _build_excel_upload(self, filename: str = "dados.xlsx") -> SimpleUploadedFile:
        temp_dir = Path(tempfile.mkdtemp(prefix="core-xlsx-"))
        xlsx_path = temp_dir / filename
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["nome"])
        sheet.append(["Ana"])
        workbook.save(xlsx_path)
        content = xlsx_path.read_bytes()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return SimpleUploadedFile(
            filename,
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_cleanup_expired_records_removes_old_files_and_keeps_recent_ones(self):
        user = get_user_model().objects.create_user(username="cleanup-user", password="senha123")
        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

        old_font = FontAsset.objects.create(
            user=user,
            name="Fonte Antiga",
            family="DejaVu Sans",
            variant=FontAsset.Variant.REGULAR,
            file=SimpleUploadedFile("DejaVuSans.ttf", font_path.read_bytes(), content_type="font/ttf"),
        )
        old_template = DocumentTemplate.objects.create(
            user=user,
            name="Template Antigo",
            slug="template-antigo",
            background_pdf=self._build_pdf_upload(),
        )
        update_template_pdf_metadata(old_template)
        old_job = GenerationJob.objects.create(
            user=user,
            template=old_template,
            name="Job Antigo",
            source_excel=self._build_excel_upload(),
            status=GenerationJob.Status.COMPLETED,
        )

        recent_template = DocumentTemplate.objects.create(
            user=user,
            name="Template Recente",
            slug="template-recente",
            background_pdf=self._build_pdf_upload("recent.pdf"),
        )
        update_template_pdf_metadata(recent_template)

        old_font_path = Path(old_font.file.path)
        old_template_pdf = Path(old_template.background_pdf.path)
        old_template_preview = Path(old_template.preview_image.path)
        old_job_excel = Path(old_job.source_excel.path)
        recent_template_pdf = Path(recent_template.background_pdf.path)

        old_timestamp = timezone.now() - timezone.timedelta(days=8)
        FontAsset.objects.filter(pk=old_font.pk).update(created_at=old_timestamp)
        DocumentTemplate.objects.filter(pk=old_template.pk).update(created_at=old_timestamp)
        GenerationJob.objects.filter(pk=old_job.pk).update(created_at=old_timestamp)

        result = cleanup_expired_records(retention_days=7)

        self.assertEqual(result["deleted_jobs"], 1)
        self.assertEqual(result["deleted_templates"], 1)
        self.assertEqual(result["deleted_fonts"], 1)
        self.assertFalse(FontAsset.objects.filter(pk=old_font.pk).exists())
        self.assertFalse(DocumentTemplate.objects.filter(pk=old_template.pk).exists())
        self.assertFalse(GenerationJob.objects.filter(pk=old_job.pk).exists())
        self.assertFalse(old_font_path.exists())
        self.assertFalse(old_template_pdf.exists())
        self.assertFalse(old_template_preview.exists())
        self.assertFalse(old_job_excel.exists())
        self.assertTrue(DocumentTemplate.objects.filter(pk=recent_template.pk).exists())
        self.assertTrue(recent_template_pdf.exists())

    def test_private_storage_has_no_public_url(self):
        storage = PrivateMediaStorage(location=TEST_MEDIA_ROOT)
        with self.assertRaises(ValueError):
            storage.url("arquivo.pdf")
