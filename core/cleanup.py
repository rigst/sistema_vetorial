from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from editor.models import DocumentTemplate
from fonts.models import FontAsset
from jobs.models import GenerationJob

from .models import UserProfile


def cleanup_visitor_data(user) -> None:
    if not user or not hasattr(user, "profile"):
        return
    if user.profile.role != UserProfile.Role.VISITOR:
        return
    GenerationJob.objects.filter(user=user).delete()
    DocumentTemplate.objects.filter(user=user).delete()
    FontAsset.objects.filter(user=user).delete()
    user.delete()


def cleanup_expired_visitors(ttl_hours: int | None = None) -> dict[str, int]:
    ttl_hours = ttl_hours if ttl_hours is not None else settings.VISITOR_ACCOUNT_TTL_HOURS
    cutoff = timezone.now() - timedelta(hours=ttl_hours)

    expired = list(
        get_user_model()
        .objects.filter(profile__role=UserProfile.Role.VISITOR, date_joined__lt=cutoff)
        .select_related("profile")
    )
    for user in expired:
        cleanup_visitor_data(user)

    return {"ttl_hours": ttl_hours, "deleted_visitors": len(expired)}


def cleanup_expired_records(retention_days: int | None = None) -> dict[str, int]:
    retention_days = retention_days or settings.FILE_RETENTION_DAYS
    cutoff = timezone.now() - timedelta(days=retention_days)

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
