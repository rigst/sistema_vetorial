from __future__ import annotations

from pathlib import Path

from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth.views import LoginView

from editor.models import DocumentTemplate
from fonts.models import FontAsset
from jobs.models import GenerationJob

from .models import UserProfile


DEFAULT_FONT_SOURCES = [
    ("Dejavu Sans", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")),
    ("Dejavu Serif", Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf")),
    ("Dejavu Mono", Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")),
]


def ensure_user_profile(user) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def ensure_default_fonts(user) -> None:
    for font_name, font_path in DEFAULT_FONT_SOURCES:
        if not font_path.exists():
            continue
        if FontAsset.objects.filter(user=user, name=font_name, is_builtin=True).exists():
            continue
        with font_path.open("rb") as font_file:
            font = FontAsset(user=user, name=font_name, family=font_name, is_builtin=True, is_active=True)
            font.file.save(font_path.name, font_file, save=False)
            font.metadata = {"builtin": True, "supports_pt_br_basic": True, "source": str(font_path)}
            font.save()


def cleanup_visitor_data(user) -> None:
    if not user or not hasattr(user, "profile"):
        return
    if user.profile.role != UserProfile.Role.VISITOR:
        return
    GenerationJob.objects.filter(user=user).delete()
    DocumentTemplate.objects.filter(user=user).delete()
    FontAsset.objects.filter(user=user).delete()
    user.delete()


class UsuarioLoginView(LoginView):
    template_name = "auth/login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            ensure_user_profile(request.user)
            ensure_default_fonts(request.user)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if "entrar_visitante" in request.POST:
            messages.warning(
                request,
                "O acesso visitante está temporariamente desativado.",
            )
            return redirect(reverse("login"))
        response = super().post(request, *args, **kwargs)
        if request.user.is_authenticated:
            ensure_user_profile(request.user)
            ensure_default_fonts(request.user)
        return response


def logout_and_cleanup(request):
    user = request.user if request.user.is_authenticated else None
    was_visitor = bool(user and hasattr(user, "profile") and user.profile.role == UserProfile.Role.VISITOR)
    if was_visitor:
        cleanup_visitor_data(user)
        logout(request)
        messages.info(
            request,
            "Sessão visitante encerrada. Os dados temporários deste acesso foram excluídos.",
        )
    else:
        logout(request)
    return redirect(reverse("login"))

