from __future__ import annotations

import unicodedata

from fontTools.ttLib import TTFont

PT_BR_REQUIRED_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÁÂÃÇÉÊÍÓÔÕÚàáâãçéêíóôõúÊêÔôÜü0123456789.,;:-_()/'\"ºª& "


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value or "")


# Rótulo por faixa de peso (escala OpenType/CSS usWeightClass, 100-900). Serve
# de reserva quando o arquivo não traz um nome de subfamília utilizável.
WEIGHT_LABELS = {
    100: "Thin",
    200: "Extra Light",
    300: "Light",
    400: "Regular",
    500: "Medium",
    600: "SemiBold",
    700: "Bold",
    800: "Extra Bold",
    900: "Black",
}


def _nearest_weight_label(weight: int) -> str:
    nearest = min(WEIGHT_LABELS, key=lambda step: abs(step - weight))
    return WEIGHT_LABELS[nearest]


def _detect_weight_and_style(font: TTFont) -> tuple[int, bool]:
    """Peso (100-900) e itálico, lidos da mesma fonte que os navegadores e o
    CSS usam: a tabela OS/2. `head.macStyle` entra só como reforço quando o
    OS/2 não deixa claro (algumas fontes utilitárias/CJK vêm sem OS/2)."""
    weight = 400
    is_italic = False
    os2 = font.get("OS/2")
    if os2 is not None:
        raw_weight = getattr(os2, "usWeightClass", 400) or 400
        weight = min(max(int(raw_weight), 100), 900)
        # fsSelection: bit 0 = itálico, bit 5 = negrito (ignorado aqui — o
        # peso numérico já cobre "negrito"), bit 6 = regular.
        is_italic = bool(getattr(os2, "fsSelection", 0) & 0x01)
    head = font.get("head")
    if head is not None:
        mac_style = getattr(head, "macStyle", 0) or 0
        if not is_italic:
            is_italic = bool(mac_style & 0x02)
        if os2 is None and mac_style & 0x01:
            weight = 700
    return weight, is_italic


# Sinônimos que fontes usam para o próprio peso regular (400) sem itálico —
# "Book" (DejaVu), "Roman", "Normal", "Text"... todos a mesma coisa dita de
# jeito diferente. Normalizar para "Regular" evita um rótulo que só quem
# desenha fontes reconhece de cara.
REGULAR_SYNONYMS = {"book", "roman", "normal", "text", "upright", "regular"}


def _detect_family_and_variant(names: dict[int, str], weight: int, is_italic: bool) -> dict:
    # nameID 16/17 (família/subfamília "tipográficas") são a fonte correta
    # para agrupar pesos que fogem do RIBBI clássico (Regular/Bold/Italic/
    # Bold Italic); nameID 1/2 é a reserva, e cobre a maioria das fontes.
    family = names.get(16) or names.get(1) or ""
    variant = names.get(17) or names.get(2) or ""
    if variant and weight == 400 and not is_italic and variant.strip().lower() in REGULAR_SYNONYMS:
        variant = "Regular"
    if not variant:
        variant = _nearest_weight_label(weight)
        if is_italic:
            variant = f"{variant} Italic" if variant != "Regular" else "Italic"
    return {"family_name": family, "variant_label": variant}


def inspect_font_file(font_path: str) -> dict:
    font = TTFont(font_path)
    try:
        names = {}
        for record in font["name"].names:
            if record.nameID in {1, 2, 4, 6, 16, 17}:
                try:
                    names[record.nameID] = record.toUnicode()
                except Exception:
                    continue

        cmap = set()
        for table in font["cmap"].tables:
            cmap.update(table.cmap.keys())

        required_chars = _normalize_text(PT_BR_REQUIRED_CHARS)
        missing_required_chars = sorted({char for char in required_chars if ord(char) not in cmap})

        weight, is_italic = _detect_weight_and_style(font)
        detected = _detect_family_and_variant(names, weight, is_italic)

        return {
            "family_name": names.get(1, ""),
            "subfamily_name": names.get(2, ""),
            "full_name": names.get(4, ""),
            "postscript_name": names.get(6, ""),
            "typographic_family_name": names.get(16, ""),
            "typographic_subfamily_name": names.get(17, ""),
            "glyph_count": len(cmap),
            "supports_pt_br_basic": not missing_required_chars,
            "missing_pt_br_basic_chars": missing_required_chars,
            "weight": weight,
            "is_italic": is_italic,
            "detected_family": detected["family_name"],
            "detected_variant": detected["variant_label"],
        }
    finally:
        font.close()
