# -*- coding: utf-8 -*-
"""
energy_normalize.cli
--------------------
Command-line interface for energy normalization.
"""

import argparse
import sys
from typing import Optional

from .converter import convert_to_kwh
from .display import list_units, print_factor_table


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="energy_normalize",
        description=(
            "Normalize energy quantities to kWh with traceable conversion factors.\n"
            "Examples:\n"
            "  energy_normalize 1000 J\n"
            "  energy_normalize 5.2 MWh\n"
            "  energy_normalize 100 BTU\n"
            "  energy_normalize --list\n"
            "  energy_normalize --check"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("value", nargs="?", type=float, help="Numeric quantity to convert")
    p.add_argument("unit", nargs="?", type=str, help="Source unit (e.g. J, MJ, BTU, MWh)")
    p.add_argument("--list", action="store_true", help="List all supported units")
    p.add_argument("--check", action="store_true", help="Print full factor table with formulas and sources")
    p.add_argument("--quiet", "-q", action="store_true", help="Print only the numeric result (no trace)")
    return p


def main(argv: Optional[list[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list:
        list_units()
        return

    if args.check:
        print_factor_table()
        return

    if args.value is None or args.unit is None:
        parser.print_help()
        sys.exit(1)

    try:
        result = convert_to_kwh(args.value, args.unit)
    except KeyError as exc:
        print(f"\n  Error: {exc}\n", file=sys.stderr)
        sys.exit(2)

    if args.quiet:
        print(result.result_kwh)
    else:
        print(result.trace())
