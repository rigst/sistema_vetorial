from __future__ import annotations

from django.core.management.base import BaseCommand

from editor.models import DocumentTemplate
from jobs.models import GenerationJob
from jobs.services import store_source_excel_on_template


class Command(BaseCommand):
    help = (
        "Copia para cada projeto a planilha do lote mais recente dele. "
        "Retroativo do momento em que o Excel passou a ser guardado no projeto; "
        "projetos que já têm planilha são ignorados."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Só mostra o que seria feito, sem gravar nada.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        copiados = 0
        for template in DocumentTemplate.objects.order_by("pk"):
            if template.source_excel.name:
                continue
            job = (
                GenerationJob.objects.filter(template=template)
                .exclude(source_excel="")
                .order_by("-created_at")
                .first()
            )
            if not job:
                continue
            self.stdout.write(f"projeto {template.pk} ({template.name}) <- lote {job.pk}")
            if not dry_run:
                store_source_excel_on_template(job)
            copiados += 1

        verbo = "seriam copiadas" if dry_run else "copiadas"
        self.stdout.write(self.style.SUCCESS(f"{copiados} planilha(s) {verbo}."))
