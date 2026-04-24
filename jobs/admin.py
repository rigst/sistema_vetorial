from django.contrib import admin

from core.admin_mixins import OwnedAdminMixin
from editor.models import DocumentTemplate

from .models import GenerationItem, GenerationJob


class GenerationItemInline(admin.TabularInline):
    model = GenerationItem
    extra = 0
    readonly_fields = ("row_number", "status", "error_message", "created_at", "updated_at")


@admin.register(GenerationJob)
class GenerationJobAdmin(OwnedAdminMixin, admin.ModelAdmin):
    owner_related_fields = {"template": DocumentTemplate}
    list_display = ("name", "user", "template", "status", "processed_rows", "total_rows", "is_active", "updated_at")
    list_filter = ("status", "is_active")
    search_fields = ("name", "user__username", "template__name")
    inlines = [GenerationItemInline]
