from django.contrib import admin

from core.admin_mixins import OwnedAdminMixin

from .models import FontAsset


@admin.register(FontAsset)
class FontAssetAdmin(OwnedAdminMixin, admin.ModelAdmin):
    list_display = ("family", "variant", "name", "user", "is_active", "updated_at")
    list_filter = ("variant", "is_active")
    search_fields = ("family", "name", "user__username")
