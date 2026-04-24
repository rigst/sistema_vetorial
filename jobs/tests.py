from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook
from reportlab.pdfgen import canvas

from editor.models import DocumentTemplate, TemplateField
from editor.services import update_template_pdf_metadata
from fonts.models import FontAsset

from .forms import GenerationJobForm
from .models import GenerationJob
from .services import format_field_value, process_job


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="sistema_vetorial_jobs_tests_")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class JobTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="jobs-user", password="senha123")
        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        cls.font = FontAsset.objects.create(
            user=cls.user,
            name="Dejavu Sans",
            family="Dejavu Sans",
            variant=FontAsset.Variant.REGULAR,
            file=SimpleUploadedFile("DejaVuSans.ttf", font_path.read_bytes(), content_type="font/ttf"),
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def _build_pdf_upload(self) -> SimpleUploadedFile:
        temp_dir = Path(tempfile.mkdtemp(prefix="jobs-pdf-"))
        pdf_path = temp_dir / "background.pdf"
        pdf_canvas = canvas.Canvas(str(pdf_path), pagesize=(400, 120))
        pdf_canvas.drawString(24, 100, "Pagina 1")
        pdf_canvas.showPage()
        pdf_canvas.save()
        content = pdf_path.read_bytes()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return SimpleUploadedFile("background.pdf", content, content_type="application/pdf")

    def _build_excel_upload(self, rows=None) -> SimpleUploadedFile:
        temp_dir = Path(tempfile.mkdtemp(prefix="jobs-xlsx-"))
        xlsx_path = temp_dir / "dados.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Nome", "Empresa"])
        for row in rows or [["Ana", "Empresa A"], ["Bruno", "Empresa B"]]:
            sheet.append(row)
        workbook.save(xlsx_path)
        content = xlsx_path.read_bytes()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return SimpleUploadedFile("dados.xlsx", content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def _build_template(self):
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Faixa",
            slug="faixa",
            background_pdf=self._build_pdf_upload(),
        )
        update_template_pdf_metadata(template)
        TemplateField.objects.create(
            template=template,
            name="nome",
            excel_column="1",
            x=20,
            y=80,
            width=200,
            height=24,
            font=self.font,
            font_size=18,
            order_index=1,
            text_transform=TemplateField.TextTransform.TITLE_SMART,
            transform_exceptions="de, da, do, dos, e",
        )
        return template

    def test_format_field_value_supports_title_transform(self):
        template = self._build_template()
        field = template.fields.get()
        formatted = format_field_value(field, "  joao da silva  ")
        self.assertEqual(formatted, "Joao da Silva")

    def test_job_form_validates_column_numbers(self):
        template = self._build_template()
        template.fields.update(excel_column="3")
        form = GenerationJobForm(
            data={"name": "Job", "template": template.pk},
            files={"source_excel": self._build_excel_upload()},
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("colunas numéricas", form.non_field_errors()[0])

    def test_process_job_uses_numeric_columns(self):
        template = self._build_template()
        job = GenerationJob.objects.create(
            user=self.user,
            template=template,
            name="Job",
            source_excel=self._build_excel_upload(),
            kind=GenerationJob.Kind.PREVIEW,
            status=GenerationJob.Status.QUEUED,
        )

        process_job(job)
        job.refresh_from_db()

        self.assertEqual(job.success_rows, 2)
        self.assertEqual(job.items.count(), 2)

    def test_job_delete_marks_inactive(self):
        template = self._build_template()
        job = GenerationJob.objects.create(
            user=self.user,
            template=template,
            name="Job Inativo",
            source_excel=self._build_excel_upload(),
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("jobs:delete", kwargs={"pk": job.pk}))

        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertFalse(job.is_active)
