"""Middleware for converting errors to strings in LLM responses."""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp import McpError

from postgres_fastmcp.logger import get_logger


if TYPE_CHECKING:
    from fastmcp.server.middleware.middleware import CallNext
    from mcp.types import CallToolRequestParams


logger = get_logger(__name__)


class ErrorToStringMiddleware(Middleware):
    """Middleware that intercepts all errors and returns them as strings in LLM responses.

    Instead of standard MCP protocol errors, all exceptions are converted to strings
    and returned as successful tool execution results.

    Example:
        ```python
        from postgres_fastmcp.server.middleware import ErrorToStringMiddleware

        mcp = FastMCP("MyServer")
        mcp.add_middleware(ErrorToStringMiddleware(include_traceback=False))
        ```
    """

    def __init__(
        self,
        *,
        include_traceback: bool = False,
    ) -> None:
        """Initialize middleware for converting errors to strings.

        Args:
            include_traceback: Whether to include full traceback in error message.
        """
        self.include_traceback = include_traceback

    def _format_error_as_string(self, error: Exception) -> str:
        """Convert exception to a readable string.

        Args:
            error: Exception to convert.

        Returns:
            String with error description.
        """
        # For ToolError, use message directly (already contains description)
        if isinstance(error, ToolError):
            error_message = str(error)
        # For McpError, extract message from ErrorData
        elif isinstance(error, McpError):
            if hasattr(error, "data") and error.data:
                error_message = str(error.data.message) if hasattr(error.data, "message") else str(error)
            else:
                error_message = str(error)
        # For other exceptions, use string representation
        else:
            error_message = str(error) or repr(error)

        # Add traceback if required
        if self.include_traceback:
            tb_str = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            return f"{error_message}\n\nTraceback:\n{tb_str}"

        return error_message

    def _get_tool_name(self, context: MiddlewareContext) -> str:
        """Get tool name from context.

        Args:
            context: Middleware context.

        Returns:
            Tool name or "unknown".
        """
        if hasattr(context, "message") and context.message:
            return getattr(context.message, "name", "unknown")
        return "unknown"

    async def _get_tool_output_schema(self, context: MiddlewareContext, tool_name: str) -> dict[str, Any] | None:
        """Get tool outputSchema.

        Args:
            context: Middleware context.
            tool_name: Tool name.

        Returns:
            Tool output schema or None.
        """
        if not hasattr(context, "fastmcp_context") or not context.fastmcp_context:
            return None

        try:
            tool = await context.fastmcp_context.fastmcp.get_tool(tool_name)
            if tool and hasattr(tool, "output_schema") and tool.output_schema:
                return tool.output_schema
        except Exception as e:
            logger.warning("Could not get tool info for '%s': %s", tool_name, e)

        return None

    def _build_structured_content(self, output_schema: dict[str, Any], error_string: str) -> dict[str, str]:
        """Build structured_content based on output schema.

        Args:
            output_schema: Tool output schema.
            error_string: Error string.

        Returns:
            Dictionary with structured_content in format matching the schema.
        """
        # By default, use "result" field
        structured_content = {"result": error_string}

        if not isinstance(output_schema, dict):
            return structured_content

        properties = output_schema.get("properties", {})
        required = output_schema.get("required", [])

        # If "result" field exists, use it
        if "result" in properties:
            structured_content = {"result": error_string}
        # Otherwise, use first required field
        elif required:
            first_required = required[0]
            structured_content = {first_required: error_string}
        # Otherwise, use first field from properties
        elif properties:
            first_prop = next(iter(properties.keys()))
            structured_content = {first_prop: error_string}

        return structured_content

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Intercept tool call and convert errors to strings.

        Args:
            context: Middleware context with request information.
            call_next: Function to call next middleware or tool.

        Returns:
            ToolResult with tool execution result or error string.
        """
        tool_name = self._get_tool_name(context)

        try:
            return await call_next(context)
        except Exception as error:
            error_type = type(error).__name__
            logger.error(
                "Error in tool '%s': %s: %s",
                tool_name,
                error_type,
                str(error),
                exc_info=self.include_traceback,
            )

            error_string = self._format_error_as_string(error)
            output_schema = await self._get_tool_output_schema(context, tool_name)

            if output_schema:
                structured_content = self._build_structured_content(output_schema, error_string)
                return ToolResult(
                    content=error_string,
                    structured_content=structured_content,
                )

            return ToolResult(content=error_string)
