"""
config.py — Centralised settings for the Ollama Platform gateway.

All values can be overridden via environment variables or the .env file.
Structured config (nodes.yaml, models.yaml) is loaded once at startup and
cached on the Settings object.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Gateway ───────────────────────────────────────────────────────────────
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8000
    log_level: str = "info"

    # ── Auth ──────────────────────────────────────────────────────────────────
    # Stored as a comma-separated string in .env; exposed as a frozenset.
    api_keys: str = "change-me-key-1"

    @field_validator("api_keys", mode="before")
    @classmethod
    def _normalise_keys(cls, v: Any) -> str:
        """Accept a list (from code) or a comma-separated string (from env)."""
        if isinstance(v, (list, tuple, set, frozenset)):
            return ",".join(str(k) for k in v)
        return str(v)

    @property
    def api_key_set(self) -> frozenset[str]:
        return frozenset(k.strip() for k in self.api_keys.split(",") if k.strip())

    # ── Config file paths ─────────────────────────────────────────────────────
    nodes_config: str = "nodes.yaml"
    models_config: str = "models.yaml"

    # ── Health check ──────────────────────────────────────────────────────────
    health_check_interval: int = 15     # seconds
    health_check_failures: int = 2      # consecutive failures → degraded
    health_check_timeout: int = 5       # per-request timeout (seconds)

    # ── Database ──────────────────────────────────────────────────────────────
    database_path: str = "data/platform.db"

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def db_dir(self) -> Path:
        return Path(self.database_path).parent

    def load_nodes_config(self) -> list[dict]:
        """Parse nodes.yaml and return the list of node dicts."""
        path = Path(self.nodes_config)
        if not path.exists():
            raise FileNotFoundError(f"Nodes config not found: {path.resolve()}")
        with path.open() as f:
            data = yaml.safe_load(f)
        return data.get("nodes", [])

    def load_models_config(self) -> list[dict]:
        """Parse models.yaml and return the list of model dicts."""
        path = Path(self.models_config)
        if not path.exists():
            raise FileNotFoundError(f"Models config not found: {path.resolve()}")
        with path.open() as f:
            data = yaml.safe_load(f)
        return data.get("models", [])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
