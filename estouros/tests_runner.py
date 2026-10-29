from unittest import mock

from django.test import SimpleTestCase

from . import runner


class DispararTests(SimpleTestCase):
    def test_usa_o_celery_quando_ele_responde(self):
        with (
            mock.patch.object(runner.processar_lote_estouro, "delay") as delay,
            mock.patch.object(runner.subprocess, "Popen") as popen,
        ):
            runner.disparar(7)
        delay.assert_called_once_with(7)
        popen.assert_not_called()

    def test_sem_broker_processa_em_subprocesso_e_registra(self):
        with (
            mock.patch.object(
                runner.processar_lote_estouro, "delay", side_effect=RuntimeError("sem redis")
            ),
            mock.patch.object(runner.subprocess, "Popen") as popen,
            self.assertLogs("estouros.runner", level="WARNING"),
        ):
            runner.disparar(7)
        argumentos = popen.call_args.args[0]
        self.assertEqual(argumentos[-2:], ["processar_estouro", "7"])
