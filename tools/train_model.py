#!/usr/bin/env python3
"""
Re-Tech Fusion — Part 3A edge ML training script.

Reads training_data.jsonl (produced by tools/subscribe.py --jsonl),
trains a tiny 5-channel MLP, converts to TFLite, and writes
include/model_data.h as a C byte array ready for EloquentTinyML.

Usage:
    pip install tensorflow numpy scikit-learn
    python tools/train_model.py
    python tools/train_model.py --jsonl path/to/data.jsonl --epochs 300
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import textwrap
from pathlib import Path

import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# Channel definitions (index = order in C arrays / ESP32 firmware)
# MUST match edge_inference.cpp EXACTLY
# ──────────────────────────────────────────────────────────────────────────────
CHANNEL_KEYS = [
    ("temperature", "ds18b20"),    # CH0
    ("temperature", "bme280"),     # CH1  (bmp280 also accepted)
    ("humidity",    "bme280"),     # CH2  (may always be NaN on BMP280)
    ("pressure",    "bme280"),     # CH3  (bmp280 also accepted)
    ("current",     "acs712"),     # CH4
]
CHANNEL_NAMES = ["ds18b20_T", "bme_T", "bme_H", "bme_P", "acs_I"]
CHANNEL_DEFAULTS = [25.0, 25.0, 50.0, 1013.0, 0.0]   # fallback for missing

WINDOW   = 5
N_CH     = len(CHANNEL_KEYS)
MIN_ROWS = 15   # hard stop below this
WARN_ROWS = 100  # warn but continue

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_HEADER   = PROJECT_ROOT / "include" / "model_data.h"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[WARN] line {i+1} skipped ({e})")
    return records


def extract_channels(records: list[dict]) -> np.ndarray:
    """
    Return (N, N_CH) float array. One row per MQTT message.
    Missing values are set to np.nan (filled later).
    """
    rows = []
    for rec in records:
        # Support both plain payload and wrapped {"payload": {...}} form
        payload = rec.get("payload", rec)
        readings = payload.get("readings", [])
        lookup = {}
        for r in readings:
            rtype  = r.get("type", "")
            rsensor = r.get("sensor", "").lower()
            val = r.get("value")
            # Accept bmp280 as bme280 for our purposes
            if rsensor == "bmp280":
                rsensor = "bme280"
            key = (rtype, rsensor)
            if key in lookup:
                continue  # take first occurrence
            try:
                lookup[key] = float(val)
            except (TypeError, ValueError):
                pass

        row = []
        for key, default in zip(CHANNEL_KEYS, CHANNEL_DEFAULTS):
            row.append(lookup.get(key, np.nan))
        rows.append(row)

    return np.array(rows, dtype=np.float32)


def impute_columns(X: np.ndarray, defaults: list[float]) -> np.ndarray:
    """Replace NaN with column mean; if column is all-NaN use default."""
    X = X.copy()
    for c in range(X.shape[1]):
        col = X[:, c]
        mask = np.isnan(col)
        if mask.all():
            X[:, c] = defaults[c]
        elif mask.any():
            X[mask, c] = np.nanmean(col)
    return X


def minmax_per_channel(X: np.ndarray):
    """Returns (X_norm, ch_min, ch_max). Adds eps to avoid /0."""
    ch_min = X.min(axis=0)
    ch_max = X.max(axis=0)
    rng = ch_max - ch_min
    rng[rng < 1e-6] = 1.0      # constant channel → safe divide
    X_norm = (X - ch_min) / rng
    return X_norm.astype(np.float32), ch_min.astype(np.float32), ch_max.astype(np.float32)


def build_windows(X_norm: np.ndarray):
    """Sliding window: X[t:t+W] → Y[t+W] (next step prediction)."""
    n = len(X_norm)
    xs, ys = [], []
    for i in range(n - WINDOW):
        xs.append(X_norm[i:i + WINDOW].flatten())   # (WINDOW*N_CH,) = (25,)
        ys.append(X_norm[i + WINDOW])                # (N_CH,) = (5,)
    return np.array(xs, dtype=np.float32), np.array(ys, dtype=np.float32)


def augment(X, Y, factor: int = 3, sigma: float = 0.01):
    """Inflate small datasets with Gaussian noise on inputs."""
    aug_x = [X]
    aug_y = [Y]
    rng = np.random.default_rng(42)
    for _ in range(factor - 1):
        noisy = X + rng.normal(0, sigma, X.shape).astype(np.float32)
        noisy = np.clip(noisy, 0.0, 1.0)
        aug_x.append(noisy)
        aug_y.append(Y)
    return np.concatenate(aug_x), np.concatenate(aug_y)


def bytes_to_c_array(data: bytes, varname: str = "MODEL_DATA") -> str:
    hex_vals = ", ".join(f"0x{b:02x}" for b in data)
    # Wrap at 16 bytes per line for readability
    chunks = [data[i:i+16] for i in range(0, len(data), 16)]
    lines  = [
        "    " + ", ".join(f"0x{b:02x}" for b in chunk)
        for chunk in chunks
    ]
    body = ",\n".join(lines)
    return (
        f"static const unsigned int {varname}_LEN = {len(data)};\n"
        f"static const unsigned char {varname}[] = {{\n{body}\n}};\n"
    )


def floats_to_c_array(arr: np.ndarray, varname: str) -> str:
    vals = ", ".join(f"{v:.8f}f" for v in arr)
    return f"static const float {varname}[{len(arr)}] = {{{vals}}};\n"


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl",   default=str(PROJECT_ROOT / "training_data.jsonl"))
    parser.add_argument("--epochs",  default=200, type=int)
    parser.add_argument("--window",  default=WINDOW, type=int)
    parser.add_argument("--patience",default=20, type=int)
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        print(f"[ERR] {jsonl_path} not found.")
        print("[ERR] Run: python tools/subscribe.py --host 192.168.137.1 --jsonl training_data.jsonl")
        print("[ERR] Wait at least 5 minutes (≥30 rows), then re-run this script.")
        sys.exit(1)

    all_records = load_jsonl(jsonl_path)
    n_rows = len(all_records)

    # Split normal vs anomaly rows (anomaly rows are excluded from training,
    # used only for post-training validation)
    normal_records  = [r for r in all_records if not r.get("is_anomaly")]
    anomaly_records = [r for r in all_records if r.get("is_anomaly")]

    print(f"\n{'='*60}")
    print(f" Re-Tech Fusion — Edge ML Training")
    print(f"{'='*60}")
    print(f"  JSONL file        : {jsonl_path}")
    print(f"  Total rows        : {n_rows}")
    print(f"  Normal (training) : {len(normal_records)}")
    print(f"  Anomaly (validation): {len(anomaly_records)}")

    records = normal_records   # train on normal only

    if len(records) < MIN_ROWS:
        print(f"\n[ERR] Too few normal rows ({len(records)} < {MIN_ROWS}). Collect more data first.")
        sys.exit(1)

    if len(records) < WARN_ROWS:
        print(f"[WARN] Only {len(records)} normal rows — model may overfit. Augmentation will help.")
        print(f"[WARN] Recommended: ≥{WARN_ROWS} rows for reliable anomaly detection.")

    # ── 1. Extract & impute ────────────────────────────────────────────────
    X_raw = extract_channels(records)
    print(f"\n  Raw shape  : {X_raw.shape}")
    nan_pct = np.isnan(X_raw).mean(axis=0) * 100
    for i, (name, pct) in enumerate(zip(CHANNEL_NAMES, nan_pct)):
        print(f"    CH{i} {name:<10s}: {pct:.0f}% NaN", end="")
        if pct > 90:
            print(f"  ← missing sensor, using default {CHANNEL_DEFAULTS[i]}", end="")
        print()

    X_imp = impute_columns(X_raw, CHANNEL_DEFAULTS)

    # ── 2. Normalise ───────────────────────────────────────────────────────
    X_norm, ch_min, ch_max = minmax_per_channel(X_imp)
    print(f"\n  Normalisation ranges (min → max per channel):")
    for i, name in enumerate(CHANNEL_NAMES):
        print(f"    CH{i} {name:<10s}: {ch_min[i]:.4f} → {ch_max[i]:.4f}")

    # ── 3. Sliding windows ─────────────────────────────────────────────────
    W = args.window
    X_win, Y_win = build_windows(X_norm)
    print(f"\n  Window size : {W}")
    print(f"  Samples     : {len(X_win)} (before augmentation)")

    if len(X_win) < 50:
        print(f"  Augmenting  : 3× (Gaussian noise σ=0.01)")
        X_win, Y_win = augment(X_win, Y_win, factor=3)
        print(f"  Samples     : {len(X_win)} (after augmentation)")

    # ── 4. Train MLP ───────────────────────────────────────────────────────
    print(f"\n  Building model: Input(25)→Dense(16,relu)→Dense(8,relu)→Dense(5,sigmoid)")

    import tensorflow as tf  # import late so --help works without TF installed
    tf.random.set_seed(42)

    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(N_CH * W,)),
        tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(8,  activation="relu"),
        tf.keras.layers.Dense(N_CH, activation="sigmoid"),
    ], name="retech_edge_mlp")

    model.compile(optimizer="adam", loss="mae", metrics=["mae"])
    model.summary(print_fn=lambda s: print("  " + s))

    val_split  = 0.2 if len(X_win) >= 20 else 0.0
    callbacks  = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss" if val_split > 0 else "loss",
            patience=args.patience,
            restore_best_weights=True,
            verbose=0,
        )
    ]
    print(f"\n  Training (epochs={args.epochs}, patience={args.patience}, val={val_split:.0%})...")
    hist = model.fit(
        X_win, Y_win,
        epochs=args.epochs,
        validation_split=val_split,
        callbacks=callbacks,
        verbose=0,
    )
    final_loss = hist.history["loss"][-1]
    epochs_ran = len(hist.history["loss"])
    print(f"  Training MAE : {final_loss:.6f}  (stopped at epoch {epochs_ran})")

    if val_split > 0:
        val_mae = hist.history["val_mae"][-1]
        print(f"  Validation MAE: {val_mae:.6f}")

    # Per-channel MAE on the full dataset
    y_pred = model.predict(X_win, verbose=0)
    per_ch_mae = np.mean(np.abs(y_pred - Y_win), axis=0)
    print(f"\n  Per-channel MAE (normalised 0–1):")
    for i, (name, mae) in enumerate(zip(CHANNEL_NAMES, per_ch_mae)):
        print(f"    CH{i} {name:<10s}: {mae:.4f}")

    # ── 5. Convert to TFLite ───────────────────────────────────────────────
    print(f"\n  Converting to TFLite (DEFAULT optimisation)...")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    tflite_model = converter.convert()
    model_bytes  = len(tflite_model)
    print(f"  ✓ TFLite model size : {model_bytes} bytes  ({model_bytes/1024:.2f} KB)")

    # ── 6. Validate on anomaly rows (if any were injected) ────────────────
    if anomaly_records:
        X_anom_raw = extract_channels(anomaly_records)
        X_anom_imp = impute_columns(X_anom_raw, CHANNEL_DEFAULTS)
        # Normalise using the SAME scaler fitted on normal data
        X_anom_norm = ((X_anom_imp - ch_min) / np.where(ch_max - ch_min < 1e-6, 1.0, ch_max - ch_min)).astype(np.float32)
        X_anom_norm = np.clip(X_anom_norm, 0.0, 1.0)

        # Build windows using the last WINDOW normal readings as history
        # (simulate what the ESP32 would see: normal window → anomalous next step)
        normal_tail = X_norm[-W:]       # last W normal readings as context
        detected = 0
        threshold = 0.15                # matches EDGE_ANOMALY_THRESHOLD

        for row_norm in X_anom_norm:
            window_flat = np.concatenate([normal_tail, row_norm.reshape(1, -1)], axis=0)
            if len(window_flat) > W:
                window_flat = window_flat[-W:]
            inp = window_flat.flatten().reshape(1, -1)
            # Pad if needed (shouldn't happen but guard against edge cases)
            if inp.shape[1] < N_CH * W:
                inp = np.pad(inp, ((0, 0), (0, N_CH * W - inp.shape[1])))
            pred = model.predict(inp, verbose=0)[0]
            err = np.max(np.abs(pred - row_norm))
            if err > threshold:
                detected += 1

        detection_rate = detected / len(anomaly_records) * 100
        print(f"\n  {'─'*50}")
        print(f"  ANOMALY VALIDATION ({len(anomaly_records)} injected rows)")
        print(f"  Threshold     : {threshold} (normalised)")
        print(f"  Detected      : {detected}/{len(anomaly_records)} ({detection_rate:.0f}%)")
        if detection_rate >= 80:
            print(f"  ✓ ANOMALY DETECTION WORKS — {detection_rate:.0f}% detection rate")
        else:
            print(f"  ⚠ Low detection rate. Try --per-type 10 or --anomaly-threshold 0.10")
        print(f"  {'─'*50}")

        # Per-type breakdown
        anom_by_type: dict = {}
        for r in anomaly_records:
            t = r.get("anomaly_type", "unknown")
            anom_by_type.setdefault(t, []).append(r)

        if len(anom_by_type) > 1:
            print(f"  Per-type breakdown:")
            for atype, type_rows in anom_by_type.items():
                X_t = extract_channels(type_rows)
                X_t = impute_columns(X_t, CHANNEL_DEFAULTS)
                X_t = np.clip((X_t - ch_min) / np.where(ch_max - ch_min < 1e-6, 1.0, ch_max - ch_min), 0.0, 1.0).astype(np.float32)
                t_detected = 0
                for row_n in X_t:
                    inp = np.concatenate([normal_tail.flatten(), row_n]).reshape(1, -1)
                    pred = model.predict(inp[:, :N_CH*W], verbose=0)[0]
                    if np.max(np.abs(pred - row_n)) > threshold:
                        t_detected += 1
                print(f"    {atype:<25s}: {t_detected}/{len(type_rows)}")

    # ── 6. Write C header ─────────────────────────────────────────────────
    OUT_HEADER.parent.mkdir(exist_ok=True)
    with open(OUT_HEADER, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(f"""\
            // AUTO-GENERATED by tools/train_model.py — DO NOT EDIT MANUALLY
            // Re-Tech Fusion Edge ML — 5-channel MLP anomaly predictor
            //
            // Architecture : Input(25) -> Dense(16,relu) -> Dense(8,relu) -> Dense(5,sigmoid)
            // TFLite size  : {model_bytes} bytes
            // Training rows: {n_rows}
            //
            // Channel order (index 0..4):
            //   0: ds18b20 temperature (celsius)
            //   1: bme/bmp temperature (celsius)
            //   2: bme humidity        (percent, NaN→50 if BMP280)
            //   3: bme/bmp pressure    (hPa)
            //   4: acs712 current      (ampere)
            #pragma once

            // ── Normalisation constants (per-channel min/max) ─────────────────────
        """))
        f.write(floats_to_c_array(ch_min, "EDGE_CHANNEL_MIN"))
        f.write(floats_to_c_array(ch_max, "EDGE_CHANNEL_MAX"))
        f.write("\n// ── TFLite flatbuffer ────────────────────────────────────────────────\n")
        f.write(bytes_to_c_array(tflite_model, "MODEL_DATA"))

    print(f"\n  ✓ C header written : {OUT_HEADER}")
    print(f"\n{'='*60}")
    print(f" DONE — screenshot this output for submission evidence")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
