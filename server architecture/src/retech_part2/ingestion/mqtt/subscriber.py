"""Live MQTT subscriber for the Phase 1 ESP32 fleet.

Subscribes to ``retech/devices/+/readings`` at QoS 1, parses each payload
against :class:`EspReadingsPayload`, and writes:

* ``meta.devices``                upsert (last_seen = NOW(), fw_version refreshed)
* ``timeseries.readings``         one row per element in payload.readings,
                                  with INSERT ... ON CONFLICT DO NOTHING
                                  against the readings_dedup_key constraint
                                  (added by migration 002).
* ``timeseries.device_status``    one row per message (status, rssi, uptime, fw)

Threading model
---------------
paho-mqtt's loop runs the ``on_message`` callback on a dedicated network
thread. We do **not** touch the SQLAlchemy async session here — paho's
threading and asyncio don't compose cleanly. A single, persistent
``psycopg.connect()`` is opened at startup; failures trigger reconnect on
the next message.

A daemon heartbeat thread logs message + insert + dedup counts every 30 s
so it's obvious from `make mqtt`'s output that data is flowing.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import paho.mqtt.client as mqtt
import psycopg
from paho.mqtt.client import CallbackAPIVersion

from retech_part2.config import get_settings
from retech_part2.ingestion.mqtt.payload import EspReadingsPayload
from retech_part2.logging import get_logger

log = get_logger("mqtt.subscriber")


# ---------------------------------------------------------------------------
# SQL — kept as module-level constants so the replay script can reuse them
# ---------------------------------------------------------------------------

_UPSERT_DEVICE = """
INSERT INTO meta.devices (device_id, site, fw_version, last_seen)
VALUES (%(device_id)s, %(site)s, %(fw_version)s, NOW())
ON CONFLICT (device_id) DO UPDATE
   SET site       = EXCLUDED.site,
       fw_version = COALESCE(EXCLUDED.fw_version, meta.devices.fw_version),
       last_seen  = NOW()
"""

_INSERT_READING = """
INSERT INTO timeseries.readings
       ("time", device_id, sensor, type, value, unit)
VALUES (%(time)s, %(device_id)s, %(sensor)s, %(type)s, %(value)s, %(unit)s)
ON CONFLICT ON CONSTRAINT readings_dedup_key DO NOTHING
"""

_INSERT_DEVICE_STATUS = """
INSERT INTO timeseries.device_status
       ("time", device_id, status, rssi, uptime_s, fw_version)
