"""Types for MCP server configuration."""

from enum import StrEnum
from typing import Literal


# Transport types for configuration
TransportConfig = Literal["http", "http_streamable", "stdio"]

# Transport types for FastMCP http_app
TransportHttpApp = Literal["http", "streamable-http"]

# Mount mode types
MountMode = Literal["tool", "endpoint"]


class AccessMode(StrEnum):
    """SQL access modes for the server."""

    UNRESTRICTED = "unrestricted"  # Unrestricted access
    RESTRICTED = "restricted"  # Read-only with safety features
