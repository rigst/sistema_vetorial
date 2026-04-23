from django.contrib import admin

from .models import GenerationItem, GenerationJob


class GenerationItemInline(admin.TabularInline):
    model = GenerationItem
    extra = 0
    readonly_fields = ("row_number", "status", "error_message", "created_at", "updated_at")


@admin.register(GenerationJob)
class GenerationJobAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "template", "status", "processed_rows", "total_rows", "updated_at")
    list_filter = ("status",)
    search_fields = ("name", "user__username", "template__name")
    inlines = [GenerationItemInline]
