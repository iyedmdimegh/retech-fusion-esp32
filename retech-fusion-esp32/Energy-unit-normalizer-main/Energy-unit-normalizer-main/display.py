# -*- coding: utf-8 -*-
"""
energy_normalize.display
------------------------
Pretty-print helpers for the unit registry.
"""

from .models import ConversionFactor
from .registry import REGISTRY


def print_factor_table() -> None:
    """Print the full factor table with formulas and sources, grouped by category."""
    categories: dict[str, list[ConversionFactor]] = {}
    for cf in REGISTRY:
        categories.setdefault(cf.category, []).append(cf)

    print("\n  Energy unit → kWh conversion factor table")
    print("  ==========================================\n")
    for cat, items in categories.items():
        print(f"  [{cat}]")
        for cf in items:
            print(f"    {cf.display_name:<42}  factor = {cf.to_kwh:.10g}")
            print(f"      {cf.formula}")
            print(f"      Source: {cf.source}")
            print()


def list_units() -> None:
    """Print a compact list of all supported units with their aliases."""
    categories: dict[str, list[ConversionFactor]] = {}
    for cf in REGISTRY:
        categories.setdefault(cf.category, []).append(cf)

    print("\n  Supported energy units")
    print("  ======================")
    for cat, items in categories.items():
        print(f"\n  {cat}")
        for cf in items:
            aliases = ", ".join(cf.aliases[:4])
            print(f"    {cf.unit_key:<14} — {cf.display_name}")
            print(f"                   aliases: {aliases}")
