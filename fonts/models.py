from django.db import models

from core.models import OwnedModel


def font_upload_to(instance: "FontAsset", filename: str) -> str:
    return f"users/{instance.user_id}/fonts/{filename}"


class FontAsset(OwnedModel):
    class Variant(models.TextChoices):
        REGULAR = "regular", "Regular"
        BOLD = "bold", "Bold"
        ITALIC = "italic", "Italic"
        BOLD_ITALIC = "bold_italic", "Bold Italic"

    name = models.CharField(max_length=255)
    family = models.CharField(max_length=255)
    file = models.FileField(upload_to=font_upload_to)
    variant = models.CharField(max_length=20, choices=Variant.choices, default=Variant.REGULAR)
    is_active = models.BooleanField(default=True)
    is_builtin = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["family", "variant", "name"]
        unique_together = ("user", "family", "variant", "name")

    def __str__(self) -> str:
        return f"{self.family} - {self.get_variant_display()}"
