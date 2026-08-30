"""Prepara o banco descartável usado pelos testes E2E.

Cria o usuário, uma fonte, um projeto com fundo de imagem (o caminho sem perdas
da conversão) e a planilha que os testes enviam pela bancada.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.sessions.middleware import SessionMiddleware  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from core.auth import ensure_default_fonts  # noqa: E402
from editor.forms import _image_to_pdf  # noqa: E402
from editor.models import DocumentTemplate, TemplateField  # noqa: E402
from editor.services import update_template_pdf_metadata  # noqa: E402
from fonts.models import FontAsset  # noqa: E402
from legal.models import OrigemAceite  # noqa: E402
from legal.services import documentos_vigentes, registrar_aceite  # noqa: E402

USERNAME = "e2e"
PASSWORD = "e2e-senha-123"
TMP_DIR = Path(__file__).resolve().parent / ".tmp"


def build_excel(path: Path, rows: list[list[str]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Nome", "Curso"])
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def build_background() -> SimpleUploadedFile:
    image = Image.new("RGB", (842, 595), (247, 249, 246))
    draw = ImageDraw.Draw(image)
    draw.rectangle([24, 24, 818, 571], outline=(31, 122, 114), width=6)
    draw.rectangle([48, 48, 794, 547], outline=(200, 210, 205), width=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return _image_to_pdf(SimpleUploadedFile("fundo.png", buffer.getvalue()), "fundo")


def ensure_legal_docs_and_acceptance(user) -> None:
    """Publica os documentos legais reais do repositório e já registra o
    aceite do usuário `e2e` — sem isto, o teste do acesso visitante (que
    precisa de documentos vigentes) e o interstitial de re-aceite (que bloquearia
    o usuário `e2e` de primeira, quebrando toda suíte que loga com ele) entram
    em conflito.
    """
    call_command("importar_documentos_legais", "--publicar", verbosity=0)
    vigentes = documentos_vigentes()
    if not vigentes:
        return
    request = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    registrar_aceite(
        request,
        usuario=user,
        origem=OrigemAceite.CADASTRO,
        documentos=list(vigentes.values()),
    )


def main() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    build_excel(
        TMP_DIR / "dados.xlsx",
        [
            ["ana paula de souza", "Design"],
            ["bruno carvalho", "Arquitetura"],
            ["carla dos santos", "Engenharia"],
            ["diego lima", "Marketing"],
            ["elisa nogueira", "Direito"],
        ],
    )
    (TMP_DIR / "dados.csv").write_text("Nome,Curso\nana,Design\n", encoding="utf-8")
    build_excel(
        TMP_DIR / "dados_grande.xlsx",
        [[f"pessoa {i:02d} da silva", "Turma Grande"] for i in range(1, 31)],
    )

    User = get_user_model()
    user, _ = User.objects.get_or_create(username=USERNAME)
    user.set_password(PASSWORD)
    user.is_staff = True
    user.save()

    ensure_legal_docs_and_acceptance(user)

    DocumentTemplate.objects.filter(user=user).delete()
    FontAsset.objects.filter(user=user).delete()

    # As mesmas fontes padrão que qualquer usuário ganha no primeiro login
    # (Regular + Bold de Sans/Serif/Mono) — exercita o agrupamento por
    # família no seletor da bancada com dados reais, não uma fonte solta.
    ensure_default_fonts(user)
    font = FontAsset.objects.get(user=user, name="Dejavu Sans")

    template = DocumentTemplate.objects.create(
        user=user,
        name="Certificado E2E",
        slug="certificado-e2e",
        background_pdf=build_background(),
    )
    update_template_pdf_metadata(template)

    TemplateField.objects.create(
        template=template,
        name="Nome",
        excel_column="1",
        x=120,
        y=240,
        width=600,
        height=48,
        font=font,
        font_size=34,
        order_index=1,
        text_align=TemplateField.TextAlign.CENTER,
        text_transform=TemplateField.TextTransform.TITLE_SMART,
    )
    TemplateField.objects.create(
        template=template,
        name="Curso",
        excel_column="2",
        x=120,
        y=320,
        width=600,
        height=32,
        font=font,
        font_size=20,
        order_index=2,
        text_align=TemplateField.TextAlign.CENTER,
    )

    print(f"TEMPLATE_ID={template.pk}")


if __name__ == "__main__":
    main()
