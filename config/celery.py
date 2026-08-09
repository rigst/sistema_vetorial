from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("sistema_vetorial")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.beat_schedule = {
    "cleanup-expired-assets-daily": {
        "task": "core.tasks.cleanup_expired_assets",
        "schedule": crontab(hour=3, minute=0),
    }
}
app.conf.timezone = settings.TIME_ZONE
