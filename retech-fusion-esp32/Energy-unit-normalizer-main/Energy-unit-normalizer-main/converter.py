# -*- coding: utf-8 -*-
"""
energy_normalize.converter
--------------------------
Core conversion functions: single and batch energy-to-kWh conversions.
"""

from .models import ConversionResult
from .registry import INDEX


def convert_to_kwh(value: float, unit: str) -> ConversionResult:
    """Convert *value* in *unit* to kWh, returning a traceable ConversionResult."""
    key = unit.strip().lower()
    factor = INDEX.get(key)
    if factor is None:
        raise KeyError(
            f"Unknown unit: '{unit}'\n"
            f"  Run with --list to see all supported units."
        )
    return ConversionResult(
        input_value=value,
        input_unit_raw=unit,
        matched_unit=factor,
        result_kwh=value * factor.to_kwh,
    )


def convert_batch(pairs: list[tuple[float, str]]) -> list[ConversionResult]:
    """Convert a list of (value, unit) tuples."""
    return [convert_to_kwh(v, u) for v, u in pairs]
