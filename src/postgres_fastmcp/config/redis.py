"""Redis configuration."""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisConfig(BaseSettings):
    """Redis configuration."""

    model_config = SettingsConfigDict(env_prefix="MCP_REDIS_", extra="ignore")

    HOST: str = Field(default="localhost", description="Redis host")
    PORT: int = Field(default=6379, description="Redis port")
    DB: int = Field(default=0, description="Redis database number")
    PASSWORD: SecretStr | None = Field(
        default=None, description="Redis password (optional, if not set, connection without password)"
    )
    DECODE_RESPONSES: bool = Field(default=True, description="Decode Redis responses as strings")
