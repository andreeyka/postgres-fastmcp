"""Utilities for working with PostgreSQL extensions."""

import logging
from dataclasses import dataclass
from typing import Literal

from .safe_sql import SafeSqlDriver
from .sql_driver import DbConnPool, SqlDriver


logger = logging.getLogger(__name__)

# Error messages
_ERROR_DETERMINING_VERSION = "Error determining PostgreSQL version"


class PostgresVersionRegistry:
    """Registry for caching PostgreSQL versions per connection.

    Manages version cache for multiple database connections, allowing
    each connection to have its own cached version.
    """

    def __init__(self) -> None:
        """Initialize the registry with empty cache."""
        self._cache: dict[str, int] = {}

    def get(self, connection_id: str) -> int | None:
        """Get cached version for a connection.

        Args:
            connection_id: Connection identifier.

        Returns:
            Cached version number or None if not cached.
        """
        return self._cache.get(connection_id)

    def set(self, connection_id: str, version: int) -> None:
        """Cache version for a connection.

        Args:
            connection_id: Connection identifier.
            version: Major PostgreSQL version number.
        """
        self._cache[connection_id] = version

    def clear(self, connection_id: str | None = None) -> None:
        """Clear cache for a connection or all connections.

        Args:
            connection_id: Optional connection identifier to clear cache for specific connection.
                          If None, clears the entire cache.
        """
        if connection_id is not None:
            self._cache.pop(connection_id, None)
        else:
            self._cache.clear()


# Global registry instance
_postgres_version_registry = PostgresVersionRegistry()


@dataclass
class ExtensionStatus:
    """Status of an extension."""

    is_installed: bool
    is_available: bool
    name: str
    message: str
    default_version: str | None


def _get_connection_id(sql_driver: SqlDriver, _visited: set[int] | None = None) -> str:
    """Get a unique identifier for the database connection.

    Args:
        sql_driver: An instance of SqlDriver to get connection identifier from
        _visited: Internal set to track visited objects and prevent infinite recursion

    Returns:
        Connection identifier string (connection_url, engine_url, or id-based fallback)
    """
    if _visited is None:
        _visited = set()

    # Prevent infinite recursion
    driver_id = id(sql_driver)
    if driver_id in _visited:
        return f"driver_{driver_id}"
    _visited.add(driver_id)

    # Handle SafeSqlDriver wrapper - it stores the underlying driver in sql_driver attribute
    if hasattr(sql_driver, "sql_driver"):
        underlying_driver = getattr(sql_driver, "sql_driver", None)
        if underlying_driver is not None and underlying_driver is not sql_driver:
            # Recursively get connection ID from the underlying driver
            return _get_connection_id(underlying_driver, _visited)

    # If connection is a DbConnPool, use its connection_url
    if (
        hasattr(sql_driver, "conn")
        and sql_driver.conn
        and isinstance(sql_driver.conn, DbConnPool)
        and sql_driver.conn.connection_url
    ):
        return sql_driver.conn.connection_url

    # If SqlDriver has engine_url, use it
    if hasattr(sql_driver, "engine_url") and sql_driver.engine_url:
        return sql_driver.engine_url

    # Fallback: use id of the connection object
    if hasattr(sql_driver, "conn") and sql_driver.conn:
        return f"conn_{id(sql_driver.conn)}"

    # Last resort: use id of sql_driver itself
    return f"driver_{id(sql_driver)}"


def reset_postgres_version_cache(connection_id: str | None = None) -> None:
    """Reset the PostgreSQL version cache. Primarily used for testing.

    Args:
        connection_id: Optional connection identifier to reset cache for specific connection.
                       If None, clears the entire cache.
    """
    _postgres_version_registry.clear(connection_id)


