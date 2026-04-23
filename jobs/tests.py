from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from openpyxl import Workbook
from reportlab.pdfgen import canvas

from editor.models import DocumentTemplate, TemplateField
from editor.services import update_template_pdf_metadata
from fonts.models import FontAsset

from .models import GenerationJob
from .services import process_job


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="sistema_vetorial_jobs_tests_")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class JobServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="jobs-user", password="senha123")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def _build_pdf_upload(self, filename: str = "background.pdf", pages: int = 1) -> SimpleUploadedFile:
        temp_dir = Path(tempfile.mkdtemp(prefix="jobs-pdf-"))
        pdf_path = temp_dir / filename
        pdf_canvas = canvas.Canvas(str(pdf_path), pagesize=(320, 220))
        for page_number in range(1, pages + 1):
            pdf_canvas.drawString(24, 200, f"Pagina {page_number}")
            pdf_canvas.showPage()
        pdf_canvas.save()
        content = pdf_path.read_bytes()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return SimpleUploadedFile(filename, content, content_type="application/pdf")

    def _build_excel_upload(self, filename: str = "dados.xlsx") -> SimpleUploadedFile:
        temp_dir = Path(tempfile.mkdtemp(prefix="jobs-xlsx-"))
        xlsx_path = temp_dir / filename
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["nome", "empresa"])
        sheet.append(["Ana", "Empresa A"])
        sheet.append(["Bruno", "Empresa B"])
        sheet.append(["Carla", "Empresa C"])
        sheet.append(["Daniel", "Empresa D"])
        workbook.save(xlsx_path)
        content = xlsx_path.read_bytes()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return SimpleUploadedFile(
            filename,
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def _build_font(self) -> FontAsset:
        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        return FontAsset.objects.create(
            user=self.user,
            name="DejaVu Sans",
            family="DejaVu Sans",
            variant=FontAsset.Variant.REGULAR,
            file=SimpleUploadedFile("DejaVuSans.ttf", font_path.read_bytes(), content_type="font/ttf"),
        )

    def _build_template(self, pages: int = 1) -> DocumentTemplate:
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Template Jobs",
            slug=f"template-jobs-{pages}",
            background_pdf=self._build_pdf_upload(pages=pages),
            status=DocumentTemplate.Status.READY,
        )
        update_template_pdf_metadata(template)
        return template

    def test_process_preview_job_uses_first_three_valid_rows(self):
        font = self._build_font()
        template = self._build_template()
        TemplateField.objects.create(
            template=template,
            name="nome",
            label="Nome",
            excel_column="nome",
            order_index=1,
            page_number=1,
            x=30,
            y=170,
            width=180,
            height=20,
            font=font,
            font_size=14,
        )
        job = GenerationJob.objects.create(
            user=self.user,
            template=template,
            name="Preview Job",
            kind=GenerationJob.Kind.PREVIEW,
            source_excel=self._build_excel_upload(),
            status=GenerationJob.Status.QUEUED,
        )

        process_job(job)
        job.refresh_from_db()

        self.assertEqual(job.status, GenerationJob.Status.COMPLETED)
        self.assertEqual(job.total_rows, 3)
        self.assertEqual(job.success_rows, 3)
        self.assertEqual(job.items.count(), 3)
        self.assertFalse(bool(job.zip_file))

    def test_process_full_job_creates_zip(self):
        font = self._build_font()
        template = self._build_template(pages=2)
        TemplateField.objects.create(
            template=template,
            name="nome_p1",
            label="Nome P1",
            excel_column="nome",
            order_index=1,
            page_number=1,
            x=30,
            y=170,
            width=180,
            height=20,
            font=font,
            font_size=14,
        )
        TemplateField.objects.create(
            template=template,
            name="nome_p2",
            label="Nome P2",
            excel_column="nome",
            order_index=2,
            page_number=2,
            x=30,
            y=170,
            width=180,
            height=20,
            font=font,
            font_size=14,
        )
        job = GenerationJob.objects.create(
            user=self.user,
            template=template,
            name="Full Job",
            kind=GenerationJob.Kind.FULL,
            source_excel=self._build_excel_upload(),
            status=GenerationJob.Status.QUEUED,
        )

        process_job(job)
        job.refresh_from_db()

        self.assertEqual(job.status, GenerationJob.Status.COMPLETED)
        self.assertEqual(job.total_rows, 4)
        self.assertEqual(job.success_rows, 4)
        self.assertTrue(bool(job.zip_file))
        self.assertEqual(job.items.count(), 4)
