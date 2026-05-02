"""Process entry point for the live MQTT subscriber.

Pure-sync — no asyncio loop in this process. paho-mqtt's network loop runs
on the main thread; psycopg writes happen on paho's worker thread (single
shared connection).

Started from the Makefile via ``make mqtt``.
"""
from __future__ import annotations

from retech_part2._compat import apply_windows_event_loop_policy
from retech_part2.ingestion.mqtt.subscriber import make_subscriber_from_settings
from retech_part2.logging import configure_logging


def main() -> None:
    apply_windows_event_loop_policy()
    configure_logging()
    sub = make_subscriber_from_settings()
    sub.run_forever()


if __name__ == "__main__":
    main()
