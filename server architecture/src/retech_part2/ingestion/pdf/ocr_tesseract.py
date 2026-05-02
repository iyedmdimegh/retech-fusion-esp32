"""Tesseract OCR for invoice pages.

Runs Tesseract once with French. If the result text contains Arabic-script
characters, retries with ``fra+ara`` and keeps the higher-confidence result.
Returns per-word mean confidence normalised to 0..1.

The Tesseract executable is resolved via the ``TESSERACT_CMD`` setting if
provided, else PATH. Same model for the ``fra`` / ``ara`` traineddata files —
they live next to the binary in ``tessdata/``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pytesseract
from PIL import Image

from retech_part2.config import get_settings

LANG_FRENCH = "fra"
LANG_FRENCH_ARABIC = "fra+ara"
ARABIC_RE = re.compile(r"[؀-ۿ]")


@dataclass
class OcrResult:
    text: str
    confidence: float  # 0..1
    language: str


_configured = False


def _configure_tesseract() -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    _configured = True


def get_tesseract_version() -> str:
    """Return the installed Tesseract version, or raise a helpful error."""
    _configure_tesseract()
    return str(pytesseract.get_tesseract_version())


def list_languages() -> list[str]:
    _configure_tesseract()
    return list(pytesseract.get_languages(config=""))


def ocr_page(image: Image.Image, *, lang: str = LANG_FRENCH) -> OcrResult:
    """Run Tesseract once with ``lang``. If the result shows Arabic chars
    and ``lang`` was French-only, retry with ``fra+ara`` and pick the
    higher-confidence answer.
    """
    _configure_tesseract()
    text, conf = _run(image, lang=lang)
    if lang == LANG_FRENCH and ARABIC_RE.search(text):
        text2, conf2 = _run(image, lang=LANG_FRENCH_ARABIC)
        if conf2 >= conf:
            return OcrResult(text=text2, confidence=conf2, language=LANG_FRENCH_ARABIC)
    return OcrResult(text=text, confidence=conf, language=lang)


def _run(image: Image.Image, *, lang: str) -> tuple[str, float]:
    data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
    text = pytesseract.image_to_string(image, lang=lang)
    # Tesseract returns -1 for non-word entries (lines / paragraphs / blocks).
    # Filter to actual word confidences > 0 for a fair mean.
    confs: list[int] = []
    for c in data.get("conf", []):
        try:
            ci = int(c)
        except (TypeError, ValueError):
            continue
        if ci > 0:
            confs.append(ci)
    mean_conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
    return text, mean_conf
