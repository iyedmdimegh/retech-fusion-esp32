"""Replay a JSONL file of MQTT payloads through the same insertion path
the live subscriber uses. Demo-day fallback if the broker / Wi-Fi is flaky.

Each line of the input file is one JSON payload matching the schema in
:mod:`retech_part2.ingestion.mqtt.payload`. (Compatible with the teammate's
``tools/subscribe.py --jsonl`` capture format.)

Usage::

    python scripts/replay_mqtt_jsonl.py path/to/recording.jsonl
    python scripts/replay_mqtt_jsonl.py path/to/recording.jsonl --rate 10
    python scripts/replay_mqtt_jsonl.py path/to/recording.jsonl --rate 0   # no throttle
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import psycopg

from retech_part2._compat import apply_windows_event_loop_policy
from retech_part2.config import get_settings
from retech_part2.ingestion.mqtt.subscriber import _Counters, process_payload
from retech_part2.logging import configure_logging, get_logger


def main() -> int:
    apply_windows_event_loop_policy()
    configure_logging()
    log = get_logger("mqtt.replay")

    p = argparse.ArgumentParser(description="Replay an MQTT JSONL recording into the DB.")
    p.add_argument("path", type=Path, help="JSONL file with one payload per line")
    p.add_argument(
        "--rate",
        type=float,
        default=10.0,
        help="messages/sec to emit (0 = full speed). Default: 10",
    )
    args = p.parse_args()

    if not args.path.exists():
        print(f"file not found: {args.path}", file=sys.stderr)
        return 2

    settings = get_settings()
    counters = _Counters()
    sleep_per = (1.0 / args.rate) if args.rate > 0 else 0.0

    log.info("mqtt_replay_start", path=str(args.path), rate_msgs_per_sec=args.rate)

    line_no = 0
    with psycopg.connect(settings.postgres_dsn, autocommit=False) as conn:
        with args.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                line_no += 1
                try:
                    payload_dict = json.loads(line)
                except json.JSONDecodeError as e:
                    log.warning("mqtt_replay_bad_json", line=line_no, error=str(e))
                    counters.messages_dropped_parse_error += 1
                    continue
                counters.messages_received += 1
                try:
                    process_payload(conn, payload_dict, counters)
                except psycopg.Error as e:
                    log.exception("mqtt_replay_db_error", line=line_no, error=str(e))
                    counters.db_errors += 1
                    conn.rollback()
                if sleep_per > 0:
                    time.sleep(sleep_per)

    log.info(
        "mqtt_replay_done",
        lines_read=line_no,
        messages_received=counters.messages_received,
        readings_inserted=counters.readings_inserted,
        readings_duplicate=counters.readings_duplicate,
        messages_dropped_pre_ntp=counters.messages_dropped_pre_ntp,
        messages_dropped_parse_error=counters.messages_dropped_parse_error,
        distinct_devices=len(counters.devices_seen),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
