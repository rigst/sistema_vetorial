from __future__ import annotations

from django.core.management.base import BaseCommand

from core.cleanup import cleanup_expired_visitors


class Command(BaseCommand):
    help = "Exclui contas de visitante mais velhas que VISITOR_ACCOUNT_TTL_HOURS."

    def handle(self, *args, **options):
        result = cleanup_expired_visitors()
        self.stdout.write(
            self.style.SUCCESS(
                f"Limpeza concluída. Visitantes excluídos: {result['deleted_visitors']} "
                f"(TTL: {result['ttl_hours']}h)."
            )
        )
