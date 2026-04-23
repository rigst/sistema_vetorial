from __future__ import annotations

import io
from functools import lru_cache
import re
import unicodedata
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile

import pikepdf
from django.core.files.base import ContentFile
from django.db import transaction
from fontTools.ttLib import TTFont as FontToolsTTFont
from openpyxl import load_workbook
from pikepdf import Page, Pdf, Rectangle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from editor.models import TemplateField

from .models import GenerationItem, GenerationJob


def _humanize_generation_error(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, pikepdf.PdfError):
        return "Não foi possível compor o PDF final desta linha com o modelo enviado."
    if isinstance(exc, OSError):
        return "Não foi possível acessar um dos arquivos necessários para gerar esta linha."
    return "Ocorreu um erro inesperado ao gerar esta linha do PDF."


def _register_font(field: TemplateField) -> str:
    font_name = f"font_{field.font_id}"
    registered = pdfmetrics.getRegisteredFontNames()
    if font_name not in registered:
        pdfmetrics.registerFont(TTFont(font_name, field.font.file.path))
    return font_name


def _normalize_value(value) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


DEFAULT_TITLE_EXCEPTIONS = {
    "a", "as", "o", "os",
    "de", "da", "das", "do", "dos",
    "e", "em", "com", "para", "por",
    "na", "nas", "no", "nos",
    "à", "às",
}


