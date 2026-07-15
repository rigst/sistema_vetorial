from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from reportlab.pdfgen import canvas

from fonts.models import FontAsset

from .forms import DocumentTemplateForm
from .models import DocumentTemplate, TemplateField
from .services import update_template_pdf_metadata


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="sistema_vetorial_editor_tests_")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class EditorFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="editor-user", password="senha123")
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

    def _build_pdf_upload(self, filename: str = "background.pdf", pages: int = 1) -> SimpleUploadedFile:
        temp_dir = Path(tempfile.mkdtemp(prefix="editor-pdf-"))
        pdf_path = temp_dir / filename
        pdf_canvas = canvas.Canvas(str(pdf_path), pagesize=(400, 120))
        for index in range(pages):
            pdf_canvas.drawString(24, 100, f"Pagina {index + 1}")
            pdf_canvas.showPage()
        pdf_canvas.save()
        content = pdf_path.read_bytes()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return SimpleUploadedFile(filename, content, content_type="application/pdf")

    def test_template_form_rejects_pdf_with_multiple_pages(self):
        form = DocumentTemplateForm(
            data={"name": "Faixa", "description": "Teste"},
            files={"background_pdf": self._build_pdf_upload(pages=2)},
        )
        form.instance.user = self.user

        self.assertFalse(form.is_valid())
        self.assertIn("exatamente 1 página", form.errors["background_pdf"][0])

    def test_preview_page_requires_owner(self):
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Template Preview",
            slug="template-preview",
            background_pdf=self._build_pdf_upload(),
        )
        update_template_pdf_metadata(template)
        other_user = get_user_model().objects.create_user(username="outro", password="senha123")

        self.client.force_login(other_user)
        response = self.client.get(reverse("editor:preview-page", kwargs={"pk": template.pk, "page_number": 1}))

        self.assertEqual(response.status_code, 404)

    def test_duplicate_template_copies_fields(self):
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Original",
            slug="original",
            background_pdf=self._build_pdf_upload(),
        )
        update_template_pdf_metadata(template)
        TemplateField.objects.create(
            template=template,
            name="nome",
            excel_column="1",
            x=20,
            y=80,
            width=160,
            height=24,
            font=self.font,
            font_size=18,
            order_index=1,
        )

        self.client.force_login(self.user)
        response = self.client.post(reverse("editor:duplicate", kwargs={"pk": template.pk}))

        self.assertEqual(response.status_code, 302)
        duplicate = DocumentTemplate.objects.exclude(pk=template.pk).get()
        self.assertEqual(duplicate.fields.count(), 1)
        self.assertEqual(duplicate.fields.first().name, "nome")

    def test_fields_api_creates_and_updates_field(self):
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Faixa",
            slug="faixa",
            background_pdf=self._build_pdf_upload(),
        )
        update_template_pdf_metadata(template)

        self.client.force_login(self.user)
        create_response = self.client.post(
            reverse("editor:fields-api", kwargs={"pk": template.pk}),
            data='{"name":"Nome","excel_column":1,"font_id":%s,"color":"#111111"}' % self.font.pk,
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        field_id = create_response.json()["field"]["id"]

        patch_response = self.client.patch(
            reverse("editor:field-api", kwargs={"pk": field_id}),
            data='{"name":"Nome completo","text_transform":"upper"}',
            content_type="application/json",
        )
        self.assertEqual(patch_response.status_code, 200)
        field = TemplateField.objects.get(pk=field_id)
        self.assertEqual(field.name, "Nome completo")
        self.assertEqual(field.text_transform, TemplateField.TextTransform.UPPER)

    def test_fields_api_creates_field_centered_with_next_excel_column(self):
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Faixa Central",
            slug="faixa-central",
            background_pdf=self._build_pdf_upload(),
            page_width=400,
            page_height=120,
        )
        TemplateField.objects.create(
            template=template,
            name="Campo existente",
            excel_column="3",
            x=20,
            y=80,
            width=100,
            height=20,
            font=self.font,
            font_size=18,
            order_index=1,
        )

        self.client.force_login(self.user)
        create_response = self.client.post(
            reverse("editor:fields-api", kwargs={"pk": template.pk}),
            data='{"name":"Novo campo","font_id":%s}' % self.font.pk,
            content_type="application/json",
        )

        self.assertEqual(create_response.status_code, 201)
        field = TemplateField.objects.exclude(name="Campo existente").get()
        self.assertEqual(field.excel_column, "4")
        self.assertEqual(float(field.x), 136.0)
        self.assertEqual(float(field.y), 49.2)
        self.assertEqual(field.text_align, TemplateField.TextAlign.CENTER)

    def test_delete_template_marks_inactive(self):
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Template",
            slug="template",
            background_pdf=self._build_pdf_upload(),
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("editor:delete", kwargs={"pk": template.pk}))

        self.assertEqual(response.status_code, 302)
        template.refresh_from_db()
        self.assertFalse(template.is_active)

    def test_update_page_renders_with_private_storage(self):
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Template Privado",
            slug="template-privado",
            background_pdf=self._build_pdf_upload(),
        )
        update_template_pdf_metadata(template)

        self.client.force_login(self.user)
        response = self.client.get(reverse("editor:update", kwargs={"pk": template.pk}))

        self.assertEqual(response.status_code, 200)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ImageBackgroundTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="editor-imagem", password="senha123")

    def _build_image_upload(self, filename: str = "fundo.png", size=(400, 120)) -> SimpleUploadedFile:
        from io import BytesIO

        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", size, (200, 220, 210)).save(buffer, format="PNG")
        return SimpleUploadedFile(filename, buffer.getvalue(), content_type="image/png")

    def test_form_converts_image_to_single_page_pdf(self):
        form = DocumentTemplateForm(
            data={"name": "Faixa de imagem", "description": ""},
            files={"background_pdf": self._build_image_upload()},
        )
        form.instance.user = self.user

        self.assertTrue(form.is_valid(), form.errors)
        template = form.save()
        self.assertTrue(template.background_pdf.name.endswith(".pdf"))

        update_template_pdf_metadata(template)
        template.refresh_from_db()
        self.assertEqual(float(template.page_width), 400.0)
        self.assertEqual(float(template.page_height), 120.0)
        self.assertEqual(template.page_count, 1)
        self.assertTrue(template.preview_pages.exists())

    def test_form_rejects_unknown_extension(self):
        upload = SimpleUploadedFile("fundo.gif", b"GIF89a...", content_type="image/gif")
        form = DocumentTemplateForm(
            data={"name": "Faixa", "description": ""},
            files={"background_pdf": upload},
        )
        form.instance.user = self.user

        self.assertFalse(form.is_valid())
        self.assertIn("PDF, PNG, JPG ou WebP", form.errors["background_pdf"][0])


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class FieldRotationAndSampleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="editor-rotacao", password="senha123")
        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        cls.font = FontAsset.objects.create(
            user=cls.user,
            name="Dejavu Sans",
            family="Dejavu Sans",
            file=SimpleUploadedFile("DejaVuSans.ttf", font_path.read_bytes(), content_type="font/ttf"),
        )

    def _build_template(self) -> DocumentTemplate:
        from io import BytesIO

        from reportlab.pdfgen import canvas as pdf_canvas

        buffer = BytesIO()
        canvas_obj = pdf_canvas.Canvas(buffer, pagesize=(400, 120))
        canvas_obj.showPage()
        canvas_obj.save()
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Rotacionado",
            slug="rotacionado",
            background_pdf=SimpleUploadedFile("fundo.pdf", buffer.getvalue(), content_type="application/pdf"),
            page_width=400,
            page_height=120,
        )
        return template

    def test_patch_persists_rotation(self):
        template = self._build_template()
        field = TemplateField.objects.create(
            template=template,
            name="nome",
            excel_column="1",
            x=20,
            y=20,
            width=160,
            height=24,
            font=self.font,
            font_size=18,
        )
        self.client.force_login(self.user)
        response = self.client.patch(
            reverse("editor:field-api", kwargs={"pk": field.pk}),
            data='{"rotation": 12.5, "x": 30, "y": 40}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["field"]["rotation"], 12.5)
        field.refresh_from_db()
        self.assertEqual(float(field.rotation), 12.5)

    def test_sample_endpoint_returns_formatted_rows(self):
        from io import BytesIO

        from openpyxl import Workbook

        template = self._build_template()
        field = TemplateField.objects.create(
            template=template,
            name="nome",
            excel_column="1",
            x=20,
            y=20,
            width=160,
            height=24,
            font=self.font,
            font_size=18,
            text_transform=TemplateField.TextTransform.UPPER,
        )
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Coluna 1"])
        sheet.append(["joão da silva"])
        sheet.append(["maria souza"])
        buffer = BytesIO()
        workbook.save(buffer)

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("editor:sample-data", kwargs={"pk": template.pk}),
            data={"excel": SimpleUploadedFile("amostra.xlsx", buffer.getvalue())},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["rows"][0]["values"][str(field.pk)], "JOÃO DA SILVA")

    def test_sample_endpoint_rejects_missing_file(self):
        template = self._build_template()
        self.client.force_login(self.user)
        response = self.client.post(reverse("editor:sample-data", kwargs={"pk": template.pk}))
        self.assertEqual(response.status_code, 400)
