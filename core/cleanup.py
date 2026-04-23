from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from editor.models import DocumentTemplate
from fonts.models import FontAsset
from jobs.models import GenerationJob


def cleanup_expired_records(retention_days: int | None = None) -> dict[str, int]:
    retention_days = retention_days or settings.FILE_RETENTION_DAYS
    cutoff = timezone.now() - timezone.timedelta(days=retention_days)

    expired_jobs = GenerationJob.objects.filter(created_at__lt=cutoff)
    expired_templates = DocumentTemplate.objects.filter(created_at__lt=cutoff)
    expired_fonts = FontAsset.objects.filter(created_at__lt=cutoff)

    deleted_jobs = expired_jobs.count()
    expired_jobs.delete()

    deleted_templates = expired_templates.count()
    expired_templates.delete()

    deleted_fonts = expired_fonts.count()
    expired_fonts.delete()

    return {
        "retention_days": retention_days,
        "deleted_jobs": deleted_jobs,
        "deleted_templates": deleted_templates,
        "deleted_fonts": deleted_fonts,
    }