async def get_postgres_version(sql_driver: SqlDriver) -> int:
    """Get the major PostgreSQL version as an integer.

    Args:
        sql_driver: An instance of SqlDriver to execute queries

    Returns:
        The major PostgreSQL version as an integer (e.g., 16 for PostgreSQL 16.2)
        Returns 0 if the version cannot be determined
    """
    # Get connection identifier for cache lookup
    connection_id = _get_connection_id(sql_driver)

    # Check if we have a cached version for this connection
    cached_version = _postgres_version_registry.get(connection_id)
    if cached_version is not None:
        return cached_version

    try:
        rows = await sql_driver.execute_query("SHOW server_version")
        if not rows:
            logger.warning("Could not determine PostgreSQL version")
            return 0

        version_string = rows[0].cells["server_version"]
        # Handle None, bytes, or string types
        if version_string is None:
            logger.warning("PostgreSQL version string is None")
            return 0

        # Convert bytes to string if needed
        if isinstance(version_string, bytes):
            version_string = version_string.decode("utf-8")

        # Ensure it's a string
        if not isinstance(version_string, str):
            version_string = str(version_string)

        # Extract the major version (before the first dot)
        major_version = version_string.split(".")[0]
        version = int(major_version)

        # Cache the version for this connection
        _postgres_version_registry.set(connection_id, version)
    except Exception as e:
        logger.warning("Error determining PostgreSQL version: %s", e)
        return 0
    else:
        return version


async def check_postgres_version_requirement(
    sql_driver: SqlDriver, min_version: int, feature_name: str
) -> tuple[bool, str]:
    """Check if the PostgreSQL version meets the minimum requirement.

    Args:
        sql_driver: An instance of SqlDriver to execute queries
        min_version: The minimum required PostgreSQL version
        feature_name: Name of the feature that requires this version

    Returns:
        A tuple of (meets_requirement, message)
    """
    pg_version = await get_postgres_version(sql_driver)

    if pg_version >= min_version:
        return True, f"PostgreSQL version {pg_version} meets the requirement for {feature_name}"

    return False, (
        f"This feature ({feature_name}) requires PostgreSQL {min_version} or later. "
        f"Your current version is PostgreSQL {pg_version or 'unknown'}."
    )


async def check_extension(
    sql_driver: SqlDriver,
    extension_name: str,
    *,
    include_messages: bool = True,
    message_type: Literal["plain", "markdown"] = "plain",
) -> ExtensionStatus:
    """Check if a PostgreSQL extension is installed or available.

    Args:
        sql_driver: An instance of SqlDriver to execute queries
        extension_name: Name of the extension to check
        include_messages: Whether to include user-friendly messages in the result
        message_type: Format for messages - 'plain' or 'markdown'

    Returns:
        ExtensionStatus with fields:
            - is_installed: True if the extension is installed
            - is_available: True if the extension is available but not installed
            - name: The extension name
            - message: A user-friendly message about the extension status
            - default_version: The default version of the extension if available
    """
    # Check if the extension is installed
    installed_result = await SafeSqlDriver.execute_param_query(
        sql_driver,
        "SELECT extversion FROM pg_extension WHERE extname = {}",
        [extension_name],
    )

    # Initialize result
    result = ExtensionStatus(
        is_installed=False,
        is_available=False,
        name=extension_name,
        message="",
        default_version=None,
    )

    if installed_result and len(installed_result) > 0:
        # Extension is installed
        version = installed_result[0].cells.get("extversion", "unknown")
        result.is_installed = True
        result.is_available = True

        if include_messages:
            if message_type == "markdown":
                result.message = f"The **{extension_name}** extension (version {version}) is already installed."
            else:
                result.message = f"The {extension_name} extension (version {version}) is already installed."
    else:
        # Check if the extension is available but not installed
        available_result = await SafeSqlDriver.execute_param_query(
            sql_driver,
            "SELECT default_version FROM pg_available_extensions WHERE name = {}",
            [extension_name],
        )

        if available_result and len(available_result) > 0:
            # Extension is available but not installed
            result.is_available = True
            result.default_version = available_result[0].cells.get("default_version")

            if include_messages:
                if message_type == "markdown":
                    result.message = (
                        f"The **{extension_name}** extension is available but not installed.\n\n"
                        f"You can install it by running: `CREATE EXTENSION {extension_name};`."
                    )
                else:
                    result.message = (
                        f"The {extension_name} extension is available but not installed.\n"
                        f"You can install it by running: CREATE EXTENSION {extension_name};"
                    )
        # Extension is not available
        elif include_messages:
            if message_type == "markdown":
                result.message = (
                    f"The **{extension_name}** extension is not available on this PostgreSQL server.\n\n"
                    f"To install it, you need to:\n"
                    f"1. Install the extension package on the server\n"
                    f"2. Run: `CREATE EXTENSION {extension_name};`"
                )
            else:
                result.message = (
                    f"The {extension_name} extension is not available on this PostgreSQL server.\n"
                    f"To install it, you need to:\n"
                    f"1. Install the extension package on the server\n"
                    f"2. Run: CREATE EXTENSION {extension_name};"
                )

    return result


