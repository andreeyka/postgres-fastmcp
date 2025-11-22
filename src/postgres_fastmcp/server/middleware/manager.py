"""Manager for configuring and adding middleware to FastMCP server."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastmcp.server.middleware.caching import (
    CallToolSettings,
    GetPromptSettings,
    ListPromptsSettings,
    ListResourcesSettings,
    ListToolsSettings,
    ReadResourceSettings,
    ResponseCachingMiddleware,
)
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware, RetryMiddleware
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware
from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware
from fastmcp.server.middleware.timing import DetailedTimingMiddleware, TimingMiddleware

from postgres_fastmcp.logger import get_logger
from postgres_fastmcp.server.middleware.error_to_string import ErrorToStringMiddleware


if TYPE_CHECKING:
    from fastmcp import FastMCP
    from fastmcp.server.auth.auth import TokenVerifier

    from postgres_fastmcp.config import Settings


logger = get_logger(__name__)


class MiddlewareManager:
    """Manager for configuring and adding middleware to FastMCP server.

    IMPORTANT: Middleware order is critical!
    Middleware are executed in the order they are added (first added = first on entry, last on exit).
    This means the first middleware intercepts errors last (outermost layer).
    """

    def __init__(self, mcp: FastMCP, settings: Settings, auth: TokenVerifier | None = None) -> None:
        """Initialize middleware manager.

        Args:
            mcp: FastMCP server instance.
            settings: Application settings.
            auth: Token verifier (optional).
        """
        self.mcp = mcp
        self.settings = settings
        self.auth = auth
        self.server_name = getattr(mcp, "name", None)

    def setup_all(self) -> None:
        """Configure and add all middleware in the correct order."""
        self._setup_error_to_string_middleware()
        self._setup_error_handling_middleware()
        self._setup_retry_middleware()
        self._setup_caching_middleware()
        self._setup_logging_middleware()
        self._setup_timing_middleware()
        self._setup_rate_limiting_middleware()

    def _setup_error_to_string_middleware(self) -> None:
        """Configure ErrorToStringMiddleware (outermost layer)."""
        if not self.settings.fastmcp.return_errors_as_strings:
            return

        self.mcp.add_middleware(
            ErrorToStringMiddleware(
                include_traceback=self.settings.fastmcp.error_traceback_in_strings,
            )
        )
        if self.server_name:
            logger.info(
                "Server '%s': Error-to-string middleware enabled: "
                "errors will be returned as strings in LLM responses (traceback: %s)",
                self.server_name,
                "enabled" if self.settings.fastmcp.error_traceback_in_strings else "disabled",
            )
        else:
            logger.info(
                "Error-to-string middleware enabled: "
                "errors will be returned as strings in LLM responses (traceback: %s)",
                "enabled" if self.settings.fastmcp.error_traceback_in_strings else "disabled",
            )

    def _setup_error_handling_middleware(self) -> None:
        """Configure ErrorHandlingMiddleware for error logging and monitoring."""
        if not self.settings.fastmcp.error_handling.enabled:
            return

        self.mcp.add_middleware(
            ErrorHandlingMiddleware(
                logger=logger,
                include_traceback=self.settings.fastmcp.error_handling.include_traceback,
                transform_errors=self.settings.fastmcp.error_handling.transform_errors,
            )
        )
        if self.server_name:
            logger.info(
                "Server '%s': Error handling middleware enabled: error logging and monitoring", self.server_name
            )
        else:
            logger.info("Error handling middleware enabled: error logging and monitoring")

    def _setup_retry_middleware(self) -> None:
        """Configure RetryMiddleware for automatic retries of external API calls."""
        if not self.settings.fastmcp.retry.enabled:
            return

        self.mcp.add_middleware(
            RetryMiddleware(
                max_retries=self.settings.fastmcp.retry.max_retries,
                base_delay=self.settings.fastmcp.retry.base_delay,
                max_delay=self.settings.fastmcp.retry.max_delay,
                backoff_multiplier=self.settings.fastmcp.retry.backoff_multiplier,
                logger=logger,
            )
        )
        if self.server_name:
            logger.info(
                "Server '%s': Retry middleware enabled: max_retries=%d, base_delay=%.1fs",
                self.server_name,
                self.settings.fastmcp.retry.max_retries,
                self.settings.fastmcp.retry.base_delay,
            )
        else:
            logger.info(
                "Retry middleware enabled: max_retries=%d, base_delay=%.1fs",
                self.settings.fastmcp.retry.max_retries,
                self.settings.fastmcp.retry.base_delay,
            )

    def _setup_caching_middleware(self) -> None:
        """Configure ResponseCachingMiddleware for response caching."""
        if not self.settings.fastmcp.caching.enabled:
            return

        cache_storage = self._get_cache_storage()
        storage_type = "Redis" if cache_storage else "Memory"

        self.mcp.add_middleware(
            ResponseCachingMiddleware(
                cache_storage=cache_storage,  # None = MemoryStore by default
                # List methods are not cached (they are fast, data from memory)
                list_tools_settings=ListToolsSettings(enabled=False),
                list_resources_settings=ListResourcesSettings(enabled=False),
                list_prompts_settings=ListPromptsSettings(enabled=False),
                call_tool_settings=CallToolSettings(
                    ttl=self.settings.fastmcp.caching.call_tool_ttl,
                    enabled=True,
                    excluded_tools=self.settings.fastmcp.caching.excluded_tools,
                ),
                read_resource_settings=ReadResourceSettings(
                    ttl=self.settings.fastmcp.caching.read_resource_ttl,
                    enabled=True,
                ),
                get_prompt_settings=GetPromptSettings(
                    ttl=self.settings.fastmcp.caching.get_prompt_ttl,
                    enabled=True,
                ),
                max_item_size=self.settings.fastmcp.caching.max_item_size,
            )
        )
        if self.server_name:
            logger.info(
                "Server '%s': Response caching middleware enabled (%s): tools/call=%ds, excluded_tools=%s",
                self.server_name,
                storage_type,
                self.settings.fastmcp.caching.call_tool_ttl,
                self.settings.fastmcp.caching.excluded_tools or "none",
            )
        else:
            logger.info(
                "Response caching middleware enabled (%s): tools/call=%ds, excluded_tools=%s",
                storage_type,
                self.settings.fastmcp.caching.call_tool_ttl,
                self.settings.fastmcp.caching.excluded_tools or "none",
            )

    def _get_cache_storage(self) -> Any:  # noqa: ANN401
        """Get cache storage (Redis or None for memory).

        Returns:
            RedisStore if Redis is enabled and available, otherwise None.
        """
        if not self.settings.fastmcp.caching.use_redis:
            return None

        try:
            # Import RedisStore only if Redis is needed
            from key_value.aio.stores.redis import RedisStore  # noqa: PLC0415

            cache_storage = RedisStore(
                host=self.settings.redis.HOST,
                port=self.settings.redis.PORT,
                db=self.settings.redis.DB,
                password=self.settings.redis.PASSWORD.get_secret_value() if self.settings.redis.PASSWORD else None,
            )
            if self.server_name:
                logger.info(
                    "Server '%s': Using Redis for cache storage: %s:%d/%d",
                    self.server_name,
                    self.settings.redis.HOST,
                    self.settings.redis.PORT,
                    self.settings.redis.DB,
                )
            else:
                logger.info(
                    "Using Redis for cache storage: %s:%d/%d",
                    self.settings.redis.HOST,
                    self.settings.redis.PORT,
                    self.settings.redis.DB,
                )
        except ImportError:
            if self.server_name:
                logger.warning(
                    "Server '%s': Redis support requires 'key-value' and 'redis' packages. "
                    "Install them with: uv add key-value redis. Falling back to memory cache.",
                    self.server_name,
                )
            else:
                logger.warning(
                    "Redis support requires 'key-value' and 'redis' packages. "
                    "Install them with: uv add key-value redis. Falling back to memory cache."
                )
            return None
        except Exception as e:
            if self.server_name:
                logger.warning(
                    "Server '%s': Failed to initialize Redis cache storage, falling back to memory: %s",
                    self.server_name,
                    e,
                )
            else:
                logger.warning(
                    "Failed to initialize Redis cache storage, falling back to memory: %s",
                    e,
                )
            return None  # MemoryStore will be used by default
        else:
            return cache_storage

    def _setup_logging_middleware(self) -> None:
        """Configure StructuredLoggingMiddleware for structured logging."""
        if not self.settings.fastmcp.logging_middleware.enabled:
            return

        log_level = getattr(logging, self.settings.fastmcp.logging_middleware.log_level.upper(), logging.INFO)
        self.mcp.add_middleware(
            StructuredLoggingMiddleware(
                logger=logger,
                log_level=log_level,
                include_payloads=self.settings.fastmcp.logging_middleware.include_payloads,
                include_payload_length=self.settings.fastmcp.logging_middleware.include_payload_length,
                estimate_payload_tokens=self.settings.fastmcp.logging_middleware.estimate_payload_tokens,
            )
        )
        if self.server_name:
            logger.info(
                "Server '%s': Structured logging middleware enabled: level=%s, payloads=%s",
                self.server_name,
                self.settings.fastmcp.logging_middleware.log_level,
                "enabled" if self.settings.fastmcp.logging_middleware.include_payloads else "disabled",
            )
        else:
            logger.info(
                "Structured logging middleware enabled: level=%s, payloads=%s",
                self.settings.fastmcp.logging_middleware.log_level,
                "enabled" if self.settings.fastmcp.logging_middleware.include_payloads else "disabled",
            )

    def _setup_timing_middleware(self) -> None:
        """Configure TimingMiddleware or DetailedTimingMiddleware for timing measurements."""
        detailed_enabled = self.settings.fastmcp.detailed_timing.enabled
        timing_enabled = self.settings.fastmcp.timing.enabled

        # DetailedTimingMiddleware is more detailed, so it has priority
        if detailed_enabled:
            log_level = getattr(logging, self.settings.fastmcp.detailed_timing.log_level.upper(), logging.INFO)
            self.mcp.add_middleware(DetailedTimingMiddleware(logger=logger, log_level=log_level))
            if self.server_name:
                logger.info(
                    "Server '%s': Detailed timing middleware enabled: level=%s "
                    "(MCP_TIMING_ENABLED ignored due to priority)",
                    self.server_name,
                    self.settings.fastmcp.detailed_timing.log_level,
                )
            else:
                logger.info(
                    "Detailed timing middleware enabled: level=%s (MCP_TIMING_ENABLED ignored due to priority)",
                    self.settings.fastmcp.detailed_timing.log_level,
                )
        elif timing_enabled:
            log_level = getattr(logging, self.settings.fastmcp.timing.log_level.upper(), logging.INFO)
            self.mcp.add_middleware(TimingMiddleware(logger=logger, log_level=log_level))
            if self.server_name:
                logger.info(
                    "Server '%s': Timing middleware enabled: level=%s",
                    self.server_name,
                    self.settings.fastmcp.timing.log_level,
                )
            else:
                logger.info("Timing middleware enabled: level=%s", self.settings.fastmcp.timing.log_level)
        elif self.server_name:
            logger.info(
                "Server '%s': Timing middleware disabled: "
                "both MCP_DETAILED_TIMING_ENABLED and MCP_TIMING_ENABLED are false",
                self.server_name,
            )
        else:
            logger.info("Timing middleware disabled: both MCP_DETAILED_TIMING_ENABLED and MCP_TIMING_ENABLED are false")

    def _setup_rate_limiting_middleware(self) -> None:
        """Configure RateLimitingMiddleware for request rate limiting (innermost layer)."""
        if not self.auth:
            return

        # Limit: 100 requests per minute, with burst capacity up to 20 requests
        self.mcp.add_middleware(
            RateLimitingMiddleware(
                max_requests_per_second=100.0 / 60.0,  # ~1.67 requests per second
                burst_capacity=20,  # Allow burst up to 20 requests
            )
        )
        if self.server_name:
            logger.info("Server '%s': Rate limiting enabled: protection against token brute force", self.server_name)
        else:
            logger.info("Rate limiting enabled: protection against token brute force")
