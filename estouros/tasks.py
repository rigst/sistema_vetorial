from celery import shared_task

from .services import processar_lote


@shared_task
def processar_lote_estouro(lote_id: int) -> None:
    processar_lote(lote_id)
