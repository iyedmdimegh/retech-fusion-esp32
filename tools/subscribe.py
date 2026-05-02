#!/usr/bin/env python3
"""
Re-Tech Fusion ESP32 Node — example MQTT consumer.

Subscribes to retech/devices/+/readings, decodes each JSON payload, prints a
one-line summary, and (optionally) appends raw payloads to a JSON-lines file
for downstream ingestion or replay.

Usage:
    pip install "paho-mqtt>=2.0"
    python tools/subscribe.py                            # broker on localhost:1883
    python tools/subscribe.py --host 192.168.137.1       # remote broker
    python tools/subscribe.py --jsonl out.jsonl          # also tee payloads to file
    python tools/subscribe.py --topic 'retech/#'         # broader topic
    python tools/subscribe.py --username u --password p  # if anonymous is off

This is a minimal reference implementation — robust enough for hackathon
demos and downstream pipelines to fork.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--host", default="localhost", help="MQTT broker hostname or IP")
    p.add_argument("--port", default=1883, type=int)
    p.add_argument("--topic", default="retech/devices/+/readings")
    p.add_argument("--username", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--jsonl", default=None,
                   help="append every raw payload (one JSON per line) to this file")
    p.add_argument("--qos", default=1, type=int, choices=(0, 1, 2))
    return p.parse_args()


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        topic = userdata["topic"]
        qos = userdata["qos"]
        print(f"[OK]   connected — subscribing to {topic!r} (QoS {qos})")
        client.subscribe(topic, qos=qos)
    else:
        print(f"[ERR]  connect failed: {reason_code}", file=sys.stderr)


def on_disconnect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        print(f"[WARN] disconnected: {reason_code} (paho will auto-reconnect)",
              file=sys.stderr)


def format_reading(r: dict) -> str:
    """Pretty-print a single reading entry as 'type(sensor)=value unit'."""
    rtype = r.get("type", "?")
    val = r.get("value")
    unit = r.get("unit", "")
    sensor = r.get("sensor", "?")
    if isinstance(val, (int, float)):
        val_s = f"{val:.3f}"
    else:
        val_s = str(val)
    return f"{rtype}({sensor})={val_s} {unit}"


def on_message(client, userdata, msg):
    raw = msg.payload.decode("utf-8", errors="replace")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[ERR]  non-JSON payload on {msg.topic}: {e}", file=sys.stderr)
        return

    device = doc.get("device_id", "?")
    ts = doc.get("timestamp", "?")
    status = doc.get("status", "?")
    rssi = doc.get("rssi", "?")
    readings = doc.get("readings", [])

    summary = "  ".join(format_reading(r) for r in readings)
    print(f"[{ts}] {device} status={status} rssi={rssi}  {summary}")

    if userdata.get("jsonl_fp") is not None:
        # Wrap with our own ingestion timestamp so consumers can distinguish
        # device-side capture time from server-side receipt time.
        record = {
            "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "topic": msg.topic,
            "payload": doc,
        }
        userdata["jsonl_fp"].write(json.dumps(record, separators=(",", ":")) + "\n")
        userdata["jsonl_fp"].flush()


def main() -> int:
    args = parse_args()

    jsonl_fp = open(args.jsonl, "a", encoding="utf-8") if args.jsonl else None
    userdata = {"topic": args.topic, "qos": args.qos, "jsonl_fp": jsonl_fp}

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        userdata=userdata,
        client_id="",            # let the broker assign one
        clean_session=True,
    )
    if args.username:
        client.username_pw_set(args.username, args.password)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    # paho-mqtt auto-reconnect: try every 1..120 s with exponential backoff.
    client.reconnect_delay_set(min_delay=1, max_delay=120)

    print(f"[..]   connecting to {args.host}:{args.port}")
    try:
        client.connect(args.host, args.port, keepalive=60)
    except (ConnectionRefusedError, OSError) as e:
        print(f"[ERR]  initial connect failed: {e}", file=sys.stderr)
        if jsonl_fp:
            jsonl_fp.close()
        return 2

    def shutdown(signum, frame):
        print("\n[..]   shutting down")
        client.disconnect()
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        client.loop_forever()
    finally:
        if jsonl_fp:
            jsonl_fp.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
