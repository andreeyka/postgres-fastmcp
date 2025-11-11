"""Utility functions for MCP tools."""

from __future__ import annotations

from typing import Any


def decode_bytes_to_utf8(obj: Any) -> Any:  # noqa: ANN401
    """Recursively decode bytes to UTF-8 strings for JSON serialization.

    Args:
        obj: Object that may contain bytes (dict, list, bytes, str, etc.)

    Returns:
        Object with decoded bytes as UTF-8 strings.
        Return type can be any JSON-serializable type.
    """
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except UnicodeDecodeError:
            # If UTF-8 decoding fails, try latin-1 (which always works)
            return obj.decode("latin-1")
    if isinstance(obj, dict):
        return {key: decode_bytes_to_utf8(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [decode_bytes_to_utf8(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(decode_bytes_to_utf8(item) for item in obj)
    return obj
