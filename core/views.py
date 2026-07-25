from django.views.generic import RedirectView


class HomeView(RedirectView):
    """A raiz do app leva direto à lista de projetos."""

    pattern_name = "editor:list"
