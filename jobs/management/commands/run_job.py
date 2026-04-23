from django.core.management.base import BaseCommand, CommandError

from jobs.models import GenerationJob
from jobs.services import process_job


class Command(BaseCommand):
    help = "Processa um job de geração isoladamente."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)

    def handle(self, *args, **options):
        job_id = options["job_id"]
        try:
            job = GenerationJob.objects.get(pk=job_id)
        except GenerationJob.DoesNotExist as exc:
            raise CommandError(f"Job {job_id} não encontrado.") from exc

        process_job(job)
        self.stdout.write(self.style.SUCCESS(f"Job {job_id} processado."))
