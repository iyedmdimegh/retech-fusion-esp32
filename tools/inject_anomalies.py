#!/usr/bin/env python3
"""
Re-Tech Fusion — Part 3A anomaly injection utility.

Reads training_data.jsonl and appends clearly anomalous rows so the
training script has labelled examples to validate anomaly detection.

Two modes:
  --synthetic   (default) Generate N artificial anomaly rows per type
  --mark-last N           Mark the last N real rows as anomalies
                          (use after physically simulating an anomaly:
                           touch DS18B20, disconnect motor, etc.)

Usage:
    python tools/inject_anomalies.py                   # 5 rows per anomaly type
    python tools/inject_anomalies.py --per-type 10     # 10 rows per type
    python tools/inject_anomalies.py --mark-last 15    # label last 15 rows
    python tools/inject_anomalies.py --list-types      # show anomaly types
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
JSONL_PATH   = PROJECT_ROOT / "training_data.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# Anomaly type definitions
# Each entry: (label, channel_overrides_dict, description)
# channel_overrides: {channel_key: (mean, stddev)}
#   channel keys: ds18b20_temperature, bme_temperature, bme_pressure, acs_current
# ─────────────────────────────────────────────────────────────────────────────
ANOMALY_TYPES = {
    "temp_spike_ds18b20": {
        "desc": "DS18B20 temperature spike (simulate by touching sensor with warm hand / lighter)",
        "overrides": {
            ("temperature", "ds18b20"): (65.0, 2.0),   # ~65°C ± 2
        },
    },
    "temp_spike_bmp280": {
        "desc": "BMP280 temperature spike (electronic heating / hot environment)",
        "overrides": {
            ("temperature", "bmp280"): (55.0, 1.5),
        },
    },
    "pressure_drop": {
        "desc": "Sudden pressure drop (altitude change / sensor fault)",
        "overrides": {
            ("pressure", "bmp280"): (955.0, 3.0),
        },
    },
    "current_zero": {
        "desc": "Current drops to zero (motor disconnected / broken cable)",
        "overrides": {
            ("current", "acs712"): (0.0, 0.002),
        },
    },
    "current_spike": {
        "desc": "Current spike (motor stall / short circuit)",
        "overrides": {
            ("current", "acs712"): (8.5, 0.5),
        },
    },
    "dual_fault": {
        "desc": "Simultaneous temp spike + current anomaly (compound fault)",
        "overrides": {
            ("temperature", "ds18b20"): (70.0, 1.0),
            ("current",     "acs712"):  (12.0, 0.3),
        },
    },
}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def compute_baseline(rows: list[dict]) -> dict:
    """Compute mean of each channel from normal rows."""
    accum: dict = {}
    counts: dict = {}
    for row in rows:
        if row.get("is_anomaly"):
            continue
        payload = row.get("payload", row)
        for r in payload.get("readings", []):
            key = (r["type"], r["sensor"].replace("bme280", "bmp280"))
            v = r.get("value")
            if v is not None and isinstance(v, (int, float)):
                accum.setdefault(key, 0.0)
                counts.setdefault(key, 0)
                accum[key] += float(v)
                counts[key] += 1
    return {k: accum[k] / counts[k] for k in accum if counts[k] > 0}


def make_anomaly_row(template_row: dict, overrides: dict, anomaly_type: str) -> dict:
    """
    Clone a real row, apply channel overrides, and mark as anomaly.
    """
    row = copy.deepcopy(template_row)
    row["is_anomaly"]   = True
    row["anomaly_type"] = anomaly_type
    row["received_at"]  = datetime.now(timezone.utc).isoformat(timespec="seconds")

    payload = row.setdefault("payload", {})
    readings = payload.get("readings", [])

    for r in readings:
        key = (r["type"], r.get("sensor", "").replace("bme280", "bmp280"))
        if key in overrides:
            mean, std = overrides[key]
            r["value"] = round(random.gauss(mean, std), 6)

    payload["status"] = "anomaly"
    return row


def append_rows(path: Path, rows: list[dict]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jsonl",       default=str(JSONL_PATH))
    parser.add_argument("--per-type",    default=5, type=int,
                        help="Number of anomaly rows to generate per type (default 5)")
    parser.add_argument("--mark-last",   default=0, type=int,
                        help="Mark the last N real rows as anomalies (after physical demo)")
    parser.add_argument("--types",       default=None,
                        help="Comma-separated anomaly types (default: all)")
    parser.add_argument("--list-types",  action="store_true")
    args = parser.parse_args()

    if args.list_types:
        print("Available anomaly types:")
        for name, info in ANOMALY_TYPES.items():
            print(f"  {name:<25s}  {info['desc']}")
        return 0

    path = Path(args.jsonl)
    if not path.exists():
        print(f"[ERR] {path} not found. Collect data first.", file=sys.stderr)
        return 1

    rows = load_jsonl(path)
    normal_rows = [r for r in rows if not r.get("is_anomaly")]
    existing_anomalies = len(rows) - len(normal_rows)

    print(f"\n{'='*60}")
    print(f" Re-Tech Fusion — Anomaly Injection")
    print(f"{'='*60}")
    print(f"  JSONL file        : {path}")
    print(f"  Normal rows       : {len(normal_rows)}")
    print(f"  Existing anomalies: {existing_anomalies}")

    if len(normal_rows) < 5:
        print("[ERR] Need at least 5 normal rows. Collect more data.", file=sys.stderr)
        return 1

    baseline = compute_baseline(rows)
    print(f"\n  Baseline means:")
    for k, v in baseline.items():
        print(f"    {str(k):<35s}: {v:.4f}")

    # ── Mode 1: mark last N rows as physical anomalies ─────────────────────
    if args.mark_last > 0:
        n = min(args.mark_last, len(normal_rows))
        to_mark = normal_rows[-n:]
        for r in to_mark:
            r["is_anomaly"]   = True
            r["anomaly_type"] = "physical"

        # Rewrite the whole file
        with open(path, "w", encoding="utf-8") as f:
            for r in rows[:-n]:   # keep earlier rows unchanged
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
            for r in to_mark:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")

        print(f"\n  ✓ Marked last {n} rows as 'physical' anomalies.")
        print(f"  Total anomaly rows: {existing_anomalies + n}")
        return 0

    # ── Mode 2: generate synthetic anomaly rows ────────────────────────────
    types_to_use = list(ANOMALY_TYPES.keys())
    if args.types:
        types_to_use = [t.strip() for t in args.types.split(",")]
        for t in types_to_use:
            if t not in ANOMALY_TYPES:
                print(f"[ERR] Unknown type '{t}'. Run --list-types.", file=sys.stderr)
                return 1

    # Use the last few real rows as templates (most representative of current state)
    templates = normal_rows[-min(10, len(normal_rows)):]
    new_rows: list[dict] = []
    random.seed(42)

    print(f"\n  Generating {args.per_type} rows × {len(types_to_use)} types"
          f" = {args.per_type * len(types_to_use)} anomaly rows")
    print()

    for atype in types_to_use:
        info = ANOMALY_TYPES[atype]
        for _ in range(args.per_type):
            template = random.choice(templates)
            new_rows.append(make_anomaly_row(template, info["overrides"], atype))
        print(f"  ✓ {atype:<25s}  {info['desc']}")

    # Shuffle so anomalies aren't all clumped at the end
    random.shuffle(new_rows)
    append_rows(path, new_rows)

    total_anomaly = existing_anomalies + len(new_rows)
    print(f"\n  Appended {len(new_rows)} anomaly rows → {path.name}")
    print(f"  Total rows now: {len(rows) + len(new_rows)}"
          f" ({total_anomaly} anomalies, {len(normal_rows)} normal)")
    print(f"\n  Next step: python tools/train_model.py")
    print(f"{'='*60}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
