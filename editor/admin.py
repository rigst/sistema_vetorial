from django.contrib import admin

from core.admin_mixins import OwnedAdminMixin
from fonts.models import FontAsset

from .models import DocumentTemplate, TemplateField, TemplatePreviewPage


class TemplateFieldInline(admin.TabularInline):
    model = TemplateField
    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "font" and not request.user.is_superuser:
            kwargs["queryset"] = FontAsset.objects.filter(user=request.user, is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class TemplatePreviewPageInline(admin.TabularInline):
    model = TemplatePreviewPage
    extra = 0
    readonly_fields = ("page_number", "image", "width", "height")


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(OwnedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "user", "status", "version", "page_count", "updated_at")
    list_filter = ("status",)
    search_fields = ("name", "slug", "user__username")
    inlines = [TemplateFieldInline, TemplatePreviewPageInline]
