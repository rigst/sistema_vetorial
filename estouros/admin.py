from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from core.admin_mixins import OwnedAdminMixin

from .models import ArquivoEstouro, LoteEstouro


class ArquivoEstouroInline(TabularInline):
    model = ArquivoEstouro
    extra = 0
    fields = ("nome_original", "status", "paginas", "erro")
    readonly_fields = fields


@admin.register(LoteEstouro)
class LoteEstouroAdmin(OwnedAdminMixin, ModelAdmin):
    list_display = ("pk", "user", "resumo_configuracao", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "resumo_configuracao")
    readonly_fields = ("configuracao", "resumo_configuracao", "zip_file", "erro")
    inlines = [ArquivoEstouroInline]
