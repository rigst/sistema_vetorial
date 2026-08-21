from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path

import pikepdf

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image, ImageChops, ImageDraw
from reportlab.pdfgen import canvas

from fonts.models import FontAsset

from .forms import DocumentTemplateForm, _image_to_pdf
from .models import DocumentTemplate, TemplateField
from .services import read_page_geometry, update_template_pdf_metadata

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
            file=SimpleUploadedFile(
                "DejaVuSans.ttf", font_path.read_bytes(), content_type="font/ttf"
            ),
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def _build_pdf_upload(
        self, filename: str = "background.pdf", pages: int = 1
    ) -> SimpleUploadedFile:
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

    def test_detail_page_wires_the_generate_card(self):
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Bancada",
            slug="bancada",
            background_pdf=self._build_pdf_upload(),
        )
        update_template_pdf_metadata(template)
        TemplateField.objects.create(
            template=template,
            name="nome",
            excel_column="1",
            x=10,
            y=10,
            width=100,
            height=20,
            font=self.font,
            font_size=12,
            order_index=1,
        )
        self.client.force_login(self.user)

        html = self.client.get(
            reverse("editor:detail", kwargs={"pk": template.pk})
        ).content.decode()

        # O card só funciona com os quatro elos: URL de lançamento, id do
        # projeto, token CSRF e o script que escuta os botões.
        self.assertIn(f'data-launch-url="{reverse("jobs:launch")}"', html)
        self.assertIn(f'data-template-id="{template.pk}"', html)
        self.assertIn("csrfmiddlewaretoken", html.split('id="generate-card"', 1)[1])
        self.assertIn("js/job_launcher.js", html)
        self.assertIn('id="generate-excel-input"', html)

    def test_detail_page_offers_the_sample_data_input(self):
        template = DocumentTemplate.objects.create(
            user=self.user,
            name="Bancada Amostra",
            slug="bancada-amostra",
            background_pdf=self._build_pdf_upload(),
        )
        update_template_pdf_metadata(template)
        self.client.force_login(self.user)

        html = self.client.get(
            reverse("editor:detail", kwargs={"pk": template.pk})
        ).content.decode()

        # template_editor.js escuta este id para carregar os dados no canvas.
        self.assertIn('id="sample-file-input"', html)
        self.assertIn('for="sample-file-input"', html)

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
        response = self.client.get(
            reverse("editor:preview-page", kwargs={"pk": template.pk, "page_number": 1})
        )

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
        cls.user = get_user_model().objects.create_user(
            username="editor-imagem", password="senha123"
        )

    def _build_image_upload(
        self, filename: str = "fundo.png", size=(400, 120)
    ) -> SimpleUploadedFile:
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
        cls.user = get_user_model().objects.create_user(
            username="editor-rotacao", password="senha123"
        )
        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        cls.font = FontAsset.objects.create(
            user=cls.user,
            name="Dejavu Sans",
            family="Dejavu Sans",
            file=SimpleUploadedFile(
                "DejaVuSans.ttf", font_path.read_bytes(), content_type="font/ttf"
            ),
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
            background_pdf=SimpleUploadedFile(
                "fundo.pdf", buffer.getvalue(), content_type="application/pdf"
            ),
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


class BackgroundImageFidelityTests(TestCase):
    """Um fundo enviado como imagem vira PDF sem reamostrar nem recomprimir:
    o que sai do gerador precisa ter os pixels do arquivo original."""

    def _sharp_image(self, mode: str = "RGB") -> Image.Image:
        image = Image.new("RGB", (240, 90), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        for x in range(0, 240, 5):
            draw.line([(x, 0), (x, 90)], fill=(0, 0, 0), width=1)
        draw.rectangle([30, 20, 110, 70], fill=(200, 30, 40))
        return image.convert(mode)

    def _decode_background(self, pdf_bytes: bytes):
        with pikepdf.Pdf.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[0]
            image = page.Resources.XObject.Im0
            box = [float(value) for value in page.MediaBox]
            filter_name = str(image.get("/Filter"))
            if filter_name == "/DCTDecode":
                decoded = Image.open(io.BytesIO(image.read_raw_bytes()))
                raw = image.read_raw_bytes()
            else:
                colorspace = str(image.ColorSpace)
                mode = "L" if colorspace == "/DeviceGray" else "RGB"
                decoded = Image.frombytes(
                    mode, (int(image.Width), int(image.Height)), image.read_bytes()
                )
                raw = None
            return decoded, filter_name, box, raw

    def test_png_background_keeps_every_pixel(self):
        source = self._sharp_image()
        buffer = io.BytesIO()
        source.save(buffer, format="PNG")

        converted = _image_to_pdf(SimpleUploadedFile("fundo.png", buffer.getvalue()), "fundo")
        decoded, filter_name, box, _ = self._decode_background(converted.read())

        self.assertEqual(filter_name, "/FlateDecode", "PNG não pode virar JPEG")
        self.assertEqual(box, [0.0, 0.0, 240.0, 90.0], "1 pixel vira 1 ponto")
        self.assertIsNone(
            ImageChops.difference(source, decoded.convert("RGB")).getbbox(),
            "a imagem embutida precisa ser idêntica à enviada",
        )

    def test_grayscale_png_stays_grayscale(self):
        source = self._sharp_image("L")
        buffer = io.BytesIO()
        source.save(buffer, format="PNG")

        converted = _image_to_pdf(SimpleUploadedFile("fundo.png", buffer.getvalue()), "fundo")
        decoded, filter_name, _, _ = self._decode_background(converted.read())

        self.assertEqual(filter_name, "/FlateDecode")
        self.assertEqual(decoded.mode, "L")
        self.assertIsNone(ImageChops.difference(source, decoded).getbbox())

    def test_jpeg_background_reuses_the_original_bytes(self):
        buffer = io.BytesIO()
        self._sharp_image().save(buffer, format="JPEG", quality=93)
        original = buffer.getvalue()

        converted = _image_to_pdf(SimpleUploadedFile("fundo.jpg", original), "fundo")
        _, filter_name, box, raw = self._decode_background(converted.read())

        # Sem recodificar: o JPEG entra no PDF exatamente como chegou.
        self.assertEqual(filter_name, "/DCTDecode")
        self.assertEqual(raw, original)
        self.assertEqual(box, [0.0, 0.0, 240.0, 90.0])

    def test_transparent_png_is_flattened_over_white(self):
        source = Image.new("RGBA", (20, 10), (0, 0, 0, 0))
        source.putpixel((5, 5), (255, 0, 0, 255))
        buffer = io.BytesIO()
        source.save(buffer, format="PNG")

        converted = _image_to_pdf(SimpleUploadedFile("fundo.png", buffer.getvalue()), "fundo")
        decoded, _, _, _ = self._decode_background(converted.read())

        self.assertEqual(decoded.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(decoded.getpixel((5, 5)), (255, 0, 0))


class PageGeometryTests(TestCase):
    def _pdf(self, *, size=(400, 120), rotation=0, cropbox=None) -> str:
        temp_dir = Path(tempfile.mkdtemp(prefix="geometry-"))
        self.addCleanup(shutil.rmtree, temp_dir, True)
        path = temp_dir / "page.pdf"
        with pikepdf.Pdf.new() as pdf:
            page = pdf.add_blank_page(page_size=size)
            if rotation:
                page.Rotate = rotation
            if cropbox:
                page.CropBox = pikepdf.Array([float(value) for value in cropbox])
            pdf.save(path)
        return str(path)

    def test_geometry_falls_back_to_the_mediabox(self):
        geometry = read_page_geometry(self._pdf())

        self.assertEqual((geometry.x0, geometry.y0, geometry.x1, geometry.y1), (0, 0, 400, 120))
        self.assertEqual((geometry.visible_width, geometry.visible_height), (400, 120))

    def test_geometry_prefers_the_cropbox(self):
        geometry = read_page_geometry(self._pdf(cropbox=[20, 10, 380, 110]))

        self.assertEqual((geometry.x0, geometry.y0), (20, 10))
        self.assertEqual((geometry.visible_width, geometry.visible_height), (360, 100))

    def test_geometry_clips_a_cropbox_larger_than_the_mediabox(self):
        geometry = read_page_geometry(self._pdf(cropbox=[-50, -50, 900, 900]))

        self.assertEqual((geometry.x0, geometry.y0, geometry.x1, geometry.y1), (0, 0, 400, 120))

    def test_rotation_swaps_the_visible_measures(self):
        for rotation, expected in ((90, (120, 400)), (180, (400, 120)), (270, (120, 400))):
            with self.subTest(rotation=rotation):
                geometry = read_page_geometry(self._pdf(rotation=rotation))
                self.assertEqual((geometry.visible_width, geometry.visible_height), expected)
