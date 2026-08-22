from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import FontAssetForm
from .models import FontAsset
from .services import inspect_font_file

TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="sistema_vetorial_fonts_tests_")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class FontTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="fonts-user", password="senha123")
        cls.font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def test_inspect_font_file_reports_portuguese_support(self):
        metadata = inspect_font_file(str(self.font_path))
        self.assertTrue(metadata["supports_pt_br_basic"])

    def test_font_form_uses_filename_when_name_missing(self):
        uploaded = SimpleUploadedFile(
            "minha_fonte.ttf", self.font_path.read_bytes(), content_type="font/ttf"
        )
        form = FontAssetForm(data={"name": ""}, files={"file": uploaded})

        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        instance.user = self.user
        instance.save()

        self.assertEqual(instance.name, "Minha Fonte")
        self.assertTrue(instance.is_active)

    def test_delete_view_marks_font_inactive(self):
        font = FontAsset.objects.create(
            user=self.user,
            name="Fonte Teste",
            family="Fonte Teste",
            variant=FontAsset.Variant.REGULAR,
            file=SimpleUploadedFile(
                "DejaVuSans.ttf", self.font_path.read_bytes(), content_type="font/ttf"
            ),
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("fonts:delete", kwargs={"pk": font.pk}))

        self.assertEqual(response.status_code, 302)
        font.refresh_from_db()
        self.assertFalse(font.is_active)

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

        other = get_user_model().objects.create_user(username="outro-fontes", password="senha123")
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
            username="fonts-preview", password="senha123"
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