VALUES (%(time)s, %(device_id)s, %(status)s, %(rssi)s, %(uptime_s)s, %(fw_version)s)
"""


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

@dataclass
class _Counters:
    messages_received: int = 0
    messages_dropped_pre_ntp: int = 0
    messages_dropped_parse_error: int = 0
    readings_inserted: int = 0       # excludes duplicates collapsed by ON CONFLICT
    readings_duplicate: int = 0
    db_errors: int = 0
    devices_seen: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# the per-payload processing path — exported for the JSONL replay script
# ---------------------------------------------------------------------------

def process_payload(
    conn: psycopg.Connection,
    payload_dict: dict[str, Any],
    counters: _Counters,
) -> None:
    """Validate one wire payload and write the resulting DB rows.

    Atomicity: each payload is one transaction. ``ON CONFLICT DO NOTHING``
    on readings means rowcount may be < len(readings); we count both halves.
    """
    try:
        payload = EspReadingsPayload.model_validate(payload_dict)
    except Exception as e:
        counters.messages_dropped_parse_error += 1
        log.warning("mqtt_payload_parse_error", error=str(e))
        return

    if payload.is_pre_ntp():
        counters.messages_dropped_pre_ntp += 1
        log.debug(
            "mqtt_payload_dropped_pre_ntp",
            device_id=payload.device_id,
            timestamp=payload.timestamp.isoformat(),
        )
        return

    counters.devices_seen.add(payload.device_id)

    with conn.cursor() as cur:
        cur.execute(
            _UPSERT_DEVICE,
            {
                "device_id": payload.device_id,
                "site": payload.site,
                "fw_version": payload.fw_version,
            },
        )
        for r in payload.readings:
            cur.execute(
                _INSERT_READING,
                {
                    "time": payload.timestamp,
                    "device_id": payload.device_id,
                    "sensor": r.sensor,
                    "type": r.type,
                    "value": r.value,
                    "unit": r.unit,
                },
            )
            if cur.rowcount == 1:
                counters.readings_inserted += 1
            else:
                counters.readings_duplicate += 1
        cur.execute(
            _INSERT_DEVICE_STATUS,
            {
                "time": payload.timestamp,
                "device_id": payload.device_id,
                "status": payload.status,
                "rssi": payload.rssi,
                "uptime_s": payload.uptime_s,
                "fw_version": payload.fw_version,
            },
        )
    conn.commit()


# ---------------------------------------------------------------------------
# subscriber
# ---------------------------------------------------------------------------

class MqttSubscriber:
    def __init__(
        self,
        *,
        broker_host: str,
        broker_port: int,
        topic: str,
        dsn: str,
        client_id: str,
        username: str = "",
        password: str = "",
        heartbeat_seconds: float = 30.0,
    ) -> None:
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic = topic
        self.dsn = dsn
        self.client_id = client_id
        self.username = username
        self.password = password
        self.heartbeat_seconds = heartbeat_seconds

        self._counters = _Counters()
        self._counters_lock = threading.Lock()
        self._conn: psycopg.Connection | None = None
        self._stop_heartbeat = threading.Event()

    # -- DB lifecycle ---------------------------------------------------

    def _connect_db(self) -> None:
        if self._conn is not None and not self._conn.closed:
            return
        self._conn = psycopg.connect(self.dsn, autocommit=False)
        log.info("mqtt_db_connected")

    def _ensure_db_alive(self) -> None:
        """Cheap liveness check; reconnect on broken connection."""
        if self._conn is None or self._conn.closed:
            self._connect_db()
            return
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
        except psycopg.Error:
            log.warning("mqtt_db_connection_dead_reconnecting")
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
            self._connect_db()

    # -- paho callbacks -------------------------------------------------

    def _on_connect(self, client: mqtt.Client, userdata, flags, reason_code, properties):
        log.info(
            "mqtt_broker_connected",
            host=self.broker_host,
            port=self.broker_port,
            reason_code=str(reason_code),
            topic=self.topic,
        )
        client.subscribe(self.topic, qos=1)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        log.warning("mqtt_broker_disconnected", reason_code=str(reason_code))

    def _on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        with self._counters_lock:
            self._counters.messages_received += 1

        try:
            payload_dict = json.loads(msg.payload)
        except json.JSONDecodeError as e:
            with self._counters_lock:
                self._counters.messages_dropped_parse_error += 1
            log.warning("mqtt_payload_not_json", topic=msg.topic, error=str(e))
            return

        try:
            self._ensure_db_alive()
            assert self._conn is not None
            with self._counters_lock:
                process_payload(self._conn, payload_dict, self._counters)
        except psycopg.Error as e:
            with self._counters_lock:
                self._counters.db_errors += 1
            log.exception("mqtt_db_error", topic=msg.topic, error=str(e))
            try:
                if self._conn is not None:
                    self._conn.rollback()
            except Exception:
                pass
        except Exception as e:
            log.exception("mqtt_handler_error", topic=msg.topic, error=str(e))

    # -- heartbeat ------------------------------------------------------

    def _heartbeat_loop(self) -> None:
        while not self._stop_heartbeat.wait(self.heartbeat_seconds):
            with self._counters_lock:
                snap = _Counters(
                    messages_received=self._counters.messages_received,
                    messages_dropped_pre_ntp=self._counters.messages_dropped_pre_ntp,
                    messages_dropped_parse_error=self._counters.messages_dropped_parse_error,
                    readings_inserted=self._counters.readings_inserted,
                    readings_duplicate=self._counters.readings_duplicate,
                    db_errors=self._counters.db_errors,
                    devices_seen=set(self._counters.devices_seen),
                )
            log.info(
                "mqtt_heartbeat",
                messages_received=snap.messages_received,
                messages_dropped_pre_ntp=snap.messages_dropped_pre_ntp,
                messages_dropped_parse_error=snap.messages_dropped_parse_error,
                readings_inserted=snap.readings_inserted,
                readings_duplicate=snap.readings_duplicate,
                db_errors=snap.db_errors,
                distinct_devices=len(snap.devices_seen),
            )

    # -- entry point ----------------------------------------------------

    def run_forever(self) -> None:
        self._connect_db()
        client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
        )
        if self.username:
            client.username_pw_set(self.username, self.password or None)
        client.reconnect_delay_set(min_delay=1, max_delay=60)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        log.info(
            "mqtt_subscriber_starting",
            host=self.broker_host,
            port=self.broker_port,
            topic=self.topic,
            client_id=self.client_id,
        )
        client.connect(self.broker_host, self.broker_port, keepalive=60)

        hb = threading.Thread(target=self._heartbeat_loop, name="mqtt-heartbeat", daemon=True)
        hb.start()

        try:
            client.loop_forever()
        except KeyboardInterrupt:
            log.info("mqtt_subscriber_stopping")
        finally:
            self._stop_heartbeat.set()
            try:
                client.disconnect()
            except Exception:
                pass
            if self._conn is not None and not self._conn.closed:
                self._conn.close()
            log.info(
                "mqtt_subscriber_stopped",
                final_messages=self._counters.messages_received,
                final_readings_inserted=self._counters.readings_inserted,
                final_duplicates=self._counters.readings_duplicate,
            )


def make_subscriber_from_settings() -> MqttSubscriber:
    s = get_settings()
    return MqttSubscriber(
        broker_host=s.mqtt_broker_host,
        broker_port=s.mqtt_broker_port,
        topic=s.mqtt_topic_readings,
        dsn=s.postgres_dsn,
        client_id=s.mqtt_client_id,
        username=s.mqtt_username,
        password=s.mqtt_password,
    )
