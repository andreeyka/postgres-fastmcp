"""Authentication helper functions for FastMCP server."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp.server.auth.providers.jwt import JWTVerifier

from postgres_fastmcp.logger import get_logger


if TYPE_CHECKING:
    from fastmcp.server.auth.auth import TokenVerifier

    from postgres_fastmcp.config import Settings

logger = get_logger(__name__)


def build_keycloak_auth(settings: Settings, server_name: str | None = None) -> TokenVerifier | None:
    """Create Keycloak authentication provider if enabled.

    Args:
        settings: Global application configuration.
        server_name: Optional server name for logging purposes.

    Returns:
        TokenVerifier | None: Token verification provider or None if Keycloak is disabled.
    """
    if settings.keycloak is None:
        if server_name:
            logger.warning(
                "Server '%s': Keycloak configuration is missing. "
                "Set MCP_KEYCLOAK_REALM and MCP_KEYCLOAK_CLIENT_ID environment variables. "
                "Authentication will be disabled.",
                server_name,
            )
        else:
            logger.warning(
                "Keycloak configuration is missing. "
                "Set MCP_KEYCLOAK_REALM and MCP_KEYCLOAK_CLIENT_ID environment variables. "
                "Authentication will be disabled."
            )
        return None

    keycloak_config = settings.keycloak

    if not keycloak_config.enabled:
        if server_name:
            logger.info(
                "Server '%s': Keycloak authentication is disabled (MCP_KEYCLOAK_ENABLED=false). "
                "Authentication will not be used.",
                server_name,
            )
        else:
            logger.info(
                "Keycloak authentication is disabled (MCP_KEYCLOAK_ENABLED=false). Authentication will not be used."
            )
        return None
    # Build Keycloak URLs from server_url and realm
    # Standard Keycloak endpoints:
    # - issuer: {server_url}/realms/{realm}
    # - jwks_uri: {server_url}/realms/{realm}/protocol/openid-connect/certs
    base_url = keycloak_config.server_url.rstrip("/")
    issuer = f"{base_url}/realms/{keycloak_config.realm}"
    jwks_uri = f"{base_url}/realms/{keycloak_config.realm}/protocol/openid-connect/certs"

    # Use audience if provided, otherwise use client_id
    audience = keycloak_config.audience or keycloak_config.client_id

    if server_name:
        logger.info(
            "Server '%s': Keycloak JWT auth enabled: realm=%s, issuer=%s",
            server_name,
            keycloak_config.realm,
            issuer,
        )
    else:
        logger.info("Keycloak JWT auth enabled: realm=%s, issuer=%s", keycloak_config.realm, issuer)

    return JWTVerifier(
        jwks_uri=jwks_uri,
        audience=audience,
        issuer=issuer,
        required_scopes=keycloak_config.required_scopes if keycloak_config.required_scopes else None,
        base_url=base_url,
    )


__all__ = ["build_keycloak_auth"]
