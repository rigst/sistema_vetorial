from django.contrib.auth import get_user_model, login
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_POST
from django.views.generic import RedirectView

from legal.forms import AceiteForm
from legal.models import OrigemAceite
from legal.services import documentos_vigentes, registrar_aceite

from .auth import ensure_default_fonts
from .models import UserProfile


class HomeView(RedirectView):
    """A raiz do app leva direto à lista de projetos."""

    pattern_name = "editor:list"


@require_POST
def criar_visitante(request):
    """Cria a conta de visitante depois do aceite em /legal/aceite/.

    É o `LEGAL_VISITOR_ACTION` que a tela `legal/aceite.html` usa como
    `action` do formulário — o app `legal` só sabe que existe essa rota, não
    como a conta é criada. A conta nasce sem senha utilizável: um visitante
    novo é sempre uma conta nova, nunca um login de volta a uma anterior.
    """
    form = AceiteForm(request.POST)
    if not form.is_valid():
        vigentes = documentos_vigentes()
        return render(
            request,
            "legal/aceite.html",
            {
                "form": form,
                "documentos": list(vigentes.values()),
                "action": reverse("core:criar_visitante"),
                "campos_extras": {},
            },
            status=400,
        )

    username = f"visitante_{get_random_string(12).lower()}"
    # create_user(password=None) já grava uma senha inutilizável: um
    # visitante nunca volta a logar numa conta anterior, é sempre uma nova.
    # O signal `core.signals.ensure_profile_for_user` já cria o UserProfile
    # (papel padrão "editor") junto com o User — só falta promovê-lo.
    user = get_user_model().objects.create_user(username=username)
    UserProfile.objects.filter(user=user).update(role=UserProfile.Role.VISITOR)

    login(request, user)
    ensure_default_fonts(user)
    registrar_aceite(request, usuario=user, origem=OrigemAceite.VISITANTE, e_visitante=True)

    return redirect("editor:list")
