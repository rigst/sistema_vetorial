from __future__ import annotations

from django.core.management.base import BaseCommand

from core.cleanup import cleanup_expired_records


class Command(BaseCommand):
    help = "Exclui os lotes gerados com retenção vencida (templates e fontes ficam)."

    def handle(self, *args, **options):
        result = cleanup_expired_records()
        self.stdout.write(
            self.style.SUCCESS(
                "Limpeza concluída. "
                f"Lotes apagados: {result['deleted_jobs']} "
                f"(retenção de {result['retention_days']} dia(s)). "
                "Templates, fundos e fontes foram preservados."
            )
        )
