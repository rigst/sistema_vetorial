from django.db import models

from core.models import OwnedModel, TimeStampedModel
from editor.models import DocumentTemplate


def excel_upload_to(instance: "GenerationJob", filename: str) -> str:
    return f"users/{instance.user_id}/jobs/{instance.pk or 'new'}/source/{filename}"


def job_zip_upload_to(instance: "GenerationJob", filename: str) -> str:
    return f"users/{instance.user_id}/jobs/{instance.pk}/exports/{filename}"


def item_pdf_upload_to(instance: "GenerationItem", filename: str) -> str:
    return f"users/{instance.job.user_id}/jobs/{instance.job_id}/items/{filename}"


class GenerationJob(OwnedModel):
    class Kind(models.TextChoices):
        PREVIEW = "preview", "Amostra"
        FULL = "full", "Lote completo"

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        PREVIEW = "preview", "Prévia"
        QUEUED = "queued", "Na fila"
        PROCESSING = "processing", "Processando"
        COMPLETED = "completed", "Concluído"
        FAILED = "failed", "Falhou"

    template = models.ForeignKey(DocumentTemplate, on_delete=models.PROTECT, related_name="jobs")
    name = models.CharField(max_length=255)
    source_excel = models.FileField(upload_to=excel_upload_to)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.PREVIEW)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    success_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    column_map = models.JSONField(default=dict, blank=True)
    zip_file = models.FileField(upload_to=job_zip_upload_to, blank=True)
    last_error = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "lote"
        verbose_name_plural = "lotes"

    def __str__(self) -> str:
        return self.name


class GenerationItem(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        PROCESSING = "processing", "Processando"
        COMPLETED = "completed", "Concluído"
        FAILED = "failed", "Falhou"

    job = models.ForeignKey(GenerationJob, on_delete=models.CASCADE, related_name="items")
    row_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payload = models.JSONField(default=dict, blank=True)
    output_pdf = models.FileField(upload_to=item_pdf_upload_to, blank=True)
    # Nome mostrado ao usuário (download avulso e dentro do ZIP). Separado do
    # nome de armazenamento porque o Storage do Django sempre troca espaço
    # por "_" no disco — sem esse campo a opção "manter espaços" não teria
    # efeito nenhum no que a pessoa baixa.
    display_filename = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["row_number"]
        unique_together = ("job", "row_number")
        verbose_name = "item do lote"
        verbose_name_plural = "itens do lote"

    def __str__(self) -> str:
        return f"{self.job.name} :: linha {self.row_number}"
