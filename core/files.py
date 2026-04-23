from __future__ import annotations

from django.db.models.fields.files import FieldFile


def iter_file_fields(instance):
    for field in instance._meta.get_fields():
        if not hasattr(field, "attname"):
            continue
        value = getattr(instance, field.attname, None)
        if isinstance(value, FieldFile):
            yield field.name, value


def delete_field_file(field_file: FieldFile | None) -> None:
    if not field_file or not getattr(field_file, "name", ""):
        return
    storage = field_file.storage
    name = field_file.name
    if storage.exists(name):
        storage.delete(name)
