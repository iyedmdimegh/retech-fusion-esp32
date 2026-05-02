# -*- coding: utf-8 -*-
"""
energy_normalize.registry
-------------------------
Unit registry: every supported energy unit with its conversion factor to kWh.

Anchor
------
1 kWh = 3 600 000 J  (exactly, by SI definition of the watt)
1 W   = 1 J/s
1 kWh = 1000 W × 3600 s = 3.6 × 10^6 J

All other conversions derive from this anchor.
"""

from .models import ConversionFactor


# ---------------------------------------------------------------------------
# Authoritative sources
# ---------------------------------------------------------------------------

_SI_SOURCE = "SI / BIPM (Bureau International des Poids et Mesures)"
_NIST_SOURCE = "NIST SP 811 (2008 edition)"
_IEA_SOURCE = "IEA Energy Statistics Manual (2005)"
_ASHRAE_SOURCE = "ASHRAE Handbook of Fundamentals (2017)"
_IEEE_SOURCE = "IEEE Std 100-2000 (The Authoritative Dictionary of IEEE Standards)"


# ---------------------------------------------------------------------------
# SI base / derived
# ---------------------------------------------------------------------------

_SI_UNITS: list[ConversionFactor] = [
    ConversionFactor(
        unit_key="j",
        display_name="Joule (J)",
        aliases=["joule", "joules"],
        to_kwh=1 / 3_600_000,
        formula="1 kWh = 3 600 000 J  →  factor = 1/3 600 000",
        source=_SI_SOURCE,
        category="SI",
    ),
    ConversionFactor(
        unit_key="kj",
        display_name="Kilojoule (kJ)",
        aliases=["kilojoule", "kilojoules"],
        to_kwh=1 / 3_600,
        formula="1 kJ = 1000 J; 1 kWh = 3600 kJ  →  factor = 1/3600",
        source=_SI_SOURCE,
        category="SI",
    ),
    ConversionFactor(
        unit_key="mj",
        display_name="Megajoule (MJ)",
        aliases=["megajoule", "megajoules"],
        to_kwh=1 / 3.6,
        formula="1 MJ = 10^6 J; 1 kWh = 3.6 MJ  →  factor = 1/3.6",
        source=_SI_SOURCE,
        category="SI",
    ),
    ConversionFactor(
        unit_key="gj",
        display_name="Gigajoule (GJ)",
        aliases=["gigajoule", "gigajoules"],
        to_kwh=1_000 / 3.6,
        formula="1 GJ = 10^9 J = 1000 MJ; 1 MJ = 1/3.6 kWh  →  factor = 1000/3.6 ≈ 277.778",
        source=_SI_SOURCE,
        category="SI",
    ),
    ConversionFactor(
        unit_key="tj",
        display_name="Terajoule (TJ)",
        aliases=["terajoule", "terajoules"],
        to_kwh=1_000_000 / 3.6,
        formula="1 TJ = 10^12 J = 10^6 MJ; factor = 10^6/3.6 ≈ 277 777.778",
        source=_SI_SOURCE,
        category="SI",
    ),
    ConversionFactor(
        unit_key="pj",
        display_name="Petajoule (PJ)",
        aliases=["petajoule", "petajoules"],
        to_kwh=1e9 / 3.6,
        formula="1 PJ = 10^15 J = 10^9 MJ; factor = 10^9/3.6 ≈ 2.7778 × 10^8",
        source=_SI_SOURCE,
        category="SI",
    ),
]


# ---------------------------------------------------------------------------
# Electrical (watt-hour family)
# ---------------------------------------------------------------------------

