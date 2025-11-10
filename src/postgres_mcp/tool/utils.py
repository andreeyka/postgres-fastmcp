"""Utility functions for MCP tools."""

from __future__ import annotations

from typing import Any


def decode_bytes_to_utf8(obj: Any) -> Any:  # noqa: ANN401
    """Рекурсивно декодирует байты в UTF-8 строки для сериализации в JSON.

    Args:
        obj: Объект, который может содержать байты (dict, list, bytes, str, и т.д.)

    Returns:
        Объект с декодированными байтами в UTF-8 строки.
        Тип возвращаемого значения может быть любым JSON-сериализуемым типом.
    """
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except UnicodeDecodeError:
            # Если не удается декодировать как UTF-8, пробуем latin-1 (который всегда работает)
            return obj.decode("latin-1")
    if isinstance(obj, dict):
        return {key: decode_bytes_to_utf8(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [decode_bytes_to_utf8(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(decode_bytes_to_utf8(item) for item in obj)
    return obj
