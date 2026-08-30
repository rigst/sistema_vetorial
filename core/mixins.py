from typing import TYPE_CHECKING

from django.contrib.auth.mixins import LoginRequiredMixin

if TYPE_CHECKING:
    from django.http import HttpRequest


class UserOwnedQuerysetMixin(LoginRequiredMixin):
    # Só a anotação: quem realmente fornece `request` em runtime é a View
    # concreta (ListView, DetailView, UpdateView — ver fonts/views.py,
    # jobs/views.py, editor/views.py), sempre depois deste mixin na MRO.
    request: "HttpRequest"

    def get_queryset(self):
        # get_queryset só existe nas Views concretas com as quais este mixin
        # é combinado (ListView/DetailView/UpdateView), nunca nele sozinho —
        # é o próprio ponto do mixin cooperativo, e o mypy não verifica MRO
        # cooperativa entre classes que só se encontram no site de uso.
        return super().get_queryset().filter(user=self.request.user)  # type: ignore[misc]

    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.user = self.request.user
        return super().form_valid(form)  # type: ignore[misc]
