from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from editor.models import DocumentTemplate, TemplatePreviewPage
from fonts.models import FontAsset
from jobs.models import GenerationItem, GenerationJob

from .files import delete_field_file, iter_file_fields
from .models import UserProfile


FILE_MODELS = (DocumentTemplate, TemplatePreviewPage, FontAsset, GenerationJob, GenerationItem)


@receiver(post_delete)
def delete_files_after_model_delete(sender, instance, **kwargs):
    if sender not in FILE_MODELS:
        return
    for _, field_file in iter_file_fields(instance):
        delete_field_file(field_file)


@receiver(pre_save)
def delete_replaced_files(sender, instance, **kwargs):
    if sender not in FILE_MODELS or not instance.pk:
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    for field_name, previous_file in iter_file_fields(previous):
        current_file = getattr(instance, field_name, None)
        previous_name = getattr(previous_file, "name", "")
        current_name = getattr(current_file, "name", "")
        if previous_name and previous_name != current_name:
            delete_field_file(previous_file)


@receiver(post_save, sender=get_user_model())
def ensure_profile_for_user(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
