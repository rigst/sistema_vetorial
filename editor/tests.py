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
