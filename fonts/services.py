from __future__ import annotations

import unicodedata
from pathlib import Path

from fontTools.ttLib import TTFont


PT_BR_REQUIRED_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÁÂÃÇÉÊÍÓÔÕÚàáâãçéêíóôõúÊêÔôÜü0123456789.,;:-_()/'\"ºª& "


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value or "")


def inspect_font_file(font_path: str) -> dict:
    font = TTFont(font_path)
    try:
        names = {}
        for record in font["name"].names:
            if record.nameID in {1, 2, 4, 6}:
                try:
                    names[record.nameID] = record.toUnicode()
                except Exception:
                    continue

        cmap = set()
        for table in font["cmap"].tables:
            cmap.update(table.cmap.keys())

        required_chars = _normalize_text(PT_BR_REQUIRED_CHARS)
        missing_required_chars = sorted({char for char in required_chars if ord(char) not in cmap})

        return {
            "family_name": names.get(1, ""),
            "subfamily_name": names.get(2, ""),
            "full_name": names.get(4, ""),
            "postscript_name": names.get(6, ""),
            "glyph_count": len(cmap),
            "supports_pt_br_basic": not missing_required_chars,
            "missing_pt_br_basic_chars": missing_required_chars,
        }
    finally:
        font.close()
