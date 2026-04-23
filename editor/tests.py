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
class EditorServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="editor-user", password="senha123")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def _build_pdf_upload(self, filename: str = "background.pdf", pages: int = 1) -> SimpleUploadedFile:
        temp_dir = Path(tempfile.mkdtemp(prefix="editor-pdf-"))
        pdf_path = temp_dir / filename
        pdf_canvas = canvas.Canvas(str(pdf_path), pagesize=(300, 200))
        for page_number in range(1, pages + 1):
            pdf_canvas.drawString(24, 180, f"Pagina {page_number}")
            pdf_canvas.showPage()
        pdf_canvas.save()
        content = pdf_path.read_bytes()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return SimpleUploadedFile(filename, content, content_type="application/pdf")

    def _build_font(self) -> FontAsset:
        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        return FontAsset.objects.create(
            user=self.user,
            name="DejaVu Sans",
            family="DejaVu Sans",
            variant=FontAsset.Variant.REGULAR,
            file=SimpleUploadedFile("DejaVuSans.ttf", font_path.read_bytes(), content_type="font/ttf"),
        )

    def test_update_template_pdf_metadata_creates_preview_pages(self):
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Template Preview",
            slug="template-preview",
            background_pdf=self._build_pdf_upload(pages=2),
        )

        update_template_pdf_metadata(template)
        template.refresh_from_db()

        self.assertEqual(int(template.page_count), 2)
        self.assertTrue(template.preview_image.name)
        self.assertEqual(template.preview_pages.count(), 2)
        self.assertTrue(template.preview_pages.first().image.name)

    def test_duplicate_template_copies_fields(self):
        font = self._build_font()
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Original",
            slug="original",
            background_pdf=self._build_pdf_upload(),
            status=DocumentTemplate.Status.READY,
        )
        update_template_pdf_metadata(template)
        TemplateField.objects.create(
            template=template,
            name="nome",
            label="Nome",
            excel_column="nome",
            order_index=1,
            page_number=1,
            x=12,
            y=40,
            width=160,
            height=18,
            font=font,
            font_size=11,
        )

        self.client.force_login(self.user)
        response = self.client.post(f"/templates/{template.pk}/duplicar/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(DocumentTemplate.objects.count(), 2)
        duplicate = DocumentTemplate.objects.exclude(pk=template.pk).get()
        self.assertEqual(duplicate.fields.count(), 1)
        self.assertEqual(duplicate.fields.first().label, "Nome")

    def test_preview_page_requires_owner(self):
        other_user = get_user_model().objects.create_user(username="outro-editor", password="senha123")
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Template Preview Protegido",
            slug="template-preview-protegido",
            background_pdf=self._build_pdf_upload(pages=2),
        )
        update_template_pdf_metadata(template)

        self.client.force_login(other_user)
        response = self.client.get(reverse("editor:preview-page", kwargs={"pk": template.pk, "page_number": 1}))

        self.assertEqual(response.status_code, 404)

    def test_template_form_rejects_invalid_pdf_with_friendly_message(self):
        uploaded = SimpleUploadedFile(
            "modelo.pdf",
            b"pdf-invalido",
            content_type="application/pdf",
        )
        form = DocumentTemplateForm(
            data={
                "name": "Template Inválido",
                "slug": "template-invalido",
                "description": "Teste",
                "status": DocumentTemplate.Status.DRAFT,
            },
            files={"background_pdf": uploaded},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Não foi possível ler este PDF", form.errors["background_pdf"][0])
