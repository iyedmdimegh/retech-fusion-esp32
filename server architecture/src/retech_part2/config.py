from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ExtractionStrategy = Literal[
    "qwen_then_regex",
    "qwen_only",
    "regex_only",
    "regex_then_qwen",
]
LogFormat = Literal["console", "json"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Postgres ----
    postgres_user: str = "retech"
    postgres_password: str = "retech"
    postgres_db: str = "retech"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn(self) -> str:
        """Plain libpq URL for raw psycopg connections (no SQLAlchemy prefix)."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ---- Redis ----
    redis_host: str = "localhost"
    redis_port: int = 6379

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    # ---- MQTT (Phase 1 — live) ----
    # Default broker host targets the Windows Mobile Hotspot adapter the ESP32
    # nodes associate to. Override via .env when the host's hotspot IP differs.
    mqtt_broker_host: str = "192.168.137.1"
    mqtt_broker_port: int = 1883
    mqtt_topic_readings: str = "retech/devices/+/readings"
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_client_id: str = "retech_part2_ingestor"

    # ---- Invoice extraction ----
    extraction_strategy: ExtractionStrategy = "qwen_then_regex"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5vl:3b"
    min_confidence: float = 0.8

    # ---- Filesystem ----
    inbox_xlsx_path: str = "inbox/xlsx"
    inbox_pdf_path: str = "inbox/pdf"
    ocr_cache_path: str = "data/ocr_cache"

    # ---- OCR toolchain ----
    # Optional absolute paths for installs that aren't on PATH (typical on Windows).
    # Leave blank to use PATH-resolved binaries.
    tesseract_cmd: str = ""
    poppler_path: str = ""
    pdf_render_dpi: int = 300

    # ---- Logging ----
    log_level: str = "INFO"
    log_format: LogFormat = "console"

    # ---- API ----
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ---- CO₂ analytics (M12) ----
    # Emission factors. Override in .env if regulator/utility figures change.
    # Defaults: gas factor derived from PCI 9.082 thermie/Nm³ (BILAN sheet header)
    # and CH₄/C₂H₆ stoichiometry; grid factor from STEG 2023 sustainability report.
    co2_gas_factor_kg_per_nm3: float = 1.96
    co2_grid_factor_kg_per_kwh: float = 0.47

    # Forecast horizons in HOURS — applied AFTER hourly resampling.
    # Comma-separated string parsed at use site (pydantic-settings keeps it simple).
    co2_horizons: str = "1,6,24"
    co2_test_ratio: float = 0.2
    co2_anomaly_contamination: float = 0.02

    # Where joblib pickles get written. Gitignored.
    co2_models_dir: str = "data/models"

    @property
    def co2_horizons_list(self) -> list[int]:
        return [int(x) for x in self.co2_horizons.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
