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

from .models import GenerationJob
from .forms import GenerationJobForm
from .services import format_field_value, process_job, validate_font_supports_text


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

    def test_format_field_value_supports_text_transformations(self):
        font = self._build_font()
        template = self._build_template()
        field = TemplateField.objects.create(
            template=template,
            name="nome",
            label="Nome",
            excel_column="nome",
            order_index=1,
            page_number=1,
            value_type=TemplateField.ValueType.TEXT,
            x=30,
            y=170,
            width=180,
            height=20,
            font=font,
            font_size=14,
            text_transform=TemplateField.TextTransform.TITLE_SMART,
            transform_exceptions="de, da, do, dos, e, com",
            prefix="Sr. ",
            suffix=" Filho",
        )

        formatted = format_field_value(field, "  joao da silva e costa  ")
        self.assertEqual(formatted, "Sr. Joao da Silva e Costa Filho")

    def test_format_field_value_preserves_portuguese_accents(self):
        font = self._build_font()
        template = self._build_template()
        field = TemplateField.objects.create(
            template=template,
            name="cidade",
            label="Cidade",
            excel_column="cidade",
            order_index=1,
            page_number=1,
            value_type=TemplateField.ValueType.TEXT,
            x=30,
            y=170,
            width=180,
            height=20,
            font=font,
            font_size=14,
            text_transform=TemplateField.TextTransform.TITLE_SMART,
            transform_exceptions="de, da, do, dos, e, com, à, às",
        )

        formatted = format_field_value(field, "  são josé dos campos à beira-mar  ")
        self.assertEqual(formatted, "São José dos Campos à Beira-Mar")

    def test_validate_font_supports_text_detects_missing_glyph(self):
        font = self._build_font()
        template = self._build_template()
        field = TemplateField.objects.create(
            template=template,
            name="simbolo",
            label="Simbolo",
            excel_column="simbolo",
            order_index=1,
            page_number=1,
            x=30,
            y=170,
            width=180,
            height=20,
            font=font,
            font_size=14,
        )

        with self.assertRaises(ValueError):
            validate_font_supports_text(field, "Texto com caractere raro: \U0001F9EA")

    def test_format_field_value_supports_integer_padding(self):
        font = self._build_font()
        template = self._build_template()
        field = TemplateField.objects.create(
            template=template,
            name="numero",
            label="Numero",
            excel_column="numero",
            order_index=1,
            page_number=1,
            value_type=TemplateField.ValueType.INTEGER,
            x=30,
            y=170,
            width=180,
            height=20,
            font=font,
            font_size=14,
            integer_min_digits=5,
            prefix="Nº ",
        )

        formatted = format_field_value(field, "42")
        self.assertEqual(formatted, "Nº 00042")

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
            text_transform=TemplateField.TextTransform.UPPER,
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

    def test_job_status_and_downloads_are_protected_by_owner(self):
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
            name="Protected Job",
            kind=GenerationJob.Kind.FULL,
            source_excel=self._build_excel_upload(),
            status=GenerationJob.Status.QUEUED,
        )
        process_job(job)
        job.refresh_from_db()
        item = job.items.first()
        other_user = get_user_model().objects.create_user(username="jobs-other", password="senha123")

        self.client.force_login(other_user)

        status_response = self.client.get(reverse("jobs:status", kwargs={"pk": job.pk}))
        source_response = self.client.get(reverse("jobs:download-source", kwargs={"pk": job.pk}))
        zip_response = self.client.get(reverse("jobs:download-zip", kwargs={"pk": job.pk}))
        item_response = self.client.get(reverse("jobs:download-item", kwargs={"pk": item.pk}))

        self.assertEqual(status_response.status_code, 404)
        self.assertEqual(source_response.status_code, 404)
        self.assertEqual(zip_response.status_code, 404)
        self.assertEqual(item_response.status_code, 404)

    def test_owner_can_download_source_excel(self):
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
            name="Source Download Job",
            kind=GenerationJob.Kind.PREVIEW,
            source_excel=self._build_excel_upload(),
            status=GenerationJob.Status.QUEUED,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("jobs:download-source", kwargs={"pk": job.pk}))

        self.assertEqual(response.status_code, 200)

    def test_job_form_rejects_invalid_excel_with_friendly_message(self):
        template = self._build_template()
        uploaded = SimpleUploadedFile(
            "dados.xlsx",
            b"excel-invalido",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        form = GenerationJobForm(
            data={"name": "Job inválido", "template": template.pk},
            files={"source_excel": uploaded},
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Não foi possível ler o Excel", form.errors["source_excel"][0])

    def test_job_form_rejects_missing_headers_with_friendly_message(self):
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
        uploaded = self._build_excel_upload()
        form = GenerationJobForm(
            data={"name": "Job cabeçalho", "template": template.pk},
            files={"source_excel": uploaded},
            user=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["empresa"])
        sheet.append(["Empresa A"])
        temp_dir = Path(tempfile.mkdtemp(prefix="jobs-xlsx-invalid-"))
        xlsx_path = temp_dir / "dados_sem_nome.xlsx"
        workbook.save(xlsx_path)
        bad_upload = SimpleUploadedFile(
            "dados_sem_nome.xlsx",
            xlsx_path.read_bytes(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        shutil.rmtree(temp_dir, ignore_errors=True)

        bad_form = GenerationJobForm(
            data={"name": "Job cabeçalho inválido", "template": template.pk},
            files={"source_excel": bad_upload},
            user=self.user,
        )

        self.assertFalse(bad_form.is_valid())
        self.assertIn("O Excel não possui todos os cabeçalhos esperados", bad_form.non_field_errors()[0])

    def test_process_job_fails_gracefully_when_excel_has_no_data_rows(self):
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
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["nome"])
        temp_dir = Path(tempfile.mkdtemp(prefix="jobs-empty-xlsx-"))
        xlsx_path = temp_dir / "vazio.xlsx"
        workbook.save(xlsx_path)
        upload = SimpleUploadedFile(
            "vazio.xlsx",
            xlsx_path.read_bytes(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        shutil.rmtree(temp_dir, ignore_errors=True)
        job = GenerationJob.objects.create(
            user=self.user,
            template=template,
            name="Job sem dados",
            kind=GenerationJob.Kind.PREVIEW,
            source_excel=upload,
            status=GenerationJob.Status.QUEUED,
        )

        process_job(job)
        job.refresh_from_db()

        self.assertEqual(job.status, GenerationJob.Status.FAILED)
        self.assertEqual(job.last_error, "O Excel não possui linhas preenchidas após o cabeçalho.")
