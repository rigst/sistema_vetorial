from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from reportlab.pdfgen import canvas

from core.auth import ensure_default_fonts
from core.cleanup import cleanup_expired_records
from core.storage import PrivateMediaStorage
from editor.models import DocumentTemplate
from editor.services import update_template_pdf_metadata
from fonts.models import FontAsset
from jobs.models import GenerationJob

TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="sistema_vetorial_core_tests_")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class CoreTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def _build_pdf_upload(self, filename: str = "background.pdf") -> SimpleUploadedFile:
        temp_dir = Path(tempfile.mkdtemp(prefix="core-pdf-"))
        pdf_path = temp_dir / filename
        pdf_canvas = canvas.Canvas(str(pdf_path), pagesize=(400, 120))
        pdf_canvas.drawString(24, 100, "Pagina 1")
        pdf_canvas.showPage()
        pdf_canvas.save()
        content = pdf_path.read_bytes()
        shutil.rmtree(temp_dir, ignore_errors=True)
        return SimpleUploadedFile(filename, content, content_type="application/pdf")

    def test_acesso_anonimo_na_raiz_termina_no_login(self):
        """A raiz virou um redirecionamento para a lista de modelos, então o
        anônimo passa por lá antes de cair no login — dois saltos, não um."""
        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("editor:list"))

        final = self.client.get(reverse("core:home"), follow=True)

        self.assertIn(reverse("login"), final.redirect_chain[-1][0])

    def test_visitor_access_is_disabled(self):
        response = self.client.post(reverse("login"), {"entrar_visitante": "1"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "O acesso visitante está temporariamente desativado.")
        self.assertFalse(
            get_user_model().objects.filter(username__startswith="visitante_").exists()
        )

    def test_authenticated_nav_links_to_jobs(self):
        user = get_user_model().objects.create_user(username="nav-user", password="senha123")
        self.client.force_login(user)

        response = self.client.get(reverse("editor:list"))

        self.assertContains(response, f'href="{reverse("jobs:list")}"')
        self.assertContains(response, "Arquivos")

    def test_ensure_default_fonts_creates_builtin_fonts(self):
        user = get_user_model().objects.create_user(username="font-user", password="senha123")
        ensure_default_fonts(user)
        self.assertGreaterEqual(FontAsset.objects.filter(user=user, is_builtin=True).count(), 1)

    def test_ensure_default_fonts_bundles_inter_full_weight_range(self):
        # DejaVu (as outras fontes padrão) só tem Regular/Bold — sem uma
        # família com a escala inteira, o seletor de "espessura" do editor
        # não tem o que oferecer além de dois pontos. Inter cobre 100-900,
        # com itálico real em cada peso.
        user = get_user_model().objects.create_user(username="inter-user", password="senha123")
        ensure_default_fonts(user)
        inter_fonts = FontAsset.objects.filter(user=user, family="Inter", is_builtin=True)
        weights = set(inter_fonts.filter(is_italic=False).values_list("weight", flat=True))
        self.assertEqual(weights, {100, 200, 300, 400, 500, 600, 700, 800, 900})
        italic_weights = set(inter_fonts.filter(is_italic=True).values_list("weight", flat=True))
        self.assertEqual(italic_weights, {100, 200, 300, 400, 500, 600, 700, 800, 900})

    def test_ensure_default_fonts_is_idempotent_for_inter(self):
        user = get_user_model().objects.create_user(username="inter-repeat", password="senha123")
        ensure_default_fonts(user)
        ensure_default_fonts(user)
        self.assertEqual(FontAsset.objects.filter(user=user, family="Inter").count(), 18)

    def test_ensure_default_fonts_bundles_wix_madefor_display(self):
        # Só existe como fonte variável no Google Fonts; os 5 arquivos
        # padrão são instâncias estáticas geradas com varLib.instancer (ver
        # core/auth.py) — confere que cada peso realmente virou um FontAsset
        # com o peso certo, não 5 cópias idênticas do 400 default.
        user = get_user_model().objects.create_user(username="wix-user", password="senha123")
        ensure_default_fonts(user)
        wix_fonts = FontAsset.objects.filter(
            user=user, family="Wix Madefor Display", is_builtin=True
        )
        weights = set(wix_fonts.values_list("weight", flat=True))
        self.assertEqual(weights, {400, 500, 600, 700, 800})
        self.assertFalse(wix_fonts.filter(is_italic=True).exists())

    def test_cleanup_expired_records_removes_old_files(self):
        user = get_user_model().objects.create_user(username="cleanup-user", password="senha123")
        font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        font = FontAsset.objects.create(
            user=user,
            name="Fonte",
            family="Fonte",
            variant="Regular",
            file=SimpleUploadedFile(
                "DejaVuSans.ttf", font_path.read_bytes(), content_type="font/ttf"
            ),
        )
        template = DocumentTemplate.objects.create(
            user=user,
            name="Template",
            slug="template",
            background_pdf=self._build_pdf_upload(),
        )
        update_template_pdf_metadata(template)
        job = GenerationJob.objects.create(
            user=user,
            template=template,
            name="Job",
            source_excel=SimpleUploadedFile(
                "dados.xlsx", b"fake", content_type="application/octet-stream"
            ),
        )
        old_timestamp = timezone.now() - timezone.timedelta(days=10)
        FontAsset.objects.filter(pk=font.pk).update(created_at=old_timestamp)
        DocumentTemplate.objects.filter(pk=template.pk).update(created_at=old_timestamp)
        GenerationJob.objects.filter(pk=job.pk).update(created_at=old_timestamp)

        result = cleanup_expired_records(retention_days=7)

        self.assertEqual(result["deleted_jobs"], 1)
        self.assertEqual(result["deleted_templates"], 1)
        self.assertEqual(result["deleted_fonts"], 1)

    def test_private_storage_has_no_public_url(self):
        storage = PrivateMediaStorage(location=TEST_MEDIA_ROOT)
        with self.assertRaises(ValueError):
            storage.url("arquivo.pdf")


class StaticAssetTests(TestCase):
    """Regressões de asset que quebram a UI sem quebrar nenhuma view."""

    def test_hidden_attribute_wins_over_the_layout_display(self):
        css = (Path(settings.BASE_DIR) / "static/css/style.css").read_text(encoding="utf-8")
        rule = re.search(r"\[hidden\]\s*\{([^}]*)\}", css)

        # Sem esta regra, .generate-progress { display: grid } deixa o
        # "Enviando a planilha…" visível para sempre no card de geração.
        self.assertIsNotNone(rule, "style.css precisa neutralizar o atributo hidden")
        self.assertIn("display: none", rule.group(1))
        self.assertIn("!important", rule.group(1))

    def test_job_launcher_script_is_shipped(self):
        script = Path(settings.BASE_DIR) / "static/js/job_launcher.js"
        self.assertTrue(script.exists())
        source = script.read_text(encoding="utf-8")
        for element_id in (
            "generate-card",
            "generate-excel-input",
            "generate-preview-button",
            "generate-full-button",
            "generate-progress-text",
            "generate-items",
        ):
            self.assertIn(element_id, source)

    def test_icon_button_wins_over_the_global_submit_button_rule(self):
        css = (Path(settings.BASE_DIR) / "static/css/style.css").read_text(encoding="utf-8")

        # `.icon-button` sozinho (uma classe) empata em especificidade com
        # `button[type="submit"]` (elemento + atributo) — e no empate quem
        # vem primeiro no arquivo perde. `button[type="submit"]` é definido
        # antes, então sem uma classe repetida aqui um botão de ícone que
        # também é `<button type="submit">` (excluir, duplicar, reprocessar)
        # herdava o preenchimento sólido do CTA primário: a exclusão de uma
        # fonte, por exemplo, ficava com a mesma cor forte do botão "Salvar".
        self.assertIn(".icon-button.icon-button", css)

    def test_field_panel_groups_are_labelled(self):
        css = (Path(settings.BASE_DIR) / "static/css/style.css").read_text(encoding="utf-8")
        self.assertIn(".field-section-label", css)
        self.assertIn(".field-advanced-hint", css)

        # Controles que só valem com o contorno ligado ficam visualmente
        # apagados via :has() — sem depender do JS terminar de rodar.
        self.assertIn("#field-outline-details:has(#field-border-enabled:not(:checked))", css)

    def test_button_secondary_and_link_button_win_over_the_global_submit_rule(self):
        css = (Path(settings.BASE_DIR) / "static/css/style.css").read_text(encoding="utf-8")

        # Mesmo bug do .icon-button, dois lugares a mais onde apareceu:
        # "Reprocessar"/"Inativar" (job_detail.html) e "Gerar lote completo"
        # (job_form.html) são <button type="submit" class="button-secondary">
        # e saíam com o preenchimento sólido do CTA primário; "Sair da conta"
        # (link-button, no interstitial de recusa dos termos) quebrava a
        # frase virando um botão cheio no meio do parágrafo.
        self.assertIn(".button-secondary.button-secondary", css)
        self.assertIn(".link-button.link-button", css)

    def test_page_titles_use_a_single_consistent_brand_name(self):
        """9 templates diziam "Sistema Vetorial" no <title> enquanto todo o
        resto do app (inclusive base.html, o valor padrão) usa
        "StölbenVetorial" — a aba do navegador mudava de nome dependendo da
        página em que a pessoa estivesse."""
        templates_dir = Path(settings.BASE_DIR) / "templates"
        offenders = [
            path
            for path in templates_dir.rglob("*.html")
            if "Sistema Vetorial{% endblock %}" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])
