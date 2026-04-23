from celery import shared_task

from .models import GenerationJob
from .services import process_job


@shared_task
def process_generation_job(job_id: int) -> None:
    job = GenerationJob.objects.get(pk=job_id)
    process_job(job)
