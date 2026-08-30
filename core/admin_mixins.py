from typing import TYPE_CHECKING, ClassVar

from django.contrib import admin
from django.db.models import Model

if TYPE_CHECKING:
    _Base = admin.ModelAdmin
else:
    _Base = object


class OwnedAdminMixin(_Base):
    owner_field_name = "user"
    owner_related_fields: ClassVar[dict[str, type[Model]]] = {}

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or not hasattr(self.model, self.owner_field_name):
            return queryset
        return queryset.filter(**{self.owner_field_name: request.user})

    def get_exclude(self, request, obj=None):
        excludes = list(super().get_exclude(request, obj) or [])
        if not request.user.is_superuser and hasattr(self.model, self.owner_field_name):
            excludes.append(self.owner_field_name)
        return excludes

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and hasattr(obj, self.owner_field_name):
            setattr(obj, self.owner_field_name, request.user)
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        allowed = super().has_view_permission(request, obj)
        if (
            not allowed
            or obj is None
            or request.user.is_superuser
            or not hasattr(obj, self.owner_field_name)
        ):
            return allowed
        return getattr(obj, self.owner_field_name) == request.user

    def has_change_permission(self, request, obj=None):
        allowed = super().has_change_permission(request, obj)
        if (
            not allowed
            or obj is None
            or request.user.is_superuser
            or not hasattr(obj, self.owner_field_name)
        ):
            return allowed
        return getattr(obj, self.owner_field_name) == request.user

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        if (
            not allowed
            or obj is None
            or request.user.is_superuser
            or not hasattr(obj, self.owner_field_name)
        ):
            return allowed
        return getattr(obj, self.owner_field_name) == request.user

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        relation = self.owner_related_fields.get(db_field.name)
        if relation and not request.user.is_superuser:
            # `.objects` existe em toda subclasse concreta de Model (via
            # metaclasse do Django); o stub só sabe disso pra tipos concretos,
            # não pro `type[Model]` genérico usado aqui.
            kwargs["queryset"] = relation.objects.filter(user=request.user)  # type: ignore[attr-defined]
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
