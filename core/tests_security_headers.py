from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.testing import SENHA_TESTE

POLITICA_PADRAO = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
CABECALHO = "Permissions-Policy"


class PermissionsPolicyTests(TestCase):
    def test_valor_padrao_e_o_da_frota(self):
        self.assertEqual(settings.PERMISSIONS_POLICY, POLITICA_PADRAO)

    def test_rotas_publicas_mandam_o_cabecalho(self):
        for url in ("/healthz/", "/login/"):
            with self.subTest(url=url):
                resposta = self.client.get(url)

                self.assertEqual(resposta.status_code, 200)
                self.assertEqual(resposta[CABECALHO], POLITICA_PADRAO)

    def test_admin_manda_o_cabecalho(self):
        resposta = self.client.get("/admin/login/")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta[CABECALHO], POLITICA_PADRAO)

    def test_admin_logado_manda_o_cabecalho_sem_trocar_a_csp_do_admin(self):
        admin = get_user_model().objects.create_superuser(
            username="admin-pp", email="admin-pp@example.com", password=SENHA_TESTE
        )
        self.client.force_login(admin)

        resposta = self.client.get("/admin/", follow=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta[CABECALHO], POLITICA_PADRAO)
        self.assertIn("'unsafe-eval'", resposta["Content-Security-Policy"])

    def test_redirecionamento_tambem_manda_o_cabecalho(self):
        resposta = self.client.get("/")

        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta[CABECALHO], POLITICA_PADRAO)

    @override_settings(PERMISSIONS_POLICY="camera=(self)")
    def test_valor_vem_da_setting(self):
        resposta = self.client.get("/healthz/")

        self.assertEqual(resposta[CABECALHO], "camera=(self)")

    @override_settings(PERMISSIONS_POLICY="")
    def test_setting_vazia_nao_manda_o_cabecalho(self):
        resposta = self.client.get("/healthz/")

        self.assertFalse(resposta.has_header(CABECALHO))
