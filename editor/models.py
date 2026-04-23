from django.db import models

from core.models import OwnedModel, TimeStampedModel
from fonts.models import FontAsset


def background_upload_to(instance: "DocumentTemplate", filename: str) -> str:
    return f"users/{instance.user_id}/templates/{instance.slug}/background/{filename}"


def preview_upload_to(instance: "DocumentTemplate", filename: str) -> str:
    return f"users/{instance.user_id}/templates/{instance.slug}/preview/{filename}"


def preview_page_upload_to(instance: "TemplatePreviewPage", filename: str) -> str:
    return f"users/{instance.template.user_id}/templates/{instance.template.slug}/preview_pages/{filename}"


class DocumentTemplate(OwnedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        READY = "ready", "Pronto"
        ARCHIVED = "archived", "Arquivado"

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    background_pdf = models.FileField(upload_to=background_upload_to)
    preview_image = models.ImageField(upload_to=preview_upload_to, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    page_width = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    page_height = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    page_count = models.PositiveIntegerField(default=1)
    version = models.PositiveIntegerField(default=1)
    editor_state = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name", "-updated_at"]
        unique_together = ("user", "slug", "version")

    def __str__(self) -> str:
        return self.name


class TemplateField(TimeStampedModel):
    class TextAlign(models.TextChoices):
        LEFT = "left", "Esquerda"
        CENTER = "center", "Centro"
        RIGHT = "right", "Direita"

    class OverflowMode(models.TextChoices):
        TRUNCATE = "truncate", "Cortar"
        WRAP = "wrap", "Quebrar linha"
        SHRINK = "shrink", "Reduzir fonte"
        ERROR = "error", "Gerar erro"

    template = models.ForeignKey(DocumentTemplate, on_delete=models.CASCADE, related_name="fields")
    name = models.CharField(max_length=100)
    label = models.CharField(max_length=255)
    excel_column = models.CharField(max_length=255, blank=True)
    order_index = models.PositiveIntegerField(default=0)
    page_number = models.PositiveIntegerField(default=1)
    x = models.DecimalField(max_digits=8, decimal_places=2)
    y = models.DecimalField(max_digits=8, decimal_places=2)
    width = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    height = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    font = models.ForeignKey(FontAsset, on_delete=models.PROTECT, related_name="template_fields")
    font_size = models.DecimalField(max_digits=6, decimal_places=2)
    is_bold = models.BooleanField(default=False)
    is_italic = models.BooleanField(default=False)
    text_align = models.CharField(max_length=10, choices=TextAlign.choices, default=TextAlign.LEFT)
    color = models.CharField(max_length=20, default="#000000")
    letter_spacing = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    line_height = models.DecimalField(max_digits=6, decimal_places=2, default=1.2)
    max_lines = models.PositiveIntegerField(default=1)
    overflow_mode = models.CharField(
        max_length=20,
        choices=OverflowMode.choices,
        default=OverflowMode.TRUNCATE,
    )
    preview_text = models.CharField(max_length=255, blank=True)
    constraints = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["page_number", "order_index", "id"]
        unique_together = ("template", "name")

    def __str__(self) -> str:
        return f"{self.template.name} :: {self.label}"


class TemplatePreviewPage(TimeStampedModel):
    template = models.ForeignKey(DocumentTemplate, on_delete=models.CASCADE, related_name="preview_pages")
    page_number = models.PositiveIntegerField()
    image = models.ImageField(upload_to=preview_page_upload_to)
    width = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    height = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    class Meta:
        ordering = ["page_number"]
        unique_together = ("template", "page_number")

    def __str__(self) -> str:
        return f"{self.template.name} :: preview página {self.page_number}"
