from django.db import models

from core.models import OwnedModel, TimeStampedModel


def original_upload_to(instance: "ArquivoEstouro", filename: str) -> str:
    return f"users/{instance.lote.user_id}/estouros/{instance.lote_id}/originais/{filename}"


def resultado_upload_to(instance: "ArquivoEstouro", filename: str) -> str:
    return f"users/{instance.lote.user_id}/estouros/{instance.lote_id}/resultados/{filename}"


def previa_upload_to(instance: "ArquivoEstouro", filename: str) -> str:
    return f"users/{instance.lote.user_id}/estouros/{instance.lote_id}/previas/{filename}"


def zip_upload_to(instance: "LoteEstouro", filename: str) -> str:
    return f"users/{instance.user_id}/estouros/{instance.pk}/{filename}"


class LoteEstouro(OwnedModel):
    """Um envio: os arquivos e a configuração de estouro aplicada a todos."""

    class Status(models.TextChoices):
        NA_FILA = "na_fila", "Na fila"
        PROCESSANDO = "processando", "Processando"
        CONCLUIDO = "concluido", "Concluído"
        CONCLUIDO_COM_FALHAS = "com_falhas", "Concluído com falhas"
        FALHOU = "falhou", "Falhou"

    STATUS_EM_ANDAMENTO = (Status.NA_FILA, Status.PROCESSANDO)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NA_FILA)
    # Configuração como foi pedida (unidade, valores por lado, preenchimento...).
    configuracao = models.JSONField(default=dict)
    resumo_configuracao = models.CharField(max_length=255, blank=True)
    zip_file = models.FileField(upload_to=zip_upload_to, blank=True)
    erro = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "lote de estouro"
        verbose_name_plural = "lotes de estouro"

    def __str__(self) -> str:
        return f"Estouro #{self.pk} · {self.resumo_configuracao}"

    @property
    def em_andamento(self) -> bool:
        return self.status in self.STATUS_EM_ANDAMENTO


class ArquivoEstouro(TimeStampedModel):
    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        CONCLUIDO = "concluido", "Pronto"
        FALHOU = "falhou", "Falhou"

    lote = models.ForeignKey(LoteEstouro, on_delete=models.CASCADE, related_name="arquivos")
    ordem = models.PositiveIntegerField(default=0)
    nome_original = models.CharField(max_length=255)
    original = models.FileField(upload_to=original_upload_to)
    resultado = models.FileField(upload_to=resultado_upload_to, blank=True)
    previa = models.ImageField(upload_to=previa_upload_to, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    erro = models.TextField(blank=True)
    paginas = models.PositiveIntegerField(default=0)
    # Medidas visuais da primeira página, em pontos (antes/depois) e a linha de
    # corte em frações da folha final, para a prévia.
    medidas = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["ordem", "pk"]
        verbose_name = "arquivo de estouro"
        verbose_name_plural = "arquivos de estouro"

    def __str__(self) -> str:
        return self.nome_original

    @property
    def medidas_cm(self) -> dict[str, str]:
        """“182 × 74 cm” antes e depois, como a página é vista."""
        m = self.medidas or {}
        if not m:
            return {}

        def cm(pontos) -> str:
            valor = round(float(pontos) / 72 * 2.54, 1)
            return f"{valor:g}".replace(".", ",")

        return {
            "antes": f"{cm(m['largura_antes'])} × {cm(m['altura_antes'])} cm",
            "depois": f"{cm(m['largura_depois'])} × {cm(m['altura_depois'])} cm",
        }

    @property
    def nome_resultado(self) -> str:
        base = self.nome_original
        if base.lower().endswith(".pdf"):
            base = base[:-4]
        sufixo = self.lote.configuracao.get("sufixo") or "estouro"
        return f"{base}_{sufixo}.pdf"
