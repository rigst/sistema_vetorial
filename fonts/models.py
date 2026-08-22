from django.db import models

from core.models import OwnedModel


def font_upload_to(instance: "FontAsset", filename: str) -> str:
    # Fontes padrão ficam na raiz compartilhada da mídia privada. O diretório
    # por usuário é criado pelo processo web (www-data) com permissão 0755 e
    # não pode ser atualizado pelo usuário de deploy. O nome inclui o dono,
    # então continua isolado e pode ser substituído por ambos os processos no
    # diretório raiz, que é compartilhado pelo grupo.
    if instance.is_builtin:
        return f"builtin-{instance.user_id}-{filename}"
    return f"users/{instance.user_id}/fonts/{filename}"


class FontAsset(OwnedModel):
    name = models.CharField(max_length=255)
    family = models.CharField(max_length=255)
    file = models.FileField(upload_to=font_upload_to)
    # Rótulo do estilo (Regular, Bold, SemiBold Italic, Black...), lido do
    # próprio arquivo — não é mais uma lista fechada de 4 opções, porque um
    # pacote de fonte real costuma trazer uma escala inteira de pesos.
    variant = models.CharField(max_length=40, default="Regular")
    # Peso na escala OpenType/CSS (100-900): é o que ordena os pesos de um
    # mesmo family na lista, do mais fino ao mais preto.
    weight = models.PositiveSmallIntegerField(default=400)
    is_italic = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_builtin = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["family", "weight", "is_italic", "name"]
        unique_together = ("user", "family", "variant", "name")
        verbose_name = "fonte"
        verbose_name_plural = "fontes"

    def __str__(self) -> str:
        return f"{self.family} - {self.variant}"
