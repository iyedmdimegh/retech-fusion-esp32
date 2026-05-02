"""Quick CO₂ estimate using user-supplied emission factors.

Independent of the M12 forecasting model — this just sums the per-interval
deltas of the gas + auxiliary-electricity meters from the ingested BILAN
data and multiplies by the factors below. Useful for sanity-checking
against an external regulator figure or producing a one-off number for a
report.

Sources:
  * gas.volume_cumulative                         → "gas consumption (Nm³)"
  * electrical.auxiliary.energy_cumulative        → "electricity consumption (kWh)"
    (column-A label in BILAN: "Consommation Auxiliare")

The same correctness rules as the main pipeline apply: rows tagged
``whole_column_zero`` or ``monotonic_inversion`` are excluded; per-interval
deltas are clipped at zero.

Run:
    python scripts/co2_simple_estimate.py
"""
from __future__ import annotations

import psycopg

from retech_part2.config import get_settings

# ---- user-provided factors --------------------------------------------------
ELEC_FACTOR_KG_PER_KWH = 0.257
GAS_FACTOR_KG_PER_NM3 = 1.876

GAS_METRIC = "gas.volume_cumulative"
ELEC_METRIC = "electrical.auxiliary.energy_cumulative"

# ---- query: hourly delta of a cumulative meter, clipped at 0, summed --------
TOTAL_SQL = """
WITH bucket AS (
    SELECT date_trunc('hour', "time") AS h,
           MAX(value)                  AS v
      FROM timeseries.bilan_readings
     WHERE metric_id = %(metric)s
       AND (data_quality_flags IS NULL
            OR NOT (data_quality_flags && ARRAY['whole_column_zero', 'monotonic_inversion']))
     GROUP BY date_trunc('hour', "time")
),
delta AS (
    SELECT GREATEST(v - LAG(v) OVER (ORDER BY h), 0) AS d
      FROM bucket
)
SELECT COALESCE(SUM(d), 0) FROM delta;
"""


def total_consumption(conn: psycopg.Connection, metric_id: str) -> float:
    with conn.cursor() as cur:
        cur.execute(TOTAL_SQL, {"metric": metric_id})
        row = cur.fetchone()
        return float(row[0]) if row else 0.0


def main() -> int:
    settings = get_settings()
    with psycopg.connect(settings.postgres_dsn) as conn:
        gas_nm3 = total_consumption(conn, GAS_METRIC)
        elec_kwh = total_consumption(conn, ELEC_METRIC)

    co2_gas_kg = gas_nm3 * GAS_FACTOR_KG_PER_NM3
    co2_elec_kg = elec_kwh * ELEC_FACTOR_KG_PER_KWH
    total_kg = co2_gas_kg + co2_elec_kg

    print()
    print(f"  gas consumed           : {gas_nm3:>15,.1f} Nm3")
    print(f"  electricity consumed   : {elec_kwh:>15,.1f} kWh")
    print(f"  factor (gas)           : {GAS_FACTOR_KG_PER_NM3} kg CO2 / Nm3")
    print(f"  factor (electricity)   : {ELEC_FACTOR_KG_PER_KWH} kg CO2 / kWh")
    print()
    print(f"  CO2 from gas           : {co2_gas_kg / 1000:>10.3f} tonnes")
    print(f"  CO2 from electricity   : {co2_elec_kg / 1000:>10.3f} tonnes")
    print(f"  -------------------------------------")
    print(f"  total CO2              : {total_kg / 1000:>10.3f} tonnes")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