_ELECTRICAL_UNITS: list[ConversionFactor] = [
    ConversionFactor(
        unit_key="wh",
        display_name="Watt-hour (Wh)",
        aliases=["watt-hour", "watt hour", "watthour", "watthours"],
        to_kwh=0.001,
        formula="1 kWh = 1000 Wh  →  factor = 0.001",
        source=_IEEE_SOURCE,
        category="Electrical",
    ),
    ConversionFactor(
        unit_key="kwh",
        display_name="Kilowatt-hour (kWh)  [canonical unit]",
        aliases=["kilowatt-hour", "kilowatt hour", "kilowatthour", "kilowatthours"],
        to_kwh=1.0,
        formula="Canonical unit; factor = 1",
        source=_IEEE_SOURCE,
        category="Electrical",
    ),
    ConversionFactor(
        unit_key="mwh",
        display_name="Megawatt-hour (MWh)",
        aliases=["megawatt-hour", "megawatt hour", "megawatthour"],
        to_kwh=1_000.0,
        formula="1 MWh = 1000 kWh  →  factor = 1000",
        source=_IEEE_SOURCE,
        category="Electrical",
    ),
    ConversionFactor(
        unit_key="gwh",
        display_name="Gigawatt-hour (GWh)",
        aliases=["gigawatt-hour", "gigawatt hour", "gigawatthour"],
        to_kwh=1_000_000.0,
        formula="1 GWh = 10^6 kWh  →  factor = 1 000 000",
        source=_IEEE_SOURCE,
        category="Electrical",
    ),
    ConversionFactor(
        unit_key="twh",
        display_name="Terawatt-hour (TWh)",
        aliases=["terawatt-hour", "terawatt hour", "terawatthour"],
        to_kwh=1_000_000_000.0,
        formula="1 TWh = 10^9 kWh  →  factor = 10^9",
        source=_IEEE_SOURCE,
        category="Electrical",
    ),
]


# ---------------------------------------------------------------------------
# Thermal — BTU family, calories, therms
# ---------------------------------------------------------------------------

_THERMAL_UNITS: list[ConversionFactor] = [
    ConversionFactor(
        unit_key="btu",
        display_name="British Thermal Unit (BTU)",
        aliases=["british thermal unit", "british thermal units", "btus"],
        to_kwh=0.000_293_071_07,
        formula=(
            "1 BTU (IT) = 1055.05585 J (NIST definition); "
            "factor = 1055.05585 / 3 600 000 ≈ 2.93071×10⁻⁴"
        ),
        source=_NIST_SOURCE,
        category="Thermal",
    ),
    ConversionFactor(
        unit_key="kbtu",
        display_name="Kilо-BTU (kBTU)",
        aliases=["kilobtu", "k btu", "1000 btu"],
        to_kwh=0.293_071_07,
        formula="1 kBTU = 1000 BTU; factor = 1000 × 2.93071×10⁻⁴ ≈ 0.293071",
        source=_NIST_SOURCE,
        category="Thermal",
    ),
    ConversionFactor(
        unit_key="mmbtu",
        display_name="Million BTU (MMBtu / MMBTU)",
        aliases=["mm btu", "million btu", "dekatherm-equivalent"],
        to_kwh=293.071_07,
        formula="1 MMBtu = 10^6 BTU; factor = 10^6 × 2.93071×10⁻⁴ ≈ 293.071",
        source=_NIST_SOURCE,
        category="Thermal",
    ),
    ConversionFactor(
        unit_key="therm",
        display_name="Therm (US)",
        aliases=["therms", "us therm"],
        to_kwh=29.307_107,
        formula=(
            "1 US therm = 100 000 BTU (IT) (US definition); "
            "factor = 100 000 × 2.93071×10⁻⁴ ≈ 29.3071"
        ),
        source="US EIA (Energy Information Administration) — therm definition",
        category="Thermal",
    ),
    ConversionFactor(
        unit_key="cal",
        display_name="Calorie (thermochemical) (cal)",
        aliases=["calorie", "calories", "cal_th"],
        to_kwh=4.184 / 3_600_000,
        formula=(
            "1 cal (thermochemical) = 4.184 J (NIST); "
            "factor = 4.184 / 3 600 000 ≈ 1.16222×10⁻⁶"
        ),
        source=_NIST_SOURCE,
        category="Thermal",
    ),
    ConversionFactor(
        unit_key="kcal",
        display_name="Kilocalorie (kcal / food calorie)",
        aliases=["kilocalorie", "kilocalories", "food calorie", "dietary calorie", "cal_food"],
        to_kwh=4184 / 3_600_000,
        formula=(
            "1 kcal = 4184 J (thermochemical); "
            "factor = 4184 / 3 600 000 ≈ 1.16222×10⁻³"
        ),
        source=_NIST_SOURCE,
        category="Thermal",
    ),
]


