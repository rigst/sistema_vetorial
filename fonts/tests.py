from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.testing import SENHA_TESTE

from .forms import FontAssetForm
from .models import FontAsset
from .services import inspect_font_file

TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="sistema_vetorial_fonts_tests_")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class FontTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="fonts-user", password=SENHA_TESTE)
        cls.font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def test_inspect_font_file_reports_portuguese_support(self):
        metadata = inspect_font_file(str(self.font_path))
        self.assertTrue(metadata["supports_pt_br_basic"])

    def test_font_form_uses_the_fonts_own_name_when_name_missing(self):
        """A fonte diz o próprio nome (nameID 4) — mais confiável que
        adivinhar a partir de como a pessoa nomeou o arquivo."""
        uploaded = SimpleUploadedFile(
            "minha_fonte.ttf", self.font_path.read_bytes(), content_type="font/ttf"
        )
        form = FontAssetForm(data={"name": ""}, files={"file": uploaded})

        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        instance.user = self.user
        instance.save()

        self.assertEqual(instance.name, "DejaVu Sans")
        self.assertTrue(instance.is_active)

    def test_font_form_falls_back_to_the_filename_without_font_metadata(self):
        # Simula uma fonte sem nameID 4 legível (utilitária, corrompida etc.):
        # sem nome próprio para usar, cai para o nome do arquivo.
        with mock.patch("fonts.forms.inspect_font_file", return_value={}):
            form = FontAssetForm(
                data={"name": ""},
                files={
                    "file": SimpleUploadedFile(
                        "minha_fonte.ttf", self.font_path.read_bytes(), content_type="font/ttf"
                    )
                },
            )
            self.assertTrue(form.is_valid(), form.errors)

        self.assertEqual(form.cleaned_data["name"], "Minha Fonte")

    def test_delete_view_marks_font_inactive(self):
        font = FontAsset.objects.create(
            user=self.user,
            name="Fonte Teste",
            family="Fonte Teste",
            variant="Regular",
            file=SimpleUploadedFile(
                "DejaVuSans.ttf", self.font_path.read_bytes(), content_type="font/ttf"
            ),
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("fonts:delete", kwargs={"pk": font.pk}))

        self.assertEqual(response.status_code, 302)
        font.refresh_from_db()
        self.assertFalse(font.is_active)

    def test_edit_page_does_not_crash_on_private_storage(self):
        # Regressão: o widget padrão do Django para FileField (Clearable
        # FileInput) monta um link "Arquivo atual: <a href=file.url>" ao
        # editar — e o Storage privado (core/storage.py) recusa gerar url()
        # de propósito, o que derrubava a página com 500 antes de o
        # usuário conseguir ver o formulário.
        font = FontAsset.objects.create(
            user=self.user,
            name="Fonte Teste",
            family="Fonte Teste",
            variant="Regular",
            file=SimpleUploadedFile(
                "DejaVuSans.ttf", self.font_path.read_bytes(), content_type="font/ttf"
            ),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("fonts:update", kwargs={"pk": font.pk}))

        self.assertEqual(response.status_code, 200)

    def test_edit_without_reuploading_keeps_the_existing_file(self):
        font = FontAsset.objects.create(
            user=self.user,
            name="Fonte Teste",
            family="Fonte Teste",
            variant="Regular",
            file=SimpleUploadedFile(
                "DejaVuSans.ttf", self.font_path.read_bytes(), content_type="font/ttf"
            ),
        )
        original_file_name = font.file.name
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("fonts:update", kwargs={"pk": font.pk}), data={"name": "Nome Novo"}
        )

        self.assertEqual(response.status_code, 302)
        font.refresh_from_db()
        self.assertEqual(font.name, "Nome Novo")
        self.assertEqual(font.file.name, original_file_name)

    def test_font_file_endpoint_serves_only_owner(self):
        font = FontAsset.objects.create(
            user=self.user,
            name="Dejavu",
            family="Dejavu Sans",
            file=SimpleUploadedFile(
                "DejaVuSans.ttf", self.font_path.read_bytes(), content_type="font/ttf"
            ),
        )
        url = reverse("fonts:file", kwargs={"pk": font.pk})

        other = get_user_model().objects.create_user(username="outro-fontes", password=SENHA_TESTE)
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 404)

        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "font/ttf")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class FontListPreviewTests(TestCase):
    """A lista de fontes só existe para escolher uma fonte — e uma lista de
    nomes em texto plano não deixa ver como cada uma realmente é."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="fonts-preview", password=SENHA_TESTE
        )
        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        cls.font = FontAsset.objects.create(
            user=cls.user,
            name="Dejavu Sans",
            family="Dejavu Sans",
            file=SimpleUploadedFile("DejaVuSans.ttf", font_path.read_bytes()),
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def test_list_renders_each_font_in_its_own_typeface(self):
        self.client.force_login(self.user)

        html = self.client.get(reverse("fonts:list")).content.decode()

        file_url = reverse("fonts:file", kwargs={"pk": self.font.pk})
        # A declaração @font-face carrega o arquivo do dono da fonte...
        self.assertIn(file_url, html)
        self.assertIn(f'font-family: "vetorial-font-{self.font.pk}"', html)
        # ...e a célula da tabela usa essa mesma família para exibir o nome.
        self.assertIn(
            f"font-family: 'vetorial-font-{self.font.pk}'",
            html,
        )

    def test_list_offers_a_search_box(self):
        self.client.force_login(self.user)

        found = self.client.get(reverse("fonts:list"), {"q": "Dejavu"})
        missing = self.client.get(reverse("fonts:list"), {"q": "Comic Sans"})

        self.assertContains(found, "Dejavu Sans")
        self.assertContains(missing, "Nenhuma fonte encontrada")
        self.assertIn('name="q"', found.content.decode())

    def test_form_labels_are_in_portuguese(self):
        """Regressão: o form nasceu sem `labels`, então Django gerava "Name"
        e "File" a partir do nome interno do campo — os únicos rótulos em
        inglês no meio de um app inteiro em pt-BR."""
        form = FontAssetForm()

        self.assertEqual(form.fields["name"].label, "Nome")
        self.assertEqual(form.fields["file"].label, "Arquivo (TTF ou OTF)")

    def test_create_page_does_not_leak_english_labels(self):
        self.client.force_login(self.user)

        html = self.client.get(reverse("fonts:create")).content.decode()

        self.assertNotIn(">Name<", html)
        self.assertNotIn(">File<", html)
        self.assertIn(">Nome<", html)
        self.assertIn("Arquivo (TTF ou OTF)", html)


class FontWeightDetectionTests(TestCase):
    """A fonte já diz o próprio peso e estilo (tabela OS/2) — o app parou de
    ignorar isso e passou a usar para agrupar família e ordenar por peso."""

    def test_regular_file_is_detected_as_weight_400(self):
        metadata = inspect_font_file("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

        self.assertEqual(metadata["weight"], 400)
        self.assertFalse(metadata["is_italic"])
        self.assertEqual(metadata["detected_family"], "DejaVu Sans")
        # A DejaVu chama a própria variante regular de "Book" (nameID 17) —
        # normalizado para "Regular", que qualquer pessoa reconhece.
        self.assertEqual(metadata["detected_variant"], "Regular")

    def test_bold_file_is_detected_as_weight_700(self):
        metadata = inspect_font_file("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

        self.assertEqual(metadata["weight"], 700)
        self.assertFalse(metadata["is_italic"])
        self.assertEqual(metadata["detected_variant"], "Bold")
        # A mesma família do arquivo regular: é o que deixa os dois lados
        # (Regular e Bold) agrupados como uma fonte só no seletor.
        self.assertEqual(metadata["detected_family"], "DejaVu Sans")

    def test_bold_oblique_file_is_detected_as_bold_and_italic(self):
        metadata = inspect_font_file(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-BoldOblique.ttf"
        )

        self.assertEqual(metadata["weight"], 700)
        self.assertTrue(metadata["is_italic"])


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class FontFamilyGroupingTests(TestCase):
    """Upload de Regular e Bold da mesma fonte: os dois precisam cair na
    mesma família em vez de virarem duas fontes sem relação (o bug que o
    formulário tinha antes — `family = name` sempre, `variant` sempre
    "regular", não importa o que o arquivo dissesse)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="fonts-grouping", password=SENHA_TESTE
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def _upload(self, filename: str, source: str) -> FontAsset:
        form = FontAssetForm(
            data={"name": ""},
            files={
                "file": SimpleUploadedFile(
                    filename, Path(source).read_bytes(), content_type="font/ttf"
                )
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        instance.user = self.user
        instance.save()
        return instance

    def test_regular_and_bold_uploads_share_the_same_family(self):
        regular = self._upload("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        bold = self._upload(
            "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        )

        self.assertEqual(regular.family, bold.family)
        self.assertNotEqual(regular.variant, bold.variant)
        self.assertLess(regular.weight, bold.weight)
        self.assertEqual(bold.weight, 700)
        self.assertEqual(bold.variant, "Bold")

    def test_editor_context_groups_fonts_by_family(self):
        from reportlab.pdfgen import canvas as rl_canvas

        from editor.forms import DocumentTemplateForm
        from editor.services import update_template_pdf_metadata
        from editor.views import _template_editor_context

        self._upload("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        self._upload("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

        buffer_path = Path(tempfile.mkdtemp(prefix="grouping-pdf-")) / "fundo.pdf"
        pdf_canvas = rl_canvas.Canvas(str(buffer_path), pagesize=(400, 120))
        pdf_canvas.showPage()
        pdf_canvas.save()
        form = DocumentTemplateForm(
            data={"name": "Grouping", "description": ""},
            files={
                "background_pdf": SimpleUploadedFile(
                    "fundo.pdf", buffer_path.read_bytes(), content_type="application/pdf"
                )
            },
        )
        form.instance.user = self.user
        self.assertTrue(form.is_valid(), form.errors)
        template = form.save()
        update_template_pdf_metadata(template)

        context = _template_editor_context(template, self.user)
        groups = {group["family"]: group["fonts"] for group in context["font_groups"]}

        self.assertIn("DejaVu Sans", groups)
        self.assertEqual(len(groups["DejaVu Sans"]), 2)
        # Regular (peso 400) vem antes de Bold (peso 700) dentro do grupo.
        self.assertEqual([font.weight for font in groups["DejaVu Sans"]], [400, 700])


class DefaultFontsIncludeBoldTests(TestCase):
    def test_ensure_default_fonts_creates_bold_variants(self):
        from core.auth import ensure_default_fonts

        user = get_user_model().objects.create_user(username="fonts-defaults", password=SENHA_TESTE)

        ensure_default_fonts(user)

        bold = FontAsset.objects.get(user=user, name="Dejavu Sans Bold")
        regular = FontAsset.objects.get(user=user, name="Dejavu Sans")
        self.assertEqual(bold.weight, 700)
        self.assertEqual(bold.family, regular.family)
        self.assertTrue(bold.is_builtin)
