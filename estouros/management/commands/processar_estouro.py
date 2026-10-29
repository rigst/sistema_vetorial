from django.core.management.base import BaseCommand

from estouros.services import processar_lote


class Command(BaseCommand):
    help = "Processa um lote de estouro (usado quando o Celery está fora do ar)."

    def add_arguments(self, parser):
        parser.add_argument("lote_id", type=int)

    def handle(self, *args, **options):
        processar_lote(options["lote_id"])
