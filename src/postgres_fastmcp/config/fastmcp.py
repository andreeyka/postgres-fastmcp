"""FastMCP and middleware configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ErrorHandlingSettings(BaseSettings):
    """ErrorHandlingMiddleware settings."""

    model_config = SettingsConfigDict(env_prefix="MCP_ERROR_HANDLING_", extra="ignore")

    enabled: bool = Field(default=True, description="Enable ErrorHandlingMiddleware (MCP_ERROR_HANDLING_ENABLED)")
    include_traceback: bool = Field(
        default=False, description="Include full traceback in error logs (MCP_ERROR_HANDLING_TRACEBACK)"
    )
    transform_errors: bool = Field(
        default=True, description="Transform non-MCP errors to MCP errors (MCP_ERROR_HANDLING_TRANSFORM)"
    )


class RetrySettings(BaseSettings):
    """RetryMiddleware settings.

    IMPORTANT: By default, only temporary network errors are retried:
    - ConnectionError (connection issues)
    - TimeoutError (timeouts)

    Argument errors (ValueError, TypeError) and other logical errors
    are NOT retried, preventing infinite retries on incorrect model requests.
    """

    model_config = SettingsConfigDict(env_prefix="MCP_RETRY_", extra="ignore")

    enabled: bool = Field(default=True, description="Enable RetryMiddleware (MCP_RETRY_ENABLED)")
    max_retries: int = Field(default=3, description="Maximum number of retries (MCP_RETRY_MAX_RETRIES)")
    base_delay: float = Field(
        default=1.0, description="Base delay between retries in seconds (MCP_RETRY_BASE_DELAY)"
    )
    max_delay: float = Field(
        default=60.0, description="Maximum delay between retries in seconds (MCP_RETRY_MAX_DELAY)"
    )
    backoff_multiplier: float = Field(
        default=2.0, description="Exponential backoff multiplier (MCP_RETRY_BACKOFF_MULTIPLIER)"
    )


class CachingSettings(BaseSettings):
    """ResponseCachingMiddleware settings.

    IMPORTANT: By default, cache is stored in memory (MemoryStore).
    """

    model_config = SettingsConfigDict(env_prefix="MCP_CACHING_", extra="ignore")

    enabled: bool = Field(default=True, description="Enable ResponseCachingMiddleware (MCP_CACHING_ENABLED)")
    use_redis: bool = Field(
        default=False,
        description=(
            "Use Redis for cache instead of memory. "
            "Requires MCP_REDIS_* environment variables to be set (MCP_CACHING_USE_REDIS)"
        ),
    )
    max_item_size: int = Field(
        default=1024 * 1024, description="Maximum cache item size in bytes (MCP_CACHING_MAX_ITEM_SIZE)"
    )
    # TTL for methods with external requests (in seconds)
    call_tool_ttl: int = Field(default=300, description="TTL for tools/call in seconds (MCP_CACHING_CALL_TOOL_TTL)")
    read_resource_ttl: int = Field(
        default=300, description="TTL for resources/read in seconds (MCP_CACHING_READ_RESOURCE_TTL)"
    )
    get_prompt_ttl: int = Field(default=300, description="TTL for prompts/get in seconds (MCP_CACHING_GET_PROMPT_TTL)")
    # Exclusions for tools/call
    excluded_tools: list[str] = Field(
        default_factory=list, description="List of tools excluded from caching (MCP_CACHING_EXCLUDED_TOOLS)"
    )


class LoggingMiddlewareSettings(BaseSettings):
    """StructuredLoggingMiddleware settings."""

    model_config = SettingsConfigDict(env_prefix="MCP_LOGGING_", extra="ignore")

    enabled: bool = Field(default=False, description="Enable StructuredLoggingMiddleware (MCP_LOGGING_ENABLED)")
    log_level: str = Field(default="INFO", description="Log level (MCP_LOGGING_LEVEL)")
    include_payloads: bool = Field(default=False, description="Include payloads in logs (MCP_LOGGING_INCLUDE_PAYLOADS)")
    include_payload_length: bool = Field(
        default=True, description="Include payload length in logs (MCP_LOGGING_INCLUDE_PAYLOAD_LENGTH)"
    )
    estimate_payload_tokens: bool = Field(
        default=False, description="Estimate token count in payload (MCP_LOGGING_ESTIMATE_TOKENS)"
    )


class TimingMiddlewareSettings(BaseSettings):
    """TimingMiddleware settings."""

    model_config = SettingsConfigDict(env_prefix="MCP_TIMING_", extra="ignore")

    enabled: bool = Field(
        default=False, description="Enable TimingMiddleware for request timing (MCP_TIMING_ENABLED)"
    )
    log_level: str = Field(default="INFO", description="Log level (MCP_TIMING_LOG_LEVEL)")


class DetailedTimingMiddlewareSettings(BaseSettings):
    """DetailedTimingMiddleware settings."""

    model_config = SettingsConfigDict(env_prefix="MCP_DETAILED_TIMING_", extra="ignore")

    enabled: bool = Field(
        default=False,
        description=(
            "Enable DetailedTimingMiddleware for detailed operation timing (MCP_DETAILED_TIMING_ENABLED)"
        ),
    )
    log_level: str = Field(default="INFO", description="Log level (MCP_DETAILED_TIMING_LOG_LEVEL)")


class FastMCPSettings(BaseSettings):
    """FastMCP settings."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MCP_", extra="ignore")

    server_name: str = Field(default="postgres-fastmcp", description="MCP server name (MCP_SERVER_NAME)")
    mask_error_details: bool = Field(
        default=True, description="Mask internal error details for security (MCP_MASK_ERROR_DETAILS)"
    )
    return_errors_as_strings: bool = Field(
        default=True,
        description="Return errors as strings in LLM responses instead of standard MCP errors",
    )
    error_traceback_in_strings: bool = Field(
        default=False, description="Include traceback in error strings when return_errors_as_strings=True"
    )

    # Middleware settings
    error_handling: ErrorHandlingSettings = Field(default_factory=ErrorHandlingSettings)
    retry: RetrySettings = Field(default_factory=RetrySettings)
    caching: CachingSettings = Field(default_factory=CachingSettings)
    logging_middleware: LoggingMiddlewareSettings = Field(default_factory=LoggingMiddlewareSettings)
    timing: TimingMiddlewareSettings = Field(default_factory=TimingMiddlewareSettings)
    detailed_timing: DetailedTimingMiddlewareSettings = Field(default_factory=DetailedTimingMiddlewareSettings)

