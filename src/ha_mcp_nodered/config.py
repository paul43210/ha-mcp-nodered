"""Configuration loaded from environment variables / .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_env() -> None:
    """Load .env from cwd if it exists.

    Honours $HAMCP_NODERED_ENV_FILE for explicit overrides (e.g. when systemd
    points at /etc/ha-mcp-nodered/env). Silent on missing files — env vars
    may come from systemd directly.
    """
    explicit = os.getenv("HAMCP_NODERED_ENV_FILE")
    if explicit:
        path = Path(explicit)
        if path.exists():
            load_dotenv(path)
            return
    default = Path.cwd() / ".env"
    if default.exists():
        load_dotenv(default)


_load_env()


class Settings(BaseSettings):
    """Runtime configuration for ha-mcp-nodered."""

    nodered_url: str = Field(..., alias="NODERED_URL")
    nodered_username: str = Field(..., alias="NODERED_USERNAME")
    nodered_password: str = Field(..., alias="NODERED_PASSWORD")
    timeout: int = Field(30, alias="NODERED_TIMEOUT")

    log_level: str = Field("INFO", alias="LOG_LEVEL")

    mcp_server_name: str = Field("ha-mcp-nodered", alias="MCP_SERVER_NAME")

    @field_validator("nodered_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("NODERED_URL must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(valid)}")
        return upper

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Singleton accessor for Settings — instantiated lazily on first call."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
