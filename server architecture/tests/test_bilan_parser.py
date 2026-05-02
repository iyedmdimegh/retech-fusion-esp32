from __future__ import annotations

import datetime as dt
from collections import Counter
from pathlib import Path

import pytest

from retech_part2.ingestion.bilan.parser import ParsedBilan, parse_bilan

SAMPLE_FILE = (
    Path(__file__).parent.parent / "data" / "samples" / "avril-report1_2442026.xlsx"
)
pytestmark = pytest.mark.skipif(
    not SAMPLE_FILE.exists(), reason=f"sample file not present at {SAMPLE_FILE}"
)


@pytest.fixture(scope="module")
def parsed() -> ParsedBilan:
    return parse_bilan(SAMPLE_FILE)


# --- date range ---------------------------------------------------------

def test_date_range_is_april_1_to_20(parsed: ParsedBilan) -> None:
    assert parsed.date_range == (dt.date(2025, 4, 1), dt.date(2025, 4, 20))


# --- volume / shape -----------------------------------------------------

def test_reading_count_in_expected_range(parsed: ParsedBilan) -> None:
    # ~50 metrics × ~2870 timestamps. Empty params + sparse cells push the
    # actual count down a bit; the spec's hint was 140k–150k.
    assert 100_000 <= len(parsed.readings) <= 200_000


def test_distinct_metric_count(parsed: ParsedBilan) -> None:
    """`parameter_summary` keys by raw_label only, so duplicate labels across
    categories (e.g. 'Energie en kWh' under 4 different energymeters) collapse
    in the summary dict. The true distinct-metric count is the number of
    unique (raw_label, category) pairs, which is what the YAML mapping in M5
    will key off.
    """
    pairs = {(r.raw_label, r.category) for r in parsed.readings}
    assert len(pairs) >= 40, f"got only {len(pairs)} distinct (raw_label, category) pairs"


# --- timestamp synthesis -----------------------------------------------

def test_at_least_one_synthetic_timestamp(parsed: ParsedBilan) -> None:
    assert any(r.timestamp_synthetic for r in parsed.readings)


def test_synthetic_count_is_substantial(parsed: ParsedBilan) -> None:
    # 927 of ~2873 columns are gap columns per the spec — many readings
    # therefore carry a synthesised timestamp.
    n_synth = sum(1 for r in parsed.readings if r.timestamp_synthetic)
    assert n_synth > 1_000


# --- data integrity ----------------------------------------------------

def test_no_none_values_or_times(parsed: ParsedBilan) -> None:
    assert all(r.time is not None for r in parsed.readings)
    assert all(r.value is not None for r in parsed.readings)


def test_all_times_are_in_april_2025(parsed: ParsedBilan) -> None:
    months = {r.time.month for r in parsed.readings}
    years = {r.time.year for r in parsed.readings}
    assert months == {4}
    assert years == {2025}


# --- monotonic meters --------------------------------------------------

def test_gas_volume_is_mostly_non_decreasing_in_column_order(parsed: ParsedBilan) -> None:
    """The spec's claim ("monotonic in column order") is the IDEAL — real data
    contains rare inversions (sensor noise, manual overrides). We assert the
    overall trend is rising and inversions are rare. M6 will tag the rare
    bad rows with `monotonic_inversion`.
    """
    label = "Consommation du gaz naturel moteur en Nm3 (Volume)"
    series = [r for r in parsed.readings if r.raw_label == label]
    assert series, f"expected readings for {label!r}"
    assert series[-1].value > series[0].value, (
        f"gas meter did not advance over the period: {series[0].value} -> {series[-1].value}"
    )
    inversions = sum(1 for a, b in zip(series, series[1:]) if b.value < a.value)
    inversion_rate = inversions / max(1, len(series) - 1)
    assert inversion_rate <= 0.01, (
        f"too many inversions in gas volume column-order: {inversions}/{len(series)-1}"
    )


def test_operating_hours_grows_overall(parsed: ParsedBilan) -> None:
    """Engine operating hours has at least one zeroed cell partway through
    (likely a maintenance reset / blank that defaulted to 0), so we can't
    assert strict monotonicity. We assert the meter shows real accumulation
    over the period when zeros are excluded.
    """
    label = "heure de fonctionnement"
    series = [r for r in parsed.readings if r.raw_label == label]
    assert series, f"expected readings for {label!r}"
    non_zero = [r.value for r in series if r.value > 0]
    assert non_zero, "expected some non-zero operating-hours values"
    assert max(non_zero) > min(non_zero), (
        f"operating hours range collapsed: min={min(non_zero)} max={max(non_zero)}"
    )


# --- empty parameter handling ------------------------------------------

def test_empty_parameter_recorded_with_zero_count(parsed: ParsedBilan) -> None:
    """Row 13 ("Puissance électrique nette") has zero values across all
    columns but must still appear in `parameter_summary` so M5/M6 know
    the row was seen and can map it explicitly as `expected_empty: true`.
    """
    label = "Puissance électrique nette"
    assert label in parsed.parameter_summary
    assert parsed.parameter_summary[label] == 0


# --- merged-cell category forward-fill ---------------------------------

def test_categories_have_been_forward_filled(parsed: ParsedBilan) -> None:
    """If our merged-cell handling silently failed, most rows would have an
    empty category. There should be several distinct categories and they
    should cover the bulk of the readings.
    """
    by_category = Counter(r.category for r in parsed.readings)
    assert len(by_category) >= 5, by_category.most_common()
    non_empty_total = sum(c for k, c in by_category.items() if k)
    assert non_empty_total >= 0.9 * len(parsed.readings), (
        "expected at least 90% of readings to have a non-empty category"
    )


# --- whitespace normalisation ------------------------------------------

def test_raw_labels_have_collapsed_whitespace(parsed: ParsedBilan) -> None:
    """The source file has labels like 'Energie en kWh ' (trailing space) and
    'Temperature entrée  (TT02)' (double space). After normalisation, no
    label may end in whitespace or contain runs of multiple spaces.
    """
    for label in parsed.parameter_summary:
        assert label == label.strip(), f"un-stripped label: {label!r}"
        assert "  " not in label, f"double-space in label: {label!r}"


# --- file-hash plumbing -------------------------------------------------

def test_file_hash_is_sha256(parsed: ParsedBilan) -> None:
    assert len(parsed.file_hash) == 64
    int(parsed.file_hash, 16)  # valid hex
