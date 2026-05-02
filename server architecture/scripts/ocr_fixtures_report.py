"""M8 verification: run the OCR pipeline on every fixture under
``data/samples/invoices/`` and print a per-file confidence table.

Tells us whether the regex extractor (M9 tier 3) will be a workhorse or just
a fallback — if Tesseract confidence is uniformly high (>90% across pages),
regex on the OCR text will work most of the time and Qwen becomes a polish
layer; if confidence dips below 50% on every page of any fixture, those are
the documents where Qwen needs to step in.

Usage: ``python scripts/ocr_fixtures_report.py``

Idempotent — re-runs hit the documents.documents dedup and report cached
results without re-OCRing.
"""
from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path

from retech_part2._compat import apply_windows_event_loop_policy

apply_windows_event_loop_policy()

from retech_part2.ingestion.pdf.ocr_tesseract import (  # noqa: E402
    get_tesseract_version,
    list_languages,
)
from retech_part2.ingestion.pdf.pipeline import (  # noqa: E402
    SUPPORTED_EXTENSIONS,
    ingest_invoice,
)

LOW_CONF_THRESHOLD = 0.50
HIGH_AVERAGE_THRESHOLD = 0.90
FIXTURES_DIR = Path("data/samples/invoices")


def _check_toolchain() -> bool:
    try:
        version = get_tesseract_version()
    except Exception as e:
        print(f"\n  Tesseract not callable: {type(e).__name__}: {e}", file=sys.stderr)
        print("  Install Tesseract and either put `tesseract` on PATH or set", file=sys.stderr)
        print("  TESSERACT_CMD in .env to the absolute path of tesseract.exe.", file=sys.stderr)
        return False
    print(f"\n  Tesseract version : {version}")
    try:
        langs = sorted(list_languages())
    except Exception as e:
        print(f"  language probe failed: {e}", file=sys.stderr)
        return False
    print(f"  Tesseract langs   : {', '.join(langs)}")
    if "fra" not in langs:
        print(
            "  ⚠ French language pack 'fra' not installed — Tesseract will be",
            file=sys.stderr,
        )
        print("    forced to English only and confidence will be poor.", file=sys.stderr)
    return True


async def _run() -> int:
    if not FIXTURES_DIR.exists():
        print(f"fixtures directory not found: {FIXTURES_DIR}", file=sys.stderr)
        return 2

    fixtures = sorted(
        f for f in FIXTURES_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not fixtures:
        print(f"no fixtures with supported extensions in {FIXTURES_DIR}", file=sys.stderr)
        return 2

    print(f"\nFixtures found: {len(fixtures)}")
    for f in fixtures:
        print(f"  - {f.name}  ({f.stat().st_size:,} bytes)")

    if not _check_toolchain():
        return 3

    print(f"\nRunning OCR pipeline on {len(fixtures)} fixture(s)…\n")

    rows: list[dict] = []
    fully_low_confidence: list[str] = []
    all_page_confidences: list[float] = []

    for path in fixtures:
        t0 = time.perf_counter()
        try:
            result = await ingest_invoice(path)
        except Exception as e:
            print(f"  {path.name}: FAILED — {type(e).__name__}: {e}")
            rows.append(
                {
                    "filename": path.name,
                    "input_kind": "?",
                    "page_count": 0,
                    "page_confidences": [],
                    "languages": [],
                    "duplicate": False,
                    "elapsed_s": 0.0,
                    "error": str(e),
                }
            )
            continue
        elapsed = time.perf_counter() - t0

        page_confs = [round(p.confidence, 3) for p in result.pages]
        languages = [p.language for p in result.pages]
        rows.append(
            {
                "filename": path.name,
                "input_kind": result.input_kind,
                "page_count": result.page_count,
                "page_confidences": page_confs,
                "languages": languages,
                "duplicate": result.duplicate,
                "elapsed_s": elapsed,
                "error": None,
            }
        )

        if page_confs:
            all_page_confidences.extend(page_confs)
            if all(c < LOW_CONF_THRESHOLD for c in page_confs):
                fully_low_confidence.append(path.name)

    # -------- table output --------
    print()
    fname_w = max(20, min(45, max(len(r["filename"]) for r in rows)))
    print(
        f"{'filename'.ljust(fname_w)}  "
        f"{'type':<6} {'pages':>5}  {'mean':>6}  {'min':>6}  {'max':>6}  "
        f"{'lang':<10} {'dup':<4} {'time':>7}"
    )
    print("-" * (fname_w + 60))
    for r in rows:
        if r["error"]:
            print(f"{r['filename'].ljust(fname_w)}  ERROR: {r['error']}")
            continue
        confs = r["page_confidences"]
        mean = statistics.mean(confs) if confs else 0.0
        mn = min(confs) if confs else 0.0
        mx = max(confs) if confs else 0.0
        # Most-common language across pages
        lang = max(set(r["languages"]), key=r["languages"].count) if r["languages"] else "-"
        dup_marker = "yes" if r["duplicate"] else "no"
        print(
            f"{r['filename'].ljust(fname_w)}  "
            f"{r['input_kind']:<6} {r['page_count']:>5}  "
            f"{mean:>6.1%}  {mn:>6.1%}  {mx:>6.1%}  "
            f"{lang:<10} {dup_marker:<4} {r['elapsed_s']:>6.1f}s"
        )

    # -------- per-page detail when interesting --------
    detailed = [r for r in rows if r["page_count"] > 1 and not r["error"]]
    if detailed:
        print(f"\nPer-page confidence (multi-page fixtures):")
        for r in detailed:
            print(f"  {r['filename']}:")
            for i, (c, lang) in enumerate(zip(r["page_confidences"], r["languages"]), start=1):
                print(f"    page {i:>2}: conf={c:.1%}  lang={lang}")

    # -------- aggregate signal for M9 prioritisation --------
    print()
    if all_page_confidences:
        overall_mean = statistics.mean(all_page_confidences)
        overall_median = statistics.median(all_page_confidences)
        n_low = sum(1 for c in all_page_confidences if c < LOW_CONF_THRESHOLD)
        print(f"Overall pages OCR'd : {len(all_page_confidences)}")
        print(f"Mean confidence     : {overall_mean:.1%}")
        print(f"Median confidence   : {overall_median:.1%}")
        print(
            f"Pages below {LOW_CONF_THRESHOLD:.0%}    : "
            f"{n_low}  ({n_low / len(all_page_confidences):.1%} of total)"
        )
    else:
        print("Overall confidence : no pages OCR'd")

    if fully_low_confidence:
        print(f"\n⚠ Fixtures where EVERY page is below {LOW_CONF_THRESHOLD:.0%} (Qwen-needed):")
        for name in fully_low_confidence:
            print(f"  - {name}")
    else:
        print(f"\nNo fixture had all pages below {LOW_CONF_THRESHOLD:.0%}.")

    if all_page_confidences and statistics.mean(all_page_confidences) > HIGH_AVERAGE_THRESHOLD:
        print(
            f"\nMean confidence > {HIGH_AVERAGE_THRESHOLD:.0%}: regex extractor on OCR text"
            f" should handle most documents; Qwen becomes a polish layer."
        )
    elif all_page_confidences:
        print(
            f"\nMean confidence ≤ {HIGH_AVERAGE_THRESHOLD:.0%}: Qwen will need to be a"
            f" workhorse, not just a fallback."
        )

    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
