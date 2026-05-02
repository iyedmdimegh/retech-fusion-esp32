"""Emission-factor constants used to convert energy quantities to kg CO₂.

All values configurable via environment variables (CO2_GAS_FACTOR_KG_PER_NM3,
CO2_GRID_FACTOR_KG_PER_KWH). Defaults documented inline so anyone reading
the code understands the provenance.
"""
from __future__ import annotations

from retech_part2.config import get_settings


def _load() -> tuple[float, float]:
    s = get_settings()
    gas = s.co2_gas_factor_kg_per_nm3
    grid = s.co2_grid_factor_kg_per_kwh
    # Sanity bounds — refuse to use absurd factors from a misconfigured .env.
    if not 1.5 <= gas <= 2.5:
        raise ValueError(f"CO2_GAS_FACTOR_KG_PER_NM3={gas} outside plausible [1.5, 2.5]")
    if not 0.1 <= grid <= 1.0:
        raise ValueError(f"CO2_GRID_FACTOR_KG_PER_KWH={grid} outside plausible [0.1, 1.0]")
    return gas, grid


# Tunisian pipeline gas: derived from PCI 9.082 thermie/Nm³ (BILAN sheet
# header) and CH₄/C₂H₆ stoichiometry. Default ~1.96 kg CO₂ / Nm³.
# STEG grid average emission intensity from 2023 sustainability report.
# Default ~0.47 kg CO₂ / kWh.
KG_CO2_PER_NM3_NATURAL_GAS, KG_CO2_PER_KWH_STEG_GRID = _load()
