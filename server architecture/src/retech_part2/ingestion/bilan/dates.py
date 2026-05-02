"""Date normalisation for BILAN Excel files.

The April-2025 sample contains two failure modes from the source system writing
French DD/MM/YYYY dates into a US-locale Excel:

  * Days 1..12 — Excel parsed "DD/MM/YYYY" as "MM/DD/YYYY" and stored a
    `datetime` cell with day and month swapped (e.g. April 1 → 2025-01-04,
    April 12 → 2025-12-04).
  * Days 13..31 — the swap is impossible (no 13th month), so Excel gave up
    and left the cell as a string like "13/04/2025".

`fix_bilan_date` reverses both. Both formats coexist in the same sheet; the
switchover happens around column 1728 in the sample.
"""
from __future__ import annotations

import datetime
from typing import Union

DateInput = Union[datetime.datetime, datetime.date, str, None]

_STRING_FORMATS: tuple[str, ...] = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y")


def fix_bilan_date(raw: DateInput) -> datetime.date | None:
    """Normalise a BILAN date cell to a real :class:`datetime.date`.

    Returns ``None`` for empty / unparseable input.
    """
    if raw is None:
        return None

    if isinstance(raw, datetime.datetime):
        # Reverse the locale swap: real day is in .month, real month is in .day.
        try:
            return datetime.date(raw.year, raw.day, raw.month)
        except ValueError:
            # Swap produces an invalid date (e.g. month 13) — fall back to as-stored.
            return raw.date()

    # Order matters: datetime is a subclass of date, so check it first.
    if isinstance(raw, datetime.date):
        return raw

    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        for fmt in _STRING_FORMATS:
            try:
                return datetime.datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    return None


def combine_date_time(
    d: datetime.date | None,
    t: datetime.time | None,
) -> datetime.datetime | None:
    """Combine a date and a time into a naive datetime. Date is required."""
    if d is None:
        return None
    return datetime.datetime.combine(d, t or datetime.time(0, 0))
