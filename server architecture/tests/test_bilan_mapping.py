from __future__ import annotations

from pathlib import Path

import pytest

from retech_part2.ingestion.bilan.mapping import (
    MappingEntry,
    load_mappings,
    match,
    match_with_score,
)

SAMPLE_FILE = (
    Path(__file__).parent.parent / "data" / "samples" / "avril-report1_2442026.xlsx"
)


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

def test_yaml_loads_with_many_entries() -> None:
    entries = load_mappings()
    assert len(entries) >= 50, f"got {len(entries)} mapping entries"


def test_metric_ids_are_unique() -> None:
    entries = load_mappings()
    ids = [e.metric_id for e in entries]
    assert len(ids) == len(set(ids))


def test_required_fields_present() -> None:
    for e in load_mappings():
        assert e.metric_id and e.match_text and e.unit and e.category


# ---------------------------------------------------------------------------
# Direct (no-context) matching
# ---------------------------------------------------------------------------

def test_gas_volume_direct_match() -> None:
    e = match("Consommation du gaz naturel moteur en Nm3 (Volume)")
    assert e is not None
    assert e.metric_id == "gas.volume_cumulative"
    assert e.unit == "Nm3"
    assert e.monotonic is True


def test_operating_hours_direct_match() -> None:
    e = match("heure de fonctionnement")
    assert e is not None
    assert e.metric_id == "engine.operating_hours"


def test_empty_parameter_is_mapped() -> None:
    e = match("Puissance électrique nette")
    assert e is not None
    assert e.metric_id == "electrical.power.net"
    assert e.expected_empty is True


def test_low_score_returns_none() -> None:
    assert match("complete garbage that should not match anything ever 12345") is None


def test_empty_input_returns_none() -> None:
    assert match("") is None


# ---------------------------------------------------------------------------
# Whitespace tolerance — the file has labels like 'Energie en kWh ' and
# 'Temperature entrée  (TT02)'. The parser already normalises these; the
# matcher must also accept either form.
# ---------------------------------------------------------------------------

def test_trailing_whitespace_in_input_still_matches() -> None:
    e = match("Energie en kWh ", "Energymeter eau glacée")
    assert e is not None
    assert e.metric_id == "chilled_water.energy_cumulative"


def test_double_space_in_input_still_matches() -> None:
    e = match("Temperature entrée  (TT02)", "Energymeter eau glacée")
    assert e is not None
    assert e.metric_id == "chilled_water.temp_in"


# ---------------------------------------------------------------------------
# Context disambiguation — the same raw_label maps to different metric_ids
# depending on the column-A category.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "category,expected_id",
    [
        ("Energymeter eau glacée", "chilled_water.energy_cumulative"),
        ("Energymeter eau chaude récupéré", "hot_water_recovered.energy_cumulative"),
        ("Energymeter eau chaude Alpha Sanitaire", "hot_water_alpha_sanitaire.energy_cumulative"),
        ("Energymeter eau chaude Alpha", "hot_water_alpha.energy_cumulative"),
        ("Energymeter eau chaude Gamma", "hot_water_gamma.energy_cumulative"),
    ],
)
def test_energie_en_kwh_disambiguated_by_category(category: str, expected_id: str) -> None:
    e = match("Energie en kWh", category)
    assert e is not None, f"no match for category={category!r}"
    assert e.metric_id == expected_id


@pytest.mark.parametrize(
    "category,expected_id",
    [
        ("Energymeter eau chaude  Alpha Sanitaire", "hot_water_alpha_sanitaire.setpoint"),
        ("Energymeter eau chaude Alpha", "hot_water_alpha.setpoint"),
        ("Energymeter eau chaude Gamma", "hot_water_gamma.setpoint"),
    ],
)
def test_setpoint_disambiguated_by_category(category: str, expected_id: str) -> None:
    e = match("Consigne de Température", category)
    assert e is not None
    assert e.metric_id == expected_id


def test_disambiguated_label_without_category_is_ambiguous_or_none() -> None:
    # "Energie en kWh" appears in 4 categories, all with `context`. Without
    # a category we should NOT confidently pick one — return None.
    assert match("Energie en kWh") is None


# ---------------------------------------------------------------------------
# Auxiliary consumption — same raw_label as engine "Energie éléctrique en KWh"
# but disambiguated by category 'Consommation Auxiliare'.
# ---------------------------------------------------------------------------

def test_auxiliary_energy_disambiguated() -> None:
    e = match("Energie éléctrique en KWh", "Consommation Auxiliare")
    assert e is not None
    assert e.metric_id == "electrical.auxiliary.energy_cumulative"


# ---------------------------------------------------------------------------
# Range / monotonic / derived flags surface correctly
# ---------------------------------------------------------------------------

def test_range_is_loaded_as_tuple() -> None:
    e = match("Débit du gaz naturel moteur en Nm3/h")
    assert e is not None
    assert e.range == (0.0, 500.0)


def test_derived_flag_on_efficiency() -> None:
    e = match("Rendement Total %")
    assert e is not None
    assert e.derived is True
    assert e.range == (0.0, 100.0)


# ---------------------------------------------------------------------------
# Integration: every (raw_label, category) pair from the real sample MUST map.
# Spec target: zero unmapped.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not SAMPLE_FILE.exists(), reason=f"sample file not present at {SAMPLE_FILE}")
def test_real_sample_has_zero_unmapped() -> None:
    from retech_part2.ingestion.bilan.parser import parse_bilan

    parsed = parse_bilan(SAMPLE_FILE)
    pairs: set[tuple[str, str]] = {(r.raw_label, r.category) for r in parsed.readings}
    # Add empty-parameter rows that have no readings
    for label, count in parsed.parameter_summary.items():
        if count == 0:
            pairs.add((label, ""))

    unmapped: list[tuple[str, str]] = []
    for label, cat in pairs:
        # Empty parameter "Puissance électrique nette" has no category in the
        # real sheet (its row has empty col A); it's a no-context entry, so
        # match without category.
        if not cat:
            entry = match(label)
        else:
            entry = match(label, cat)
        if entry is None:
            unmapped.append((label, cat))

    assert not unmapped, f"unmapped pairs (target=0):\n  " + "\n  ".join(
        f"raw_label={l!r}  category={c!r}" for l, c in unmapped
    )
