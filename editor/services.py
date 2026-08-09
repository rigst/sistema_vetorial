from __future__ import annotations

import subprocess
from pathlib import Path

import pikepdf
from django.core.files.base import File

from .models import DocumentTemplate, TemplatePreviewPage


def _render_page_previews(template: DocumentTemplate) -> None:
    pdf_path = Path(template.background_pdf.path)
    output_dir = Path(template.background_pdf.path).parent / "_preview"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = output_dir / "page"

    subprocess.run(
        [
            "pdftoppm",
            "-png",
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
    with pikepdf.Pdf.open(template.background_pdf.path) as pdf:
        first_page = pdf.pages[0]
        mediabox = [float(value) for value in first_page.MediaBox]
        template.page_width = mediabox[2] - mediabox[0]
        template.page_height = mediabox[3] - mediabox[1]
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
