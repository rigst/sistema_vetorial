"""Dispara o processamento fora da requisição (Celery; sem ele, subprocesso).

Mesmo esquema de `jobs.runner`: se o broker estiver fora, o lote não fica
parado na fila.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from django.conf import settings

from .tasks import processar_lote_estouro

logger = logging.getLogger(__name__)


def disparar(lote_id: int) -> None:
    try:
        processar_lote_estouro.delay(lote_id)
        return
    except Exception:
        # Broker fora do ar aparece de várias formas (OperationalError do kombu,
        # RuntimeError do backend de resultados, OSError): qualquer falha ao
        # enfileirar cai no subprocesso, e fica registrada.
        logger.warning(
            "Celery indisponível; estouro processado em subprocesso",
            extra={"lote_id": lote_id},
            exc_info=True,
        )
        subprocess.Popen(
            [sys.executable, "manage.py", "processar_estouro", str(lote_id)],
            cwd=Path(settings.BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
