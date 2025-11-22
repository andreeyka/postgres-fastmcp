"""Tests for health check endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr
from starlette.testclient import TestClient

from postgres_fastmcp.config import DatabaseConfig, get_settings
from postgres_fastmcp.server.http import HttpServerBuilder


class TestHealthEndpoint:
    """Test cases for health check endpoint."""

    def test_health_endpoint_enabled(self):
        """Test that health endpoint is accessible when enabled."""
        settings = get_settings(
            server={"transport": "http", "health_endpoint_enabled": True},
            databases={"db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1"))},
        )

        builder = HttpServerBuilder(settings)
        # Mock ToolManager
        mock_tools = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools)

        # Build the application
        app = builder.build()

        # Test health endpoint
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == settings.name
        assert "auth_enabled" in data

    def test_health_endpoint_disabled(self):
        """Test that health endpoint is not accessible when disabled."""
        settings = get_settings(
            server={"transport": "http", "health_endpoint_enabled": False},
            databases={"db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1"))},
        )

        builder = HttpServerBuilder(settings)
        # Mock ToolManager
        mock_tools = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools)

        # Build the application
        app = builder.build()

        # Test health endpoint should return 404
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 404

    def test_health_endpoint_with_auth_enabled(self):
        """Test that health endpoint shows auth_enabled=True when Keycloak is enabled."""
        settings = get_settings(
            server={"transport": "http", "health_endpoint_enabled": True},
            databases={"db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1"))},
            keycloak={
                "enabled": True,
                "realm": "test-realm",
                "server_url": "https://keycloak.example.com",
                "client_id": "test-client",
            },
        )

        builder = HttpServerBuilder(settings)
        # Mock ToolManager
        mock_tools = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools)

        # Build the application
        app = builder.build()

        # Test health endpoint
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == settings.name
        assert data["auth_enabled"] is True

    def test_health_endpoint_with_auth_disabled(self):
        """Test that health endpoint shows auth_enabled=False when Keycloak is disabled."""
        settings = get_settings(
            server={"transport": "http", "health_endpoint_enabled": True},
            databases={"db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1"))},
            keycloak={
                "enabled": False,
                "realm": "test-realm",
                "server_url": "https://keycloak.example.com",
                "client_id": "test-client",
            },
        )

        builder = HttpServerBuilder(settings)
        # Mock ToolManager
        mock_tools = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools)

        # Build the application
        app = builder.build()

        # Test health endpoint
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == settings.name
        assert data["auth_enabled"] is False

    def test_health_endpoint_no_authorization_required(self):
        """Test that health endpoint is accessible without authorization."""
        settings = get_settings(
            server={"transport": "http", "health_endpoint_enabled": True},
            databases={"db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1"))},
            keycloak={
                "enabled": True,
                "realm": "test-realm",
                "server_url": "https://keycloak.example.com",
                "client_id": "test-client",
            },
        )

        builder = HttpServerBuilder(settings)
        # Mock ToolManager
        mock_tools = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools)

        # Build the application
        app = builder.build()

        # Test health endpoint without authorization header
        client = TestClient(app)
        response = client.get("/health")

        # Should still work without auth token
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