# ---------------------------------------------------------------------------
# Mechanical
# ---------------------------------------------------------------------------

_MECHANICAL_UNITS: list[ConversionFactor] = [
    ConversionFactor(
        unit_key="ftlbf",
        display_name="Foot-pound force (ft·lbf)",
        aliases=["ft-lb", "ft·lb", "foot-pound", "foot pound", "ft lbf", "ftlb"],
        to_kwh=1.355_818_5 / 3_600_000,
        formula=(
            "1 ft·lbf = 1.3558185 J (NIST); "
            "factor = 1.3558185 / 3 600 000 ≈ 3.76616×10⁻⁷"
        ),
        source=_NIST_SOURCE,
        category="Mechanical",
    ),
    ConversionFactor(
        unit_key="hph",
        display_name="Horsepower-hour (hp·h)",
        aliases=["horsepower-hour", "horsepower hour", "hp·hr", "hphr"],
        to_kwh=0.745_699_872,
        formula=(
            "1 hp (mechanical) = 550 ft·lbf/s = 745.699872 W; "
            "1 hp·h = 745.699872 Wh = 0.745699872 kWh"
        ),
        source=_NIST_SOURCE,
        category="Mechanical",
    ),
    ConversionFactor(
        unit_key="erg",
        display_name="Erg (erg)",
        aliases=["ergs"],
        to_kwh=1e-7 / 3_600_000,
        formula="1 erg = 10⁻⁷ J (CGS definition); factor = 10⁻⁷ / 3.6×10⁶ = 2.7778×10⁻¹⁴",
        source=_SI_SOURCE,
        category="Mechanical",
    ),
]


# ---------------------------------------------------------------------------
# Nuclear / Atomic
# ---------------------------------------------------------------------------

_NUCLEAR_UNITS: list[ConversionFactor] = [
    ConversionFactor(
        unit_key="ev",
        display_name="Electron-volt (eV)",
        aliases=["electron-volt", "electron volt", "electronvolt"],
        to_kwh=1.602_176_634e-19 / 3_600_000,
        formula=(
            "1 eV = 1.602176634×10⁻¹⁹ J (exact, BIPM 2019 SI redefinition); "
            "factor = 1.602176634×10⁻¹⁹ / 3.6×10⁶ ≈ 4.45049×10⁻²⁶"
        ),
        source="BIPM — 2019 SI redefinition (exact elementary charge)",
        category="Nuclear",
    ),
    ConversionFactor(
        unit_key="kev",
        display_name="Kiloelectron-volt (keV)",
        aliases=["kiloelectron-volt", "kiloelectron volt"],
        to_kwh=1.602_176_634e-16 / 3_600_000,
        formula="1 keV = 10³ eV; factor = 10³ × 4.45049×10⁻²⁶ ≈ 4.45049×10⁻²³",
        source="BIPM — 2019 SI redefinition",
        category="Nuclear",
    ),
    ConversionFactor(
        unit_key="mev",
        display_name="Megaelectron-volt (MeV)",
        aliases=["megaelectron-volt", "megaelectron volt"],
        to_kwh=1.602_176_634e-13 / 3_600_000,
        formula="1 MeV = 10⁶ eV; factor = 10⁶ × 4.45049×10⁻²⁶ ≈ 4.45049×10⁻²⁰",
        source="BIPM — 2019 SI redefinition",
        category="Nuclear",
    ),
    ConversionFactor(
        unit_key="gev",
        display_name="Gigaelectron-volt (GeV)",
        aliases=["gigaelectron-volt", "gigaelectron volt"],
        to_kwh=1.602_176_634e-10 / 3_600_000,
        formula="1 GeV = 10⁹ eV; factor = 10⁹ × 4.45049×10⁻²⁶ ≈ 4.45049×10⁻¹⁷",
        source="BIPM — 2019 SI redefinition",
        category="Nuclear",
    ),
]


