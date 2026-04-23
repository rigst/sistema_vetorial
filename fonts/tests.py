from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .forms import FontAssetForm
from .services import inspect_font_file


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="sistema_vetorial_fonts_tests_")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class FontValidationTests(TestCase):
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
        self.assertFalse(metadata["missing_pt_br_basic_chars"])

    def test_font_form_persists_metadata(self):
        uploaded = SimpleUploadedFile(
            "DejaVuSans.ttf",
            self.font_path.read_bytes(),
            content_type="font/ttf",
        )
        form = FontAssetForm(
            data={
                "name": "",
                "family": "",
                "variant": "regular",
                "is_active": "on",
            },
            files={"file": uploaded},
        )

        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        instance.user = self.user
        instance.save()

        self.assertTrue(instance.metadata.get("supports_pt_br_basic"))
        self.assertTrue(instance.family)
        self.assertTrue(instance.name)

    def test_font_form_rejects_invalid_font_with_friendly_message(self):
        uploaded = SimpleUploadedFile(
            "fonte.ttf",
            b"arquivo-invalido",
            content_type="font/ttf",
        )
        form = FontAssetForm(
            data={
                "name": "",
                "family": "",
                "variant": "regular",
                "is_active": "on",
            },
            files={"file": uploaded},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Não foi possível ler esta fonte", form.errors["file"][0])
