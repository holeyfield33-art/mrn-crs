"""MRN Constrained CRS – configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service URLs
    aletheia_url: str = "http://localhost:8300"
    geometric_url: str = "http://localhost:8200"
    mneme_url: str = "http://localhost:8100"

    # API key auth (comma-separated list; empty = auth disabled)
    crs_api_keys: str = ""

    # Rate limiting
    crs_rate_limit_per_minute: int = 60
    redis_url: str = ""

    # Self-healing
    enable_self_healing: bool = True
    self_heal_interval_seconds: int = 60
    self_heal_drift_threshold: float = 0.5
    self_heal_healthy_r_min: float = 0.57
    self_heal_healthy_r_max: float = 0.59
    self_heal_healthy_shi_min: float = 0.8
    self_heal_min_memories: int = 10

    # Self-healing action levels (drift thresholds)
    self_heal_level_low: float = 0.02
    self_heal_level_medium: float = 0.05
    self_heal_level_high: float = 0.10

    # Self-healing escalation webhook (optional)
    self_heal_escalation_webhook: str = ""
    self_heal_escalation_file: str = "escalations.jsonl"

    # Healing history SQLite path
    healing_history_db: str = "healing_history.db"

    # Sampling temperature (mutable at runtime via self-healing)
    sampling_temperature: float = 0.7

    # Logging
    log_level: str = "INFO"

    # Aletheia secrets
    aletheia_receipt_secret: str = "changeme"
    aletheia_api_keys: str = "deepseek_v4,perplexity"

    # Mneme / storage
    personal_mode: bool = True
    database_url: str = "sqlite:///./dev.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
