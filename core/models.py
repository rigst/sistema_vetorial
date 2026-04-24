from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OwnedModel(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)ss",
    )

    class Meta:
        abstract = True


class UserProfile(TimeStampedModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        EDITOR = "editor", "Editor"
        VISITOR = "visitor", "Visitante"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EDITOR)

    class Meta:
        verbose_name = "perfil de usuário"
        verbose_name_plural = "perfis de usuários"

    def __str__(self) -> str:
        return f"{self.user.username} :: {self.get_role_display()}"
