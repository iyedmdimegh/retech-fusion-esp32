"""Semantic mapping: raw BILAN labels → canonical metric IDs.

The YAML lives next to this module. Loaded once at import time.

Match rules (from spec):
  - Direct match (no `context` on the entry): label fuzzy-score must be ≥ 90.
  - Disambiguated match (entry has `context`): label score ≥ 80 AND
    context score ≥ 80 (so two entries sharing the same `match_text` can be
    distinguished by their column-A category).
  - Below threshold → ``None``; the caller should record an unmapped warning.

Fuzzy scoring uses ``rapidfuzz.fuzz.token_sort_ratio`` after normalising both
sides (whitespace collapse + casefold). The spec wording said "token-set
ratio" but that scores any subset at 100 — so e.g. "Energie en kWh" would
fuzzy-match the much longer "Energie éléctrique au borne de l'alternateur
en KWh" at 100, and "Energymeter eau chaude Alpha" would tie with
"…Alpha Sanitaire" for context. ``token_sort_ratio`` penalises length
differences, which is what the spec actually wants for disambiguation.
Whitespace collapsing in `_normalize` covers the trailing-space / double-space
anomalies that `token_set_ratio` was originally chosen to absorb.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from rapidfuzz import fuzz

DIRECT_MATCH_THRESHOLD = 90
DISAMBIGUATED_LABEL_THRESHOLD = 80
DISAMBIGUATED_CONTEXT_THRESHOLD = 80

WHITESPACE_RE = re.compile(r"\s+")
YAML_PATH = Path(__file__).with_name("mapping.yaml")


@dataclass(frozen=True)
class MappingEntry:
    metric_id: str
    match_text: str
    unit: str
    category: str
    context: str | None = None
    range: tuple[float, float] | None = None
    monotonic: bool = False
    expected_empty: bool = False
    derived: bool = False
    # cached normalised forms (computed at load time)
    _norm_match_text: str = field(default="", repr=False, compare=False)
    _norm_context: str | None = field(default=None, repr=False, compare=False)


@dataclass
class MatchResult:
    entry: MappingEntry
    label_score: float
    context_score: float | None  # None if entry has no context


# ---------------------------------------------------------------------------
# normalisation
# ---------------------------------------------------------------------------

def _normalize(s: str | None) -> str:
    if s is None:
        return ""
    return WHITESPACE_RE.sub(" ", s).strip().casefold()


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

def _coerce_range(raw: Any) -> tuple[float, float] | None:
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        return (float(raw[0]), float(raw[1]))
    raise ValueError(f"invalid range value: {raw!r}")


def _build_entry(raw: dict) -> MappingEntry:
    # Required fields
    try:
        match_text = raw["match_text"]
        metric_id = raw["metric_id"]
        unit = raw["unit"]
        category = raw["category"]
    except KeyError as e:
        raise ValueError(f"mapping entry missing required key {e}: {raw!r}") from e

    context = raw.get("context")
    return MappingEntry(
        metric_id=metric_id,
        match_text=match_text,
        unit=unit,
        category=category,
        context=context,
        range=_coerce_range(raw.get("range")),
        monotonic=bool(raw.get("monotonic", False)),
        expected_empty=bool(raw.get("expected_empty", False)),
        derived=bool(raw.get("derived", False)),
        _norm_match_text=_normalize(match_text),
        _norm_context=_normalize(context) if context else None,
    )


@lru_cache
def load_mappings(path: Path | None = None) -> tuple[MappingEntry, ...]:
    """Parse ``mapping.yaml`` and return the entries (cached)."""
    p = path or YAML_PATH
    with p.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    raw_entries = doc.get("mappings") or []
    if not raw_entries:
        raise ValueError(f"no mappings found in {p}")

    entries: list[MappingEntry] = []
    seen_metric_ids: set[str] = set()
    for raw in raw_entries:
        entry = _build_entry(raw)
        if entry.metric_id in seen_metric_ids:
            raise ValueError(f"duplicate metric_id in YAML: {entry.metric_id}")
        seen_metric_ids.add(entry.metric_id)
        entries.append(entry)
    return tuple(entries)


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------

def match(raw_label: str, category: str | None = None) -> MappingEntry | None:
    """Best-fit YAML entry for a raw column-B label, optionally disambiguated
    by the column-A category. Returns ``None`` below threshold.
    """
    result = match_with_score(raw_label, category)
    return result.entry if result else None


def match_with_score(
    raw_label: str, category: str | None = None
) -> MatchResult | None:
    """Like :func:`match` but also returns the label / context scores —
    useful for diagnostics and for the CLI summary table.
    """
    if not raw_label:
        return None

    norm_label = _normalize(raw_label)
    norm_cat = _normalize(category) if category else ""

    best: MatchResult | None = None

    for entry in load_mappings():
        label_score = fuzz.token_sort_ratio(norm_label, entry._norm_match_text)

        if entry.context is None:
            # Direct entry — no disambiguation needed; high label threshold.
            if label_score < DIRECT_MATCH_THRESHOLD:
                continue
            ctx_score: float | None = None
            ranking = (label_score, 0.0)
        else:
            # Disambiguated entry — require both label AND context to match.
            if label_score < DISAMBIGUATED_LABEL_THRESHOLD:
                continue
            ctx_score = fuzz.token_sort_ratio(norm_cat, entry._norm_context or "")
            if ctx_score < DISAMBIGUATED_CONTEXT_THRESHOLD:
                continue
            # Rank by combined score; ties broken by context score.
            ranking = (label_score + ctx_score, ctx_score)

        if best is None or ranking > (best.label_score + (best.context_score or 0), (best.context_score or 0)):
            best = MatchResult(entry=entry, label_score=float(label_score), context_score=float(ctx_score) if ctx_score is not None else None)

    return best


# ---------------------------------------------------------------------------
# CLI: python -m retech_part2.ingestion.bilan.mapping <xlsx>
# ---------------------------------------------------------------------------

def _print_match_table(xlsx_path: Path) -> int:
    """Run the parser on `xlsx_path` and print every distinct (raw_label, category)
    pair → matched metric_id (or UNMAPPED). Returns exit code: 0 if zero unmapped.
    """
    from retech_part2.ingestion.bilan.parser import parse_bilan

    parsed = parse_bilan(xlsx_path)
    pairs: dict[tuple[str, str], int] = {}
    for r in parsed.readings:
        pairs[(r.raw_label, r.category)] = pairs.get((r.raw_label, r.category), 0) + 1
    # Include empty-parameter entries too
    for label in parsed.parameter_summary:
        if parsed.parameter_summary[label] == 0:
            pairs.setdefault((label, ""), 0)

    label_w = min(max((len(k[0]) for k in pairs), default=20), 55)
    cat_w = min(max((len(k[1]) for k in pairs), default=10), 40)

    print(f"\nFile : {xlsx_path.name}")
    print(f"Distinct (raw_label, category) pairs: {len(pairs)}\n")
    header = f"{'raw_label'.ljust(label_w)}  {'category'.ljust(cat_w)}  {'count':>7}  {'metric_id'}"
    print(header)
    print("-" * len(header))

    unmapped: list[tuple[str, str]] = []
    for (label, cat), count in sorted(pairs.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        result = match_with_score(label, cat)
        if result is None:
            metric = "UNMAPPED"
            unmapped.append((label, cat))
        else:
            metric = result.entry.metric_id
        l = label if len(label) <= label_w else label[: label_w - 1] + "…"
        c = cat if len(cat) <= cat_w else cat[: cat_w - 1] + "…"
        print(f"{l.ljust(label_w)}  {c.ljust(cat_w)}  {count:>7,}  {metric}")

    print()
    print(f"Total pairs    : {len(pairs)}")
    print(f"Mapped         : {len(pairs) - len(unmapped)}")
    print(f"Unmapped       : {len(unmapped)}")
    if unmapped:
        print("\nUNMAPPED:")
        for label, cat in unmapped:
            print(f"  - raw_label={label!r}  category={cat!r}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print(
            "usage: python -m retech_part2.ingestion.bilan.mapping <path-to-xlsx>",
            file=sys.stderr,
        )
        return 2
    path = Path(args[0]).resolve()
    if not path.exists():
        print(f"file not found: {path}", file=sys.stderr)
        return 1
    return _print_match_table(path)


if __name__ == "__main__":
    raise SystemExit(main())
