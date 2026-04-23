from __future__ import annotations

from django.core.management.base import BaseCommand

from core.cleanup import cleanup_expired_records


class Command(BaseCommand):
    help = "Exclui registros e arquivos com retenção vencida."

    def handle(self, *args, **options):
        result = cleanup_expired_records()
        self.stdout.write(
            self.style.SUCCESS(
                "Limpeza concluída. "
                f"Jobs: {result['deleted_jobs']}, "
                f"Templates: {result['deleted_templates']}, "
                f"Fontes: {result['deleted_fonts']}."
            )
        )
