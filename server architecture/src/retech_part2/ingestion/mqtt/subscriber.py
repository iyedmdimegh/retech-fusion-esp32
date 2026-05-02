"""
Stub for MQTT ingestion. Phase 1 (ESP32) is not yet wired.

When ready, implement MqttSubscriber here following this contract:

  Topic pattern : retech/devices/+/readings
  QoS           : 1
  Payload schema: see docs/mqtt-payload.json (matches Phase 1 spec)

For each message:
  1. Validate against ReadingsPayload Pydantic model (in schemas.py).
  2. Upsert meta.devices (device_id, site, fw_version, last_seen=NOW()).
  3. Insert one row per element in payload.readings into timeseries.readings.
     Use payload.timestamp as `time` (NOT NOW() — Phase 1 buffers offline messages).
  4. Insert one row into timeseries.device_status with status, rssi, uptime_s,
     fw_version, drift_alert.

Offline detection (background task): if no message from a device in > 30s,
insert a synthetic row in device_status with status='offline'.
"""
from __future__ import annotations


class MqttSubscriber:
    def __init__(self, *, broker_host: str, broker_port: int) -> None:  # noqa: D401
        raise NotImplementedError("Phase 1 not ready — to be implemented")
