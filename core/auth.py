from __future__ import annotations

from pathlib import Path

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.urls import reverse

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
    # Inter: única família padrão que traz a escala inteira de peso
    # (Thin…Black) com itálico real em cada peso — é o que dá conteúdo de
    # verdade ao seletor de "espessura" do painel, em vez de só Regular/Bold.
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
    # Wix Madefor Display: só existe como fonte variável no Google Fonts (um
    # arquivo só, peso 400-800 controlado por eixo) — sem itálico. Os 5
    # arquivos aqui são instâncias estáticas de verdade (glifo já "assado"
    # naquele peso), geradas uma vez com fontTools.varLib.instancer a partir
    # do .ttf variável oficial; o pipeline de contorno vetorial deste app não
    # lê eixo de variação, só glyf estático. Ver fonts/vendor/wix-madefor-
    # display/OFL.txt para a licença (SIL Open Font License).
    ("Wix Madefor Display", _WIX_DIR / "WixMadeforDisplay-Regular.ttf"),
    ("Wix Madefor Display Medium", _WIX_DIR / "WixMadeforDisplay-Medium.ttf"),
    ("Wix Madefor Display SemiBold", _WIX_DIR / "WixMadeforDisplay-SemiBold.ttf"),
    ("Wix Madefor Display Bold", _WIX_DIR / "WixMadeforDisplay-Bold.ttf"),
    ("Wix Madefor Display ExtraBold", _WIX_DIR / "WixMadeforDisplay-ExtraBold.ttf"),
]


def ensure_user_profile(user) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def ensure_default_fonts(user) -> None:
    from fonts.services import inspect_font_file

    for font_name, font_path in DEFAULT_FONT_SOURCES:
        if not font_path.exists():
            continue
        if FontAsset.objects.filter(user=user, name=font_name, is_builtin=True).exists():
            continue
        # Peso, itálico e a família de agrupamento vêm do próprio arquivo —
        # a mesma leitura que o upload manual usa (fonts/services.py) — para
        # que "Dejavu Sans" e "Dejavu Sans Bold" caiam na mesma família em
        # vez de virarem duas fontes sem relação nenhuma entre si.
        metadata = inspect_font_file(str(font_path))
        with font_path.open("rb") as font_file:
            font = FontAsset(
                user=user,
                name=font_name,
                family=metadata.get("detected_family") or font_name,
                variant=metadata.get("detected_variant") or "Regular",
                weight=metadata.get("weight") or 400,
                is_italic=bool(metadata.get("is_italic")),
                is_builtin=True,
                is_active=True,
            )
            font.file.save(font_path.name, font_file, save=False)
            font.metadata = {
                **metadata,
                "builtin": True,
                "source": str(font_path),
            }
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
