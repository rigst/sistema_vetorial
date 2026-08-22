from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.auth import ensure_default_fonts


class Command(BaseCommand):
    help = "Adiciona ou atualiza as fontes padrão de todos os usuários."

    def handle(self, *args, **options):
        totals = {"users": 0, "created": 0, "updated": 0, "unchanged": 0}
        users = get_user_model().objects.order_by("pk").iterator()
        for user in users:
            result = ensure_default_fonts(user)
            totals["users"] += 1
            for key in ("created", "updated", "unchanged"):
                totals[key] += result[key]

        self.stdout.write(
            self.style.SUCCESS(
                "Fontes padrão provisionadas: "
                f"{totals['users']} usuário(s), "
                f"{totals['created']} criada(s), "
                f"{totals['updated']} atualizada(s), "
                f"{totals['unchanged']} inalterada(s)."
            )
        )
