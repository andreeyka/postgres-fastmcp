"""Types for MCP server configuration."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal


# Mount mode types
MountMode = Literal["tool", "endpoint"]


class AccessMode(StrEnum):
    """SQL access modes for the server."""

    # User modes (only public schema)
    USER_RO = "user_ro"  # User mode: only public schema, read-only, basic tools
    USER_RW = "user_rw"  # User mode: only public schema, read-write (DML), basic tools

    # Admin modes (all schemas)
    ADMIN_RO = "admin_ro"  # Admin mode: all schemas, read-only, all tools
    ADMIN_RW = "admin_rw"  # Admin mode: all schemas, full access (including DDL), all tools

    @property
    def is_user_mode(self) -> bool:
        """Check if the access mode is a user mode (limited to public schema).

        Returns:
            True if the mode is USER_RO or USER_RW, False otherwise.
        """
        return self in (AccessMode.USER_RO, AccessMode.USER_RW)

    @property
    def is_read_only(self) -> bool:
        """Check if the access mode is read-only.

        Returns:
            True if the mode is USER_RO or ADMIN_RO, False otherwise.
        """
        return self in (AccessMode.USER_RO, AccessMode.ADMIN_RO)

    @property
    def allowed_schema(self) -> str | None:
        """Get the allowed schema for this access mode.

        Returns:
            'public' for user modes, None for admin modes (all schemas allowed).
        """
        if self.is_user_mode:
            return "public"
        return None


class TransportConfig(StrEnum):
    """Transport types for configuration."""

    HTTP = "http"
    STDIO = "stdio"


class TransportHttpApp(StrEnum):
    """HTTP transport types for FastMCP http_app."""

    HTTP = "http"
    STREAMABLE_HTTP = "streamable-http"
