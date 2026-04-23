from __future__ import annotations

from celery import shared_task

from .cleanup import cleanup_expired_records


@shared_task
def cleanup_expired_assets() -> dict[str, int]:
    return cleanup_expired_records()