async def check_hypopg_installation_status(
    sql_driver: SqlDriver, message_type: Literal["plain", "markdown"] = "markdown"
) -> tuple[bool, str]:
    """Get a detailed status message for the HypoPG extension.

    Args:
        sql_driver: An instance of SqlDriver to execute queries
        message_type: Format for messages - 'plain' or 'markdown'

    Returns:
        A formatted message about the HypoPG extension status with installation instructions
    """
    status = await check_extension(sql_driver, "hypopg", include_messages=False)

    if status.is_installed:
        if message_type == "markdown":
            return True, "The **hypopg** extension is already installed."
        return True, "The hypopg extension is already installed."

    if status.is_available:
        if message_type == "markdown":
            return False, (
                "The **hypopg** extension is required to test hypothetical indexes, but it is not currently installed."
                "\n\nYou can ask me to install 'hypopg' using the 'execute_query' tool.\n\n"
                "**Is it safe?** Installing 'hypopg' is generally safe and a standard practice for index testing. "
                "It adds a virtual layer that simulates indexes without actually creating them in the database. "
                "It requires database privileges (often superuser) to install.\n\n"
                "**What does it do?** It allows you to create virtual indexes and test how they would affect "
                "query performance without the overhead of actually creating the indexes.\n\n"
                "**How to undo?** If you later decide to remove it, you can ask me to run 'DROP EXTENSION hypopg;'."
            )
        return False, (
            "The hypopg extension is required to test hypothetical indexes, but it is not currently installed.\n"
            "You can ask me to install it using the 'execute_query' tool.\n"
            "It is generally safe to install and allows testing indexes without creating them."
        )

    pg_version = await get_postgres_version(sql_driver)
    major_version_str = f"{pg_version}" if pg_version > 0 else "XX"
    # Extension is not available
    if message_type == "markdown":
        return False, (
            "The **hypopg** extension is not available on this PostgreSQL server.\n\n"
            "To install HypoPG:\n"
            f"1. For Debian/Ubuntu: `sudo apt-get install postgresql-{major_version_str}-hypopg`\n"
            f"2. For RHEL/CentOS: `sudo yum install postgresql{major_version_str}-hypopg`\n"
            "3. For MacOS with Homebrew: `brew install hypopg`\n"
            "4. For other systems, build from source: `git clone https://github.com/HypoPG/hypopg`\n\n"
            "After installing the extension packages, connect to your database and run: `CREATE EXTENSION hypopg;`"
        )
    return False, (
        "The hypopg extension is not available on this PostgreSQL server.\n"
        "To install HypoPG:\n"
        f"1. For Debian/Ubuntu: sudo apt-get install postgresql-{major_version_str}-hypopg\n"
        f"2. For RHEL/CentOS: sudo yum install postgresql{major_version_str}-hypopg\n"
        "3. For MacOS with Homebrew: brew install hypopg\n"
        "4. For other systems, build from source: git clone https://github.com/HypoPG/hypopg\n"
        "After installing the extension packages, connect to your database and run: CREATE EXTENSION hypopg;"
    )
