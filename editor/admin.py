from django.contrib import admin

from .models import DocumentTemplate, TemplateField, TemplatePreviewPage


class TemplateFieldInline(admin.TabularInline):
    model = TemplateField
    extra = 0


class TemplatePreviewPageInline(admin.TabularInline):
    model = TemplatePreviewPage
    extra = 0
    readonly_fields = ("page_number", "image", "width", "height")


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "status", "version", "page_count", "updated_at")
    list_filter = ("status",)
    search_fields = ("name", "slug", "user__username")
    inlines = [TemplateFieldInline, TemplatePreviewPageInline]
