"""Image loading + OCR preprocessing.

Two entry points:
  * :func:`load_pages` — uniform per-page image list across PDFs and loose
    images, so downstream OCR / extraction code never branches on input type.
  * :func:`preprocess_for_ocr` — grayscale → deskew → adaptive threshold →
    light denoise. Tuned for Tesseract on scanned French invoices.

Image formats accepted as first-class invoice inputs (per project decision):
``.pdf .jpg .jpeg .png .tiff .tif .webp``. PDFs are rendered to images via
pdf2image (Poppler under the hood); loose images are opened with PIL,
converted to RGB, and returned as a single-page list.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pdf2image
from PIL import Image

from retech_part2.config import get_settings

# PIL's default DOS-protection limit is ~178M pixels; some scanned PDFs render
# above that at 300 DPI. We control the inputs (operator-uploaded invoices, not
# adversarial) so raise the cap rather than refuse to load. 500M pixels covers
# anything we've seen so far.
Image.MAX_IMAGE_PIXELS = 500_000_000

PDF_EXTENSIONS: frozenset[str] = frozenset({".pdf"})
IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp"}
)
SUPPORTED_EXTENSIONS: frozenset[str] = PDF_EXTENSIONS | IMAGE_EXTENSIONS


def render_pdf_to_images(pdf_path: Path, *, dpi: int | None = None) -> list[Image.Image]:
    settings = get_settings()
    dpi = dpi if dpi is not None else settings.pdf_render_dpi
    kwargs: dict[str, object] = {"dpi": dpi}
    if settings.poppler_path:
        kwargs["poppler_path"] = settings.poppler_path
    return pdf2image.convert_from_path(str(pdf_path), **kwargs)


def load_pages(file_path: Path, *, dpi: int | None = None) -> list[Image.Image]:
    """Return per-page PIL images regardless of input type."""
    ext = file_path.suffix.lower()
    if ext in PDF_EXTENSIONS:
        return render_pdf_to_images(file_path, dpi=dpi)
    if ext in IMAGE_EXTENSIONS:
        img = Image.open(file_path)
        img.load()
        if img.mode != "RGB":
            img = img.convert("RGB")
        return [img]
    raise ValueError(
        f"unsupported extension {ext!r}; expected one of {sorted(SUPPORTED_EXTENSIONS)}"
    )


def is_pdf(file_path: Path) -> bool:
    return file_path.suffix.lower() in PDF_EXTENSIONS


# ---------------------------------------------------------------------------
# preprocessing for Tesseract
# ---------------------------------------------------------------------------

def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """Grayscale → deskew → adaptive threshold → light denoise.

    Operates on a copy; does not mutate the input. Returns a binarised
    (1-bit-equivalent, mode='L') image suitable for Tesseract. The original
    RGB image should be kept around for downstream extractors that benefit
    from colour (Qwen vision in M9).
    """
    arr = np.array(image.convert("L"))
    arr = _deskew(arr)
    arr = cv2.adaptiveThreshold(
        arr,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY,
        blockSize=31,
        C=10,
    )
    arr = cv2.fastNlMeansDenoising(arr, h=10)
    return Image.fromarray(arr)


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Estimate page skew via minAreaRect of edge pixels and rotate to flat."""
    edges = cv2.Canny(gray, 50, 150)
    coords = np.column_stack(np.where(edges > 0))
    if len(coords) < 100:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) < 0.5:
        return gray
    h, w = gray.shape
    rotation_matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(
        gray,
        rotation_matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
