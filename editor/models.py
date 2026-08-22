from django.db import models

from core.models import OwnedModel, TimeStampedModel
from fonts.models import FontAsset


def background_upload_to(instance: "DocumentTemplate", filename: str) -> str:
    return f"users/{instance.user_id}/templates/{instance.storage_slug}/background/{filename}"


def preview_upload_to(instance: "DocumentTemplate", filename: str) -> str:
    return f"users/{instance.user_id}/templates/{instance.storage_slug}/preview/{filename}"


def preview_page_upload_to(instance: "TemplatePreviewPage", filename: str) -> str:
    return f"users/{instance.template.user_id}/templates/{instance.template.storage_slug}/preview_pages/{filename}"


class DocumentTemplate(OwnedModel):
    class FilenameSpaceMode(models.TextChoices):
        KEEP = "keep", "Manter como estão no texto"
        STRIP = "strip", "Remover"
        REPLACE = "replace", "Substituir por"

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    background_pdf = models.FileField(upload_to=background_upload_to)
    preview_image = models.ImageField(upload_to=preview_upload_to, blank=True)
    page_width = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    page_height = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    page_count = models.PositiveIntegerField(default=1)
    editor_state = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    # Nome de cada PDF gerado, com variáveis {1}, {2}... para colunas do
    # Excel (ex.: "{1}_{2}"). Em branco, cai no nome padrão (nome do job +
    # linha) — ver jobs/services.py:_create_item_pdf.
    filename_pattern = models.CharField(max_length=255, blank=True)
    # Só decide o que fazer com espaços vindos do TEXTO das colunas dentro de
    # filename_pattern — sem escolher nada, o espaço vai pro nome do arquivo
    # igual está no Excel (sistemas de arquivo atuais aceitam espaço no nome).
    filename_space_mode = models.CharField(
        max_length=10, choices=FilenameSpaceMode.choices, default=FilenameSpaceMode.KEEP
    )
    filename_space_replacement = models.CharField(max_length=5, blank=True, default="-")

    class Meta:
        ordering = ["name", "-updated_at"]
        unique_together = ("user", "slug")
        verbose_name = "projeto"
        verbose_name_plural = "projetos"

    def __str__(self) -> str:
        return self.name

    @property
    def storage_slug(self) -> str:
        return self.slug or f"template-{self.pk or 'novo'}"


class TemplateField(TimeStampedModel):
    class ValueType(models.TextChoices):
        TEXT = "text", "Texto"
        INTEGER = "integer", "Inteiro"

    class TextAlign(models.TextChoices):
        LEFT = "left", "Esquerda"
        CENTER = "center", "Centro"
        RIGHT = "right", "Direita"

    class TextTransform(models.TextChoices):
        NONE = "none", "Sem transformação"
        LOWER = "lower", "Minúsculas"
        UPPER = "upper", "Maiúsculas"
        TITLE = "title", "Iniciais maiúsculas"
        TITLE_SMART = "title_smart", "Palavras principais"

    class OverflowMode(models.TextChoices):
        TRUNCATE = "truncate", "Cortar"
        WRAP = "wrap", "Quebrar linha"
        SHRINK = "shrink", "Reduzir fonte"
        ERROR = "error", "Gerar erro"

    class GrowDirection(models.TextChoices):
        DOWN = "down", "Para baixo"
        UP = "up", "Para cima"

    template = models.ForeignKey(DocumentTemplate, on_delete=models.CASCADE, related_name="fields")
    name = models.CharField(max_length=100)
    excel_column = models.CharField(max_length=255, blank=True)
    order_index = models.PositiveIntegerField(default=0)
    page_number = models.PositiveIntegerField(default=1)
    value_type = models.CharField(max_length=20, choices=ValueType.choices, default=ValueType.TEXT)
    # x/y: canto superior-esquerdo da caixa, em pontos PDF, medidos a partir do
    # topo-esquerda da página (mesmo sistema do canvas do editor).
    x = models.DecimalField(max_digits=8, decimal_places=2)
    y = models.DecimalField(max_digits=8, decimal_places=2)
    width = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    height = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    # rotação em graus, sentido horário, em torno do canto superior-esquerdo.
    rotation = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    font = models.ForeignKey(FontAsset, on_delete=models.PROTECT, related_name="template_fields")
    font_size = models.DecimalField(max_digits=6, decimal_places=2)
    text_align = models.CharField(max_length=10, choices=TextAlign.choices, default=TextAlign.LEFT)
    text_transform = models.CharField(
        max_length=20, choices=TextTransform.choices, default=TextTransform.NONE
    )
    transform_exceptions = models.CharField(max_length=255, blank=True)
    # Quando excel_column junta mais de uma coluna (ex.: "{3}-{5}"), limita a
    # Transformação (text_transform) só às colunas listadas aqui (números
    # 1-based, os mesmos citados entre chaves). Lista vazia = aplica em
    # todas — mesmo comportamento de antes desta opção existir.
    transform_columns = models.JSONField(default=list, blank=True)
    color = models.CharField(max_length=20, default="#000000")
    text_underline = models.BooleanField(default=False)
    text_strikethrough = models.BooleanField(default=False)
    border_enabled = models.BooleanField(default=False)
    border_color = models.CharField(max_length=20, default="#000000")
    border_size_ratio = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    border_opacity = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    border_blur = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    line_height = models.DecimalField(max_digits=6, decimal_places=2, default=1.2)
    max_lines = models.PositiveIntegerField(default=1)
    # Só importa quando overflow_mode = WRAP: para onde o texto cresce ao
    # ganhar mais linhas do que cabiam antes. "down" mantém o topo da caixa
    # fixo (comportamento de sempre); "up" mantém a base fixa, para não
    # atropelar um campo colocado logo abaixo.
    grow_direction = models.CharField(
        max_length=10, choices=GrowDirection.choices, default=GrowDirection.DOWN
    )
    integer_min_digits = models.PositiveIntegerField(default=0)
    integer_keep_sign = models.BooleanField(default=True)
    empty_value = models.CharField(max_length=255, blank=True)
    trim_whitespace = models.BooleanField(default=True)
    overflow_mode = models.CharField(
        max_length=20,
        choices=OverflowMode.choices,
        default=OverflowMode.TRUNCATE,
    )
    constraints = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["page_number", "order_index", "id"]
        unique_together = ("template", "name")
        verbose_name = "campo"
        verbose_name_plural = "campos"

    def __str__(self) -> str:
        return f"{self.template.name} :: {self.name}"


class TemplatePreviewPage(TimeStampedModel):
    template = models.ForeignKey(
        DocumentTemplate, on_delete=models.CASCADE, related_name="preview_pages"
    )
    page_number = models.PositiveIntegerField()
    image = models.ImageField(upload_to=preview_page_upload_to)
    width = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    height = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    class Meta:
        ordering = ["page_number"]
        unique_together = ("template", "page_number")
        verbose_name = "página de pré-visualização"
        verbose_name_plural = "páginas de pré-visualização"

    def __str__(self) -> str:
        return f"{self.template.name} :: preview página {self.page_number}"
