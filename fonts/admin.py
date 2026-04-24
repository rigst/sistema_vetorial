from django.contrib import admin

from core.admin_mixins import OwnedAdminMixin

from .models import FontAsset


@admin.register(FontAsset)
class FontAssetAdmin(OwnedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "user", "is_active", "is_builtin", "updated_at")
    list_filter = ("is_active", "is_builtin")
    search_fields = ("name", "user__username")