# ---------------------------------------------------------------------------
# Fossil fuel equivalents  (IEA / EIA conventional values)
# ---------------------------------------------------------------------------

_FOSSIL_UNITS: list[ConversionFactor] = [
    ConversionFactor(
        unit_key="toe",
        display_name="Tonne of Oil Equivalent (toe)",
        aliases=["tonne of oil equivalent", "tonnes of oil equivalent"],
        to_kwh=11_630.0,
        formula=(
            "1 toe = 41.868 GJ (IEA lower heating value convention); "
            "41.868 GJ × (1000/3.6) kWh/GJ = 11 630 kWh"
        ),
        source=_IEA_SOURCE,
        category="Fossil",
    ),
    ConversionFactor(
        unit_key="ktoe",
        display_name="Kilotonne of Oil Equivalent (ktoe)",
        aliases=["kilotonne of oil equivalent"],
        to_kwh=11_630_000.0,
        formula="1 ktoe = 1000 toe; factor = 1000 × 11 630 = 11 630 000",
        source=_IEA_SOURCE,
        category="Fossil",
    ),
    ConversionFactor(
        unit_key="mtoe",
        display_name="Megatonne of Oil Equivalent (Mtoe)",
        aliases=["megatonne of oil equivalent"],
        to_kwh=11_630_000_000.0,
        formula="1 Mtoe = 10⁶ toe; factor = 10⁶ × 11 630 = 1.163×10¹⁰",
        source=_IEA_SOURCE,
        category="Fossil",
    ),
    ConversionFactor(
        unit_key="tce",
        display_name="Tonne of Coal Equivalent (tce)",
        aliases=["tonne of coal equivalent", "tonnes of coal equivalent"],
        to_kwh=8_141.0,
        formula=(
            "1 tce = 29.3076 GJ (IEA net calorific value convention); "
            "29.3076 GJ × (1000/3.6) kWh/GJ ≈ 8 141 kWh"
        ),
        source=_IEA_SOURCE,
        category="Fossil",
    ),
    ConversionFactor(
        unit_key="boe",
        display_name="Barrel of Oil Equivalent (BOE)",
        aliases=["barrel of oil equivalent", "barrels of oil equivalent"],
        to_kwh=1_700.0,
        formula=(
            "1 BOE ≈ 6.117 GJ (US EIA / API, 42 US gal crude at ~5.8 MMBtu/bbl); "
            "6.117 GJ × (1000/3.6) ≈ 1699.2 kWh, rounded to 1700 kWh"
        ),
        source="US EIA — Crude oil energy equivalents",
        category="Fossil",
    ),
    ConversionFactor(
        unit_key="cf_ng",
        display_name="Cubic Foot of Natural Gas (cf)",
        aliases=["cf", "scf", "standard cubic foot", "cubic foot natural gas"],
        to_kwh=0.293_071,
        formula=(
            "1 cf natural gas ≈ 1020 BTU (US average HHV, EIA); "
            "1020 × 2.93071×10⁻⁴ ≈ 0.2989 kWh — "
            "conservative standard value used: 0.293071 kWh/cf"
        ),
        source="US EIA — Natural Gas Calorific Values",
        category="Fossil",
    ),
    ConversionFactor(
        unit_key="ccf_ng",
        display_name="Hundred Cubic Feet of Natural Gas (CCF)",
        aliases=["ccf", "hundred cubic feet"],
        to_kwh=29.307_1,
        formula="1 CCF = 100 cf; factor = 100 × 0.293071 = 29.3071",
        source="US EIA — Natural Gas Calorific Values",
        category="Fossil",
    ),
    ConversionFactor(
        unit_key="mcf_ng",
        display_name="Thousand Cubic Feet of Natural Gas (MCF)",
        aliases=["mcf", "thousand cubic feet"],
        to_kwh=293.071,
        formula="1 MCF = 1000 cf; factor = 1000 × 0.293071 = 293.071",
        source="US EIA — Natural Gas Calorific Values",
        category="Fossil",
    ),
    ConversionFactor(
        unit_key="gal_gasoline",
        display_name="US Gallon of Gasoline (gal)",
        aliases=["gallon gasoline", "gallons gasoline", "gal gasoline", "us gallon gasoline"],
        to_kwh=33.41,
        formula=(
            "1 US gal gasoline ≈ 114 000 BTU (HHV, EIA); "
            "114 000 × 2.93071×10⁻⁴ ≈ 33.41 kWh"
        ),
        source="US EIA — Motor Gasoline Energy Content",
        category="Fossil",
    ),
    ConversionFactor(
        unit_key="gal_diesel",
        display_name="US Gallon of Diesel (gal diesel)",
        aliases=["gallon diesel", "gallons diesel", "gal diesel"],
        to_kwh=37.95,
        formula=(
            "1 US gal diesel ≈ 129 488 BTU (HHV, EIA); "
            "129 488 × 2.93071×10⁻⁴ ≈ 37.95 kWh"
        ),
        source="US EIA — Diesel Fuel Energy Content",
        category="Fossil",
    ),
    ConversionFactor(
        unit_key="gal_lpg",
        display_name="US Gallon of LPG / Propane (gal LPG)",
        aliases=["gallon lpg", "gal lpg", "gallon propane", "gal propane"],
        to_kwh=25.53,
        formula=(
            "1 US gal propane ≈ 91 452 BTU (HHV, EIA); "
            "91 452 × 2.93071×10⁻⁴ ≈ 25.53 kWh (liquid, vaporized)"
        ),
        source="US EIA — Propane Energy Content",
        category="Fossil",
    ),
    ConversionFactor(
        unit_key="liter_gasoline",
        display_name="Litre of Gasoline (L)",
        aliases=["litre gasoline", "liter gasoline", "l gasoline", "litre petrol", "liter petrol"],
        to_kwh=8.83,
        formula=(
            "1 US gal gasoline = 3.785411784 L; "
            "33.41 kWh/gal / 3.785411784 L/gal ≈ 8.83 kWh/L"
        ),
        source="US EIA — Motor Gasoline Energy Content (litre conversion)",
        category="Fossil",
    ),
]


# ---------------------------------------------------------------------------
# Combined registry
# ---------------------------------------------------------------------------

REGISTRY: list[ConversionFactor] = (
    _SI_UNITS
    + _ELECTRICAL_UNITS
    + _THERMAL_UNITS
    + _MECHANICAL_UNITS
    + _NUCLEAR_UNITS
    + _FOSSIL_UNITS
)


# ---------------------------------------------------------------------------
# Build lookup index (key + all aliases → ConversionFactor)
# ---------------------------------------------------------------------------

def _build_index(registry: list[ConversionFactor]) -> dict[str, ConversionFactor]:
    """Build a case-insensitive lookup dict mapping every key and alias to its factor."""
    index: dict[str, ConversionFactor] = {}
    for cf in registry:
        for token in [cf.unit_key] + cf.aliases:
            key = token.strip().lower()
            if key in index:
                raise ValueError(f"Duplicate alias '{key}' for units '{index[key].unit_key}' and '{cf.unit_key}'")
            index[key] = cf
    return index


INDEX: dict[str, ConversionFactor] = _build_index(REGISTRY)
