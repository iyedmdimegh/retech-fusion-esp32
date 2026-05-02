"""Seed the database with the minimum fixtures required for downstream queries.

Currently inserts one fake device into meta.devices so that any future MQTT-side
query / FK insert doesn't blow up before Phase 1 is wired.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from retech_part2.db import get_session_factory
from retech_part2.logging import configure_logging, get_logger

SEED_DEVICE_ID = "esp32-dev-001"
SEED_SITE = "INSAT-Lab"
SEED_FW_VERSION = "0.1.0-stub"


async def seed() -> None:
    log = get_logger("seed")
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO meta.devices (device_id, site, fw_version)
                VALUES (:device_id, :site, :fw_version)
                ON CONFLICT (device_id) DO NOTHING
                RETURNING device_id
                """
            ),
            {
                "device_id": SEED_DEVICE_ID,
                "site": SEED_SITE,
                "fw_version": SEED_FW_VERSION,
            },
        )
        inserted = result.first()
        await session.commit()

        if inserted:
            log.info("seed_inserted", device_id=SEED_DEVICE_ID)
        else:
            log.info("seed_already_present", device_id=SEED_DEVICE_ID)


def main() -> None:
    configure_logging()
    asyncio.run(seed())


if __name__ == "__main__":
    main()