def _normalize_unicode_text(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def _title_word_pt_br(word: str) -> str:
    if not word:
        return word
    first = word[:1].upper()
    rest = word[1:]
    return first + rest


def _smart_title_token(token: str, exceptions: set[str], is_edge: bool) -> str:
    parts = re.split(r"([-/'’])", token)
    normalized_parts = []
    for part in parts:
        if part in {"-", "/", "'", "’"}:
            normalized_parts.append(part)
            continue
        lowered = part.lower()
        if not is_edge and lowered in exceptions:
            normalized_parts.append(lowered)
        else:
            normalized_parts.append(_title_word_pt_br(lowered))
    return "".join(normalized_parts)


def _smart_title(text: str, exceptions_raw: str) -> str:
    text = _normalize_unicode_text(text)
    words = text.split()
    if not words:
        return ""
    exceptions = {
        _normalize_unicode_text(item.strip()).lower()
        for item in (exceptions_raw or "").split(",")
        if item.strip()
    } or DEFAULT_TITLE_EXCEPTIONS
    return " ".join(
        _smart_title_token(word, exceptions, index in {0, len(words) - 1})
        for index, word in enumerate(words)
    )


def _load_font_cmap(font_path: str) -> set[int]:
    font = FontToolsTTFont(font_path)
    try:
        cmap = set()
        for table in font["cmap"].tables:
            cmap.update(table.cmap.keys())
        return cmap
    finally:
        font.close()


@lru_cache(maxsize=256)
def _cached_font_cmap(font_path: str) -> frozenset[int]:
    return frozenset(_load_font_cmap(font_path))


def get_missing_font_chars(field: TemplateField, text: str) -> list[str]:
    text = _normalize_unicode_text(text)
    if not text:
        return []
    supported_codepoints = _cached_font_cmap(field.font.file.path)
    return sorted({char for char in text if not char.isspace() and ord(char) not in supported_codepoints})


def validate_font_supports_text(field: TemplateField, text: str) -> None:
    text = _normalize_unicode_text(text)
    if not text:
        return
    missing_chars = get_missing_font_chars(field, text)
    if missing_chars:
        chars_display = ", ".join(repr(char) for char in missing_chars[:10])
        raise ValueError(
            f"A fonte '{field.font.family}' nao suporta todos os caracteres exigidos pelo texto. Faltando: {chars_display}."
        )


def format_field_value(field: TemplateField, raw_value: str) -> str:
    value = _normalize_unicode_text("" if raw_value is None else str(raw_value))
    if field.trim_whitespace:
        value = value.strip()

    if not value:
        value = field.empty_value or ""

    if field.value_type == TemplateField.ValueType.INTEGER and value:
        stripped = value.strip()
        negative = stripped.startswith("-")
        digits = re.sub(r"\D", "", stripped)
        if digits:
            number = str(int(digits))
            if field.integer_min_digits:
                number = number.zfill(field.integer_min_digits)
            if negative and field.integer_keep_sign:
                value = f"-{number}"
            else:
                value = number

    if field.text_transform == TemplateField.TextTransform.LOWER:
        value = value.lower()
    elif field.text_transform == TemplateField.TextTransform.UPPER:
        value = value.upper()
    elif field.text_transform == TemplateField.TextTransform.TITLE:
        value = " ".join(_title_word_pt_br(token.lower()) for token in value.split())
    elif field.text_transform == TemplateField.TextTransform.TITLE_SMART:
        value = _smart_title(value, field.transform_exceptions)

    return _normalize_unicode_text(f"{field.prefix or ''}{value}{field.suffix or ''}")


def load_excel_rows(excel_path: str):
    workbook = load_workbook(excel_path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    workbook.close()
    if not rows:
        return [], []
    headers = [_normalize_value(value) for value in rows[0]]
    data_rows = []
    for row_index, row in enumerate(rows[1:], start=2):
        payload = {}
        has_value = False
        for idx, header in enumerate(headers):
            key = header or f"coluna_{idx + 1}"
            value = _normalize_value(row[idx] if idx < len(row) else "")
            payload[key] = value
            has_value = has_value or bool(value)
        if has_value:
            data_rows.append((row_index, payload))
    return headers, data_rows


def get_template_expected_headers(job: GenerationJob) -> list[str]:
    return [field.excel_column for field in job.template.fields.all() if field.excel_column]


def _fit_text_lines(text: str, font_name: str, font_size: float, max_width: float, mode: str, max_lines: int):
    if not text:
        return [""], font_size

    if max_width <= 0:
        return text.splitlines()[:max_lines], font_size

    def wrap(current_size: float):
        words = text.split()
        if not words:
            return [""]
        lines = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if pdfmetrics.stringWidth(candidate, font_name, current_size) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    if mode == TemplateField.OverflowMode.WRAP:
        lines = wrap(font_size)
        return lines[:max_lines], font_size

    if mode == TemplateField.OverflowMode.SHRINK:
        size = font_size
        while size >= 4:
            lines = wrap(size)
            if len(lines) <= max_lines and max(
                pdfmetrics.stringWidth(line, font_name, size) for line in lines if line is not None
            ) <= max_width:
                return lines, size
            size -= 0.5
        return wrap(max(4, size)), max(4, size)

    if mode == TemplateField.OverflowMode.ERROR:
        if pdfmetrics.stringWidth(text, font_name, font_size) > max_width:
            raise ValueError("Texto excede a largura configurada para o campo.")
        return [text], font_size

    trimmed = text
    while trimmed and pdfmetrics.stringWidth(trimmed, font_name, font_size) > max_width:
        trimmed = trimmed[:-1]
    return [trimmed], font_size


def _draw_field(pdf_canvas, field: TemplateField, value: str):
    font_name = _register_font(field)
    validate_font_supports_text(field, value)
    font_size = float(field.font_size)
    max_width = float(field.width)
    max_lines = max(field.max_lines, 1)
    lines, adjusted_size = _fit_text_lines(
        value,
        font_name,
        font_size,
        max_width,
        field.overflow_mode,
        max_lines,
    )

    pdf_canvas.saveState()
    pdf_canvas.setFillColor(HexColor(field.color or "#000000"))
    pdf_canvas.setFont(font_name, adjusted_size)

    line_height = max(adjusted_size * float(field.line_height), adjusted_size)
    top_y = float(field.y)

    for index, line in enumerate(lines[:max_lines]):
        baseline_y = top_y - adjusted_size - (index * line_height)
        x = float(field.x)
        if field.text_align == TemplateField.TextAlign.CENTER and max_width > 0:
            x = x + max_width / 2
            pdf_canvas.drawCentredString(x, baseline_y, line)
        elif field.text_align == TemplateField.TextAlign.RIGHT and max_width > 0:
            x = x + max_width
            pdf_canvas.drawRightString(x, baseline_y, line)
        else:
            pdf_canvas.drawString(x, baseline_y, line)
    pdf_canvas.restoreState()


def _build_overlay_pdf(job: GenerationJob, payload: dict) -> bytes:
    buffer = io.BytesIO()
    page_width = float(job.template.page_width or 0)
    page_height = float(job.template.page_height or 0)
    pdf_canvas = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    fields = list(job.template.fields.select_related("font").order_by("page_number", "order_index"))
    total_pages = max(job.template.page_count, 1)

    for page_number in range(1, total_pages + 1):
        for field in fields:
            if field.page_number != page_number:
                continue
            raw_value = payload.get(field.excel_column) or payload.get(field.label) or payload.get(field.name) or ""
            value = format_field_value(field, raw_value)
            _draw_field(pdf_canvas, field, value)
        pdf_canvas.showPage()
    pdf_canvas.save()
    return buffer.getvalue()


def _merge_overlay(background_pdf_path: str, overlay_bytes: bytes) -> bytes:
    with NamedTemporaryFile(suffix=".pdf") as overlay_temp:
        overlay_temp.write(overlay_bytes)
        overlay_temp.flush()

        with Pdf.open(background_pdf_path) as base_pdf, Pdf.open(overlay_temp.name) as overlay_pdf:
            for index, destination in enumerate(base_pdf.pages):
                if index >= len(overlay_pdf.pages):
                    break
                destination_page = Page(destination)
                overlay_page = Page(overlay_pdf.pages[index])
                mediabox = [float(value) for value in destination_page.obj.MediaBox]
                destination_page.add_overlay(
                    overlay_page,
                    Rectangle(mediabox[0], mediabox[1], mediabox[2], mediabox[3]),
                )

            output = io.BytesIO()
            base_pdf.save(output)
            return output.getvalue()


def _create_item_pdf(job: GenerationJob, row_number: int, payload: dict) -> GenerationItem:
    item = GenerationItem.objects.create(job=job, row_number=row_number, payload=payload, status=GenerationItem.Status.PROCESSING)
    try:
        overlay_bytes = _build_overlay_pdf(job, payload)
        output_bytes = _merge_overlay(job.template.background_pdf.path, overlay_bytes)
        filename = f"{job.name.lower().replace(' ', '_')}-linha-{row_number}.pdf"
        item.output_pdf.save(filename, ContentFile(output_bytes), save=False)
        item.status = GenerationItem.Status.COMPLETED
        item.error_message = ""
    except Exception as exc:
        item.status = GenerationItem.Status.FAILED
        item.error_message = _humanize_generation_error(exc)
    item.save()
    return item


def _build_zip_for_job(job: GenerationJob) -> None:
    completed_items = job.items.filter(status=GenerationItem.Status.COMPLETED, output_pdf__gt="")
    if not completed_items.exists():
        return

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in completed_items:
            with item.output_pdf.open("rb") as generated:
                archive.writestr(Path(item.output_pdf.name).name, generated.read())
    job.zip_file.save(f"{job.name.lower().replace(' ', '_')}.zip", ContentFile(buffer.getvalue()), save=False)


@transaction.atomic
def process_job(job: GenerationJob) -> GenerationJob:
    try:
        headers, data_rows = load_excel_rows(job.source_excel.path)
    except Exception as exc:
        job.status = GenerationJob.Status.FAILED
        job.last_error = (
            "Falha ao importar o Excel. Verifique se o arquivo está íntegro, com cabeçalho na primeira linha e formato válido."
        )
        job.save(update_fields=["status", "last_error", "updated_at"])
        return job

    if not job.template.fields.exists():
        job.status = GenerationJob.Status.FAILED
        job.last_error = "O template precisa ter ao menos um campo configurado."
        job.save(update_fields=["status", "last_error", "updated_at"])
        return job

    expected_headers = get_template_expected_headers(job)
    missing_headers = [header for header in expected_headers if header not in headers]

    limit = 3 if job.kind == GenerationJob.Kind.PREVIEW else len(data_rows)
    selected_rows = data_rows[:limit]

    if not data_rows:
        job.status = GenerationJob.Status.FAILED
        job.last_error = "O Excel não possui linhas preenchidas após o cabeçalho."
        job.column_map = {
            "headers": headers,
            "expected_headers": expected_headers,
            "missing_headers": missing_headers,
            "sample_row_numbers": [],
        }
        job.save(update_fields=["status", "last_error", "column_map", "updated_at"])
        return job

    if missing_headers:
        job.status = GenerationJob.Status.FAILED
        job.last_error = (
            "O Excel não possui todos os cabeçalhos esperados pelo template. Faltando: "
            + ", ".join(missing_headers)
        )
        job.column_map = {
            "headers": headers,
            "expected_headers": expected_headers,
            "missing_headers": missing_headers,
            "sample_row_numbers": [row_number for row_number, _ in selected_rows],
        }
        job.save(update_fields=["status", "last_error", "column_map", "updated_at"])
        return job

    job.status = GenerationJob.Status.PROCESSING
    job.total_rows = len(selected_rows)
    job.processed_rows = 0
    job.success_rows = 0
    job.failed_rows = 0
    job.last_error = ""
    job.column_map = {
        "headers": headers,
        "expected_headers": expected_headers,
        "missing_headers": missing_headers,
        "sample_row_numbers": [row_number for row_number, _ in selected_rows],
    }
    job.save(
        update_fields=[
            "status",
            "total_rows",
            "processed_rows",
            "success_rows",
            "failed_rows",
            "last_error",
            "column_map",
            "updated_at",
        ]
    )
    job.items.all().delete()

    for row_number, payload in selected_rows:
        item = _create_item_pdf(job, row_number, payload)
        job.processed_rows += 1
        if item.status == GenerationItem.Status.COMPLETED:
            job.success_rows += 1
        else:
            job.failed_rows += 1
            job.last_error = item.error_message
        job.save(update_fields=["processed_rows", "success_rows", "failed_rows", "last_error", "updated_at"])

    if job.kind == GenerationJob.Kind.FULL:
        try:
            _build_zip_for_job(job)
        except Exception:
            job.status = GenerationJob.Status.FAILED
            job.last_error = "Falha ao exportar o ZIP final do job."
            job.save(update_fields=["status", "last_error", "updated_at"])
            return job

    job.status = GenerationJob.Status.COMPLETED if job.failed_rows == 0 else GenerationJob.Status.FAILED
    job.save(update_fields=["status", "zip_file", "updated_at"])
    return job


def clone_preview_to_full(preview_job: GenerationJob) -> GenerationJob:
    with preview_job.source_excel.open("rb") as source_file:
        full_job = GenerationJob.objects.create(
            user=preview_job.user,
            template=preview_job.template,
            name=f"{preview_job.name} - lote completo",
            source_excel=ContentFile(source_file.read(), name=Path(preview_job.source_excel.name).name),
            kind=GenerationJob.Kind.FULL,
            status=GenerationJob.Status.QUEUED,
        )
    return process_job(full_job)
