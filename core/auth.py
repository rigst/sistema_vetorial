from __future__ import annotations

import hashlib
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from editor.models import DocumentTemplate
from fonts.models import FontAsset
from jobs.models import GenerationJob

from .models import UserProfile

_INTER_DIR = Path(__file__).resolve().parent.parent / "fonts" / "vendor" / "inter"
_WIX_DIR = Path(__file__).resolve().parent.parent / "fonts" / "vendor" / "wix-madefor-display"

DEFAULT_FONT_SOURCES = [
    ("Dejavu Sans", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")),
    ("Dejavu Sans Bold", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    ("Dejavu Serif", Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf")),
    ("Dejavu Serif Bold", Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf")),
    ("Dejavu Mono", Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")),
    ("Dejavu Mono Bold", Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf")),
    # Cada variação é um arquivo selecionável por si só no editor. Peso e
    # itálico são lidos do arquivo; não são simulados por controles separados.
    # Arquivos vendorizados em fonts/vendor/inter/ (SIL OFL 1.1, ver LICENSE.txt).
    ("Inter Thin", _INTER_DIR / "Inter-Thin.ttf"),
    ("Inter Thin Italic", _INTER_DIR / "Inter-ThinItalic.ttf"),
    ("Inter Extra Light", _INTER_DIR / "Inter-ExtraLight.ttf"),
    ("Inter Extra Light Italic", _INTER_DIR / "Inter-ExtraLightItalic.ttf"),
    ("Inter Light", _INTER_DIR / "Inter-Light.ttf"),
    ("Inter Light Italic", _INTER_DIR / "Inter-LightItalic.ttf"),
    ("Inter Regular", _INTER_DIR / "Inter-Regular.ttf"),
    ("Inter Italic", _INTER_DIR / "Inter-Italic.ttf"),
    ("Inter Medium", _INTER_DIR / "Inter-Medium.ttf"),
    ("Inter Medium Italic", _INTER_DIR / "Inter-MediumItalic.ttf"),
    ("Inter SemiBold", _INTER_DIR / "Inter-SemiBold.ttf"),
    ("Inter SemiBold Italic", _INTER_DIR / "Inter-SemiBoldItalic.ttf"),
    ("Inter Bold", _INTER_DIR / "Inter-Bold.ttf"),
    ("Inter Bold Italic", _INTER_DIR / "Inter-BoldItalic.ttf"),
    ("Inter Extra Bold", _INTER_DIR / "Inter-ExtraBold.ttf"),
    ("Inter Extra Bold Italic", _INTER_DIR / "Inter-ExtraBoldItalic.ttf"),
    ("Inter Black", _INTER_DIR / "Inter-Black.ttf"),
    ("Inter Black Italic", _INTER_DIR / "Inter-BlackItalic.ttf"),
    # O Google Fonts publica a Wix Madefor Display como variável (wght
    # 400-800), sem itálico. Estas cinco instâncias estáticas foram geradas do
    # arquivo oficial para o pipeline vetorial usar o desenho real de cada
    # peso. Origem e reprodução: fonts/vendor/wix-madefor-display/SOURCE.md.
    ("Wix Madefor Display", _WIX_DIR / "WixMadeforDisplay-Regular.ttf"),
    ("Wix Madefor Display Medium", _WIX_DIR / "WixMadeforDisplay-Medium.ttf"),
    ("Wix Madefor Display SemiBold", _WIX_DIR / "WixMadeforDisplay-SemiBold.ttf"),
    ("Wix Madefor Display Bold", _WIX_DIR / "WixMadeforDisplay-Bold.ttf"),
    ("Wix Madefor Display ExtraBold", _WIX_DIR / "WixMadeforDisplay-ExtraBold.ttf"),
]


def ensure_user_profile(user) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_default_fonts(user) -> dict[str, int]:
    from fonts.services import inspect_font_file

    result = {"created": 0, "updated": 0, "unchanged": 0}
    for font_name, font_path in DEFAULT_FONT_SOURCES:
        if not font_path.exists():
            continue
        source_sha256 = _file_sha256(font_path)
        existing = FontAsset.objects.filter(
            user=user, name=font_name, is_builtin=True
        ).first()
        if existing and existing.metadata.get("builtin_sha256") == source_sha256:
            result["unchanged"] += 1
            continue
        metadata = inspect_font_file(str(font_path))
        with font_path.open("rb") as font_file:
            font = existing or FontAsset(user=user, name=font_name, is_builtin=True)
            font.family = metadata.get("detected_family") or font_name
            font.variant = metadata.get("detected_variant") or "Regular"
            font.weight = metadata.get("weight") or 400
            font.is_italic = bool(metadata.get("is_italic"))
            if not existing:
                font.is_active = True
            old_file_name = font.file.name if existing and font.file else ""
            font.file.save(font_path.name, font_file, save=False)
            font.metadata = {
                **metadata,
                "builtin": True,
                "source": str(font_path),
                "builtin_sha256": source_sha256,
            }
            if existing:
                # QuerySet.update evita o sinal global de substituição, que
                # tenta apagar o arquivo legado (pertencente ao www-data)
                # antes de o banco apontar para a cópia nova.
                FontAsset.objects.filter(pk=font.pk).update(
                    family=font.family,
                    variant=font.variant,
                    weight=font.weight,
                    is_italic=font.is_italic,
                    file=font.file.name,
                    metadata=font.metadata,
                    updated_at=timezone.now(),
                )
            else:
                font.save()
            # Só remove depois que o banco aponta para a cópia nova. Arquivos
            # legados podem pertencer ao www-data e não ser apagáveis pelo
            # usuário de deploy; nesse caso ficam órfãos, mas o provisionamento
            # e a aplicação continuam íntegros.
            if old_file_name and old_file_name != font.file.name:
                try:
                    font.file.storage.delete(old_file_name)
                except PermissionError:
                    pass
        result["updated" if existing else "created"] += 1
    return result


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
    was_visitor = bool(
        user and hasattr(user, "profile") and user.profile.role == UserProfile.Role.VISITOR
    )
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
