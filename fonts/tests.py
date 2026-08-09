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
