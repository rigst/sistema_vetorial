from __future__ import annotations

import subprocess
from pathlib import Path
from typing import NamedTuple

import pikepdf
from django.core.files.base import File

from .models import DocumentTemplate, TemplatePreviewPage


class PageGeometry(NamedTuple):
    """Geometria real da página de fundo, em pontos.

    `box` é a caixa visível (CropBox quando existe, senão MediaBox) — a mesma
    que o pdftoppm rasteriza para o editor. `visible_width`/`visible_height`
    já consideram o /Rotate, então são as medidas que o usuário vê na bancada
    e nas quais os campos são posicionados.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    rotation: int

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def visible_width(self) -> float:
        return self.height if self.rotation in {90, 270} else self.width

    @property
    def visible_height(self) -> float:
        return self.width if self.rotation in {90, 270} else self.height


def _box_values(page, name: str) -> list[float] | None:
    box = page.get(name)
    if box is None:
        return None
    values = [float(value) for value in box]
    return [
        min(values[0], values[2]),
        min(values[1], values[3]),
        max(values[0], values[2]),
        max(values[1], values[3]),
    ]


def read_page_geometry(pdf_path: str, page_index: int = 0) -> PageGeometry:
    with pikepdf.Pdf.open(pdf_path) as pdf:
        page = pdf.pages[page_index]
        media = _box_values(page, "/MediaBox") or [0.0, 0.0, 612.0, 792.0]
        crop = _box_values(page, "/CropBox") or media
        # A spec manda recortar a CropBox pela MediaBox.
        box = [
            max(crop[0], media[0]),
            max(crop[1], media[1]),
            min(crop[2], media[2]),
            min(crop[3], media[3]),
        ]
        if box[2] <= box[0] or box[3] <= box[1]:
            box = media
        rotation = int(page.get("/Rotate") or 0) % 360
        if rotation % 90:
            rotation = 0
    return PageGeometry(box[0], box[1], box[2], box[3], rotation)


def _render_page_previews(template: DocumentTemplate) -> None:
    pdf_path = Path(template.background_pdf.path)
    output_dir = Path(template.background_pdf.path).parent / "_preview"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = output_dir / "page"

    subprocess.run(
        [
            "pdftoppm",
            "-png",
            # Sem -cropbox o poppler rasteriza a MediaBox; a geração compõe na
            # caixa visível, então o preview precisa recortar do mesmo jeito.
            "-cropbox",
            "-scale-to",
            "1400",
            str(pdf_path),
            str(output_prefix),
        ],
        check=True,
        capture_output=True,
    )

    template.preview_pages.all().delete()

    preview_files = sorted(output_dir.glob("page-*.png"))
    for index, preview_file in enumerate(preview_files, start=1):
        preview_page = TemplatePreviewPage(
            template=template,
            page_number=index,
            width=template.page_width or 0,
            height=template.page_height or 0,
        )
        with preview_file.open("rb") as rendered:
            preview_page.image.save(
                f"{template.storage_slug}-preview-{index}.png",
                File(rendered),
                save=False,
            )
        preview_page.save()

    if preview_files:
        with preview_files[0].open("rb") as rendered:
            template.preview_image.save(
                f"{template.storage_slug}-preview.png", File(rendered), save=False
            )


def update_template_pdf_metadata(template: DocumentTemplate) -> DocumentTemplate:
    geometry = read_page_geometry(template.background_pdf.path)
    # Medidas visíveis: é nelas que o editor posiciona os campos e é nelas que
    # a geração desenha o overlay, então as duas pontas não podem divergir.
    template.page_width = geometry.visible_width
    template.page_height = geometry.visible_height
    with pikepdf.Pdf.open(template.background_pdf.path) as pdf:
        template.page_count = len(pdf.pages)

    _render_page_previews(template)
    template.save(
        update_fields=[
            "page_width",
            "page_height",
            "page_count",
            "preview_image",
            "updated_at",
        ]
    )
    return template
