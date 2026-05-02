# -*- coding: utf-8 -*-
"""
energy_normalize.models
-----------------------
Data models for energy unit conversion.
"""

from dataclasses import dataclass


@dataclass
class ConversionFactor:
    """One row in the unit registry."""
    unit_key: str           # canonical lookup key (lowercase, no spaces)
    display_name: str       # pretty name shown to users
    aliases: list[str]      # alternate spellings / abbreviations
    to_kwh: float           # multiply input value by this to get kWh
    formula: str            # human-readable derivation
    source: str             # authoritative reference
    category: str           # SI / Electrical / Thermal / Fossil / Nuclear / Mechanical


@dataclass
class ConversionResult:
    """Result of a single energy-to-kWh conversion, with full traceability."""
    input_value: float
    input_unit_raw: str
    matched_unit: ConversionFactor
    result_kwh: float

    def trace(self) -> str:
        lines = [
            "",
            "  +-- Conversion trace ---------------------------------------------------+",
            f"  |  Input        : {self.input_value:g} {self.input_unit_raw}",
            f"  |  Matched unit : {self.matched_unit.display_name}",
            f"  |  Factor->kWh  : {self.matched_unit.to_kwh:.10g}",
            f"  |  Formula      : {self.matched_unit.formula}",
            f"  |  Source       : {self.matched_unit.source}",
            f"  |  Category     : {self.matched_unit.category}",
            f"  |  Result       : {self.result_kwh:g} kWh",
            "  +-----------------------------------------------------------------------+",
            "",
        ]
        return "\n".join(lines)
