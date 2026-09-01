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
    """Retenção temporal: apaga só o que é *saída gerada* — o lote e os PDFs/ZIP
    que saíram dele, junto com a planilha de origem.

    Os insumos reutilizáveis (templates, fundos, fontes e a planilha guardada
    no projeto) nunca são removidos por retenção: são o trabalho da pessoa, não
    subproduto descartável, e regerar um lote a partir deles é barato. A cópia
    da planilha que morre aqui é a do lote — a do projeto fica, ver
    jobs.services.store_source_excel_on_template. Insumo só some quando a
    própria conta é apagada — ver cleanup_visitor_data.
    """
    retention_days = retention_days or settings.FILE_RETENTION_DAYS
    cutoff = timezone.now() - timedelta(days=retention_days)

    # Só apaga registros de contas visitante: dados de usuários reais nunca
    # devem ser removidos por retenção temporal.
    visitor_users = get_user_model().objects.filter(profile__role=UserProfile.Role.VISITOR)

    expired_jobs = GenerationJob.objects.filter(created_at__lt=cutoff, user__in=visitor_users)

    deleted_jobs = expired_jobs.count()
    # O post_delete de core.signals limpa do storage o source_excel e o zip_file,
    # e o cascade em GenerationItem leva junto cada output_pdf.
    expired_jobs.delete()

    return {
        "retention_days": retention_days,
        "deleted_jobs": deleted_jobs,
    }
