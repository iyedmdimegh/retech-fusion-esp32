"""Invoice OCR pipeline.

M8 scope: load pages → preprocess → Tesseract OCR → cache normalised image →
write rows into ``documents.documents`` + ``documents.ocr_pages``. Extraction
status stays at ``pending`` — the structured-extraction tier (Qwen → regex)
plugs in here at M9.

Idempotent: a second ingest of the same SHA-256 returns the existing
``doc_id`` without re-OCRing. Forcing a re-OCR means deleting the
``documents.documents`` row first (cascade clears ``ocr_pages``).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from retech_part2.config import get_settings
from retech_part2.db import get_session_factory
from retech_part2.ingestion.pdf.ocr_tesseract import OcrResult, ocr_page
from retech_part2.ingestion.pdf.preprocessing import (
    SUPPORTED_EXTENSIONS,
    is_pdf,
    load_pages,
    preprocess_for_ocr,
)
from retech_part2.logging import get_logger
from retech_part2.models import Document, OcrPage
from retech_part2.utils.files import ensure_dir
from retech_part2.utils.hashing import sha256_file

log = get_logger("pdf.pipeline")


@dataclass
class PageOutcome:
    page_number: int
    image_path: Path
    text: str
    confidence: float
    language: str


@dataclass
class OcrIngestionResult:
    file_hash: str
    doc_id: UUID
    page_count: int
    duplicate: bool = False
    input_kind: str = "pdf"  # 'pdf' or 'image'
    pages: list[PageOutcome] = field(default_factory=list)


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

async def ingest_invoice(file_path: Path) -> OcrIngestionResult:
    settings = get_settings()
    file_hash = sha256_file(file_path)
    log.info("invoice_ingest_start", file=str(file_path), file_hash=file_hash[:16])

    factory = get_session_factory()

    # 1. dedup
    async with factory() as s:
        existing = (
            await s.execute(select(Document).where(Document.file_hash == file_hash))
        ).scalar_one_or_none()
        if existing is not None:
            log.info(
                "invoice_ingest_duplicate",
                doc_id=str(existing.doc_id),
                extraction_status=existing.extraction_status,
            )
            # Re-hydrate page-level OCR records so callers can report
            # confidences without re-running Tesseract.
            cached_pages = (
                await s.execute(
                    select(OcrPage)
                    .where(OcrPage.doc_id == existing.doc_id)
                    .order_by(OcrPage.page_number)
                )
            ).scalars().all()
            return OcrIngestionResult(
                file_hash=file_hash,
                doc_id=existing.doc_id,
                page_count=existing.page_count or 0,
                duplicate=True,
                input_kind="pdf" if is_pdf(file_path) else "image",
                pages=[
                    PageOutcome(
                        page_number=p.page_number,
                        image_path=Path(p.image_path) if p.image_path else Path(),
                        text=p.text or "",
                        confidence=float(p.ocr_confidence or 0.0),
                        language="cached",  # we don't persist per-page language
                    )
                    for p in cached_pages
                ],
            )

    # 2. load pages (CPU + Poppler, run in thread)
    images = await asyncio.to_thread(load_pages, file_path)
    page_count = len(images)
    input_kind = "pdf" if is_pdf(file_path) else "image"
    log.info("invoice_pages_loaded", page_count=page_count, input_kind=input_kind)

    # 3. insert document row (extraction_status='pending' — M9 will update)
    async with factory() as s:
        doc = Document(
            file_hash=file_hash,
            doc_type="invoice",
            source_file=str(file_path),
            page_count=page_count,
            extraction_status="pending",
        )
        s.add(doc)
        await s.commit()
        await s.refresh(doc)
        doc_id = doc.doc_id

    # 4. cache + OCR each page
    cache_dir = ensure_dir(Path(settings.ocr_cache_path) / file_hash)
    pages: list[PageOutcome] = []

    for i, original_image in enumerate(images, start=1):
        cached_path = cache_dir / f"page_{i}.png"
        # Save the original (RGB) image — extractors in M9 want colour.
        if original_image.mode != "RGB":
            original_image = original_image.convert("RGB")
        original_image.save(cached_path, format="PNG")

        # Preprocess + OCR (sync + CPU-bound)
        ocr_result: OcrResult = await asyncio.to_thread(
            _ocr_one_page, original_image
        )

        async with factory() as s:
            s.add(
                OcrPage(
                    doc_id=doc_id,
                    page_number=i,
                    image_path=str(cached_path),
                    text=ocr_result.text,
                    ocr_confidence=ocr_result.confidence,
                )
            )
            await s.commit()

        pages.append(
            PageOutcome(
                page_number=i,
                image_path=cached_path,
                text=ocr_result.text,
                confidence=ocr_result.confidence,
                language=ocr_result.language,
            )
        )
        log.info(
            "invoice_page_ocr_done",
            page=i,
            confidence=round(ocr_result.confidence, 3),
            language=ocr_result.language,
            text_length=len(ocr_result.text),
        )

    return OcrIngestionResult(
        file_hash=file_hash,
        doc_id=doc_id,
        page_count=page_count,
        duplicate=False,
        input_kind=input_kind,
        pages=pages,
    )


def _ocr_one_page(image) -> OcrResult:
    """Sync helper: preprocess + run Tesseract. Wrapped in to_thread by caller."""
    prepped = preprocess_for_ocr(image)
    return ocr_page(prepped)


# ---------------------------------------------------------------------------
# convenience: list supported extensions for the upload endpoint / watcher.
# ---------------------------------------------------------------------------

def supported_invoice_extensions() -> set[str]:
    return set(SUPPORTED_EXTENSIONS)
