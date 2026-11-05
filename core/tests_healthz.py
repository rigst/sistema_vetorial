from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import TestCase, override_settings

from core import healthz
from core.testing import SENHA_TESTE

URL = "/healthz/"


class HealthzTests(TestCase):
    def test_tudo_ok_responde_200(self):
        resposta = self.client.get(URL)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.content, b"ok\n")
        self.assertIn("no-cache", resposta["Cache-Control"])

    def test_banco_fora_responde_503(self):
        with (
            mock.patch.object(
                healthz.connection, "cursor", side_effect=OperationalError("banco fora")
            ),
            self.assertLogs("core.healthz", level="ERROR") as logs,
        ):
            resposta = self.client.get(URL)

        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.content, b"indisponivel\n")
        self.assertIn("banco", logs.output[0])

    def test_cache_fora_responde_503(self):
        with (
            mock.patch.object(healthz.cache, "get", return_value=None),
            self.assertLogs("core.healthz", level="ERROR") as logs,
        ):
            resposta = self.client.get(URL)

        self.assertEqual(resposta.status_code, 503)
        self.assertIn("cache", logs.output[0])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False, CELERY_BROKER_URL="redis://x:6379/0")
    def test_broker_fora_responde_503(self):
        from config.celery import app

        with (
            mock.patch.object(app, "connection_for_write", side_effect=OSError("redis fora")),
            self.assertLogs("core.healthz", level="ERROR") as logs,
        ):
            resposta = self.client.get(URL)

        self.assertEqual(resposta.status_code, 503)
        self.assertIn("broker", logs.output[0])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False, CELERY_BROKER_URL="redis://x:6379/0")
    def test_broker_no_ar_responde_200(self):
        from config.celery import app

        with mock.patch.object(app, "connection_for_write") as conexao:
            resposta = self.client.get(URL)

        self.assertEqual(resposta.status_code, 200)
        conexao.return_value.__enter__.return_value.ensure_connection.assert_called_once()

    def test_post_nao_e_aceito(self):
        self.assertEqual(self.client.post(URL).status_code, 405)

    def test_nao_redireciona_usuario_com_termos_pendentes(self):
        # Usuário logado que ainda não aceitou os termos é levado ao re-aceite
        # em toda rota; a sonda não pode cair nesse redirecionamento.
        usuario = get_user_model().objects.create_user("sonda", password=SENHA_TESTE)
        self.client.force_login(usuario)

        with mock.patch("legal.middleware.precisa_reaceitar", return_value=True):
            self.assertEqual(self.client.get(URL).status_code, 200)
            self.assertEqual(self.client.get("/").status_code, 302)
