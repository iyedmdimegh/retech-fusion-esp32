# -*- coding: utf-8 -*-
"""
energy_normalize
================
Normalize any energy quantity to kWh (kilowatt-hours).

Each conversion factor is fully traceable: the value, formula, and source
are stored alongside the multiplier so you can audit every result.

Package usage::

    from energy_normalize import convert_to_kwh, convert_batch

    result = convert_to_kwh(1000, "J")
    print(result.result_kwh)   # 0.000277778
    print(result.trace())      # full audit trail

CLI usage::

    python -m energy_normalize 1000 J
    python -m energy_normalize 5.2 MWh
    python -m energy_normalize --list
    python -m energy_normalize --check
"""

import sys

# Ensure UTF-8 output on all platforms (Windows console defaults to cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Public API
from .models import ConversionFactor, ConversionResult
from .registry import REGISTRY, INDEX
from .converter import convert_to_kwh, convert_batch
from .display import print_factor_table, list_units
from .cli import main

__all__ = [
    "convert_to_kwh",
    "convert_batch",
    "ConversionResult",
    "ConversionFactor",
    "REGISTRY",
    "INDEX",
    "print_factor_table",
    "list_units",
    "main",
]
