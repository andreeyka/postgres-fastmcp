"""SQL driver adapter for PostgreSQL connections."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, LiteralString, NoReturn
from urllib.parse import urlparse, urlunparse

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


if TYPE_CHECKING:
    from psycopg import AsyncConnection
else:
    AsyncConnection = Any


logger = logging.getLogger(__name__)


class ConnectionFailedError(ValueError):
    """Exception for database connection errors."""

    def __init__(self, error_details: str | None) -> None:
        """Initialize exception.

        Args:
            error_details: Connection error details (with obfuscated password).
        """
        message = f"Connection attempt failed: {error_details}"
        super().__init__(message)
        self.error_details = error_details


def obfuscate_password(text: str | None) -> str | None:
    """Obfuscate password in any text containing connection information.

    Works on connection URLs, error messages, and other strings.

    Args:
        text: The text containing connection information.

    Returns:
        The text with passwords obfuscated, or None if input was None.
    """
    if text is None:
        return None

    if not text:
        return text

    # Try first as a proper URL
    try:
        parsed = urlparse(text)
        if parsed.scheme and parsed.netloc and parsed.password:
            # Replace password with asterisks in proper URL
            netloc = parsed.netloc.replace(parsed.password, "****")
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception as e:
        # If URL parsing fails, fall back to regex-based obfuscation
        logger.debug("Failed to parse text as URL, using regex-based obfuscation: %s", e)

    # Handle strings that contain connection strings but aren't proper URLs
    # Match postgres://user:password@host:port/dbname pattern
    url_pattern = re.compile(r"(postgres(?:ql)?:\/\/[^:]+:)([^@]+)(@[^\/\s]+)")
    text = re.sub(url_pattern, r"\1****\3", text)

    # Match connection string parameters (password=xxx)
    # This simpler pattern captures password without quotes
    param_pattern = re.compile(r'(password=)([^\s&;"\']+)', re.IGNORECASE)
    text = re.sub(param_pattern, r"\1****", text)

    # Match password in DSN format with single quotes
    dsn_single_quote = re.compile(r"(password\s*=\s*')([^']+)(')", re.IGNORECASE)
    text = re.sub(dsn_single_quote, r"\1****\3", text)

    # Match password in DSN format with double quotes
    dsn_double_quote = re.compile(r'(password\s*=\s*")([^"]+)(")', re.IGNORECASE)
    return re.sub(dsn_double_quote, r"\1****\3", text)


class DbConnPool:
    """Database connection manager using psycopg's connection pool."""

    def __init__(
        self,
        connection_url: str | None = None,
        min_size: int = 1,
        max_size: int = 5,
    ) -> None:
        """Initialize database connection pool.

        Args:
            connection_url: Database connection URL.
            min_size: Minimum number of connections in the pool.
            max_size: Maximum number of connections in the pool.
        """
        self.connection_url = connection_url
        self.min_size = min_size
        self.max_size = max_size
        self.pool: AsyncConnectionPool | None = None
        self._is_valid = False
        self._last_error: str | None = None

    async def pool_connect(self, connection_url: str | None = None) -> AsyncConnectionPool:
        """Initialize connection pool with retry logic."""
        # If we already have a valid pool, return it
        if self.pool and self._is_valid:
            return self.pool

        url = connection_url or self.connection_url
        self.connection_url = url
        if not url:
            self._is_valid = False
            error_msg = "Database connection URL not provided"
            self._last_error = error_msg
            raise ValueError(error_msg)

        # Close any existing pool before creating a new one
        await self.close()

        try:
            # Configure connection pool with appropriate settings
            self.pool = AsyncConnectionPool(
                conninfo=url,
                min_size=self.min_size,
                max_size=self.max_size,
                open=False,  # Don't connect immediately, let's do it explicitly
            )

            # Open the pool explicitly
            await self.pool.open()

            # Test the connection pool by executing a simple query
            async with self.pool.connection() as conn, conn.cursor() as cursor:
                await cursor.execute("SELECT 1")

            self._is_valid = True
            self._last_error = None
        except Exception as e:
            self._is_valid = False
            error_msg = str(e)
            self._last_error = error_msg

            # Clean up failed pool
            await self.close()

            obfuscated_error = obfuscate_password(error_msg)
            raise ConnectionFailedError(obfuscated_error) from e
        else:
            return self.pool

    async def close(self) -> None:
        """Close the connection pool."""
        if self.pool:
            try:
                # Close the pool
                await self.pool.close()
            except Exception as e:
                logger.warning("Error closing connection pool: %s", e)
            finally:
                self.pool = None
                self._is_valid = False

    @property
    def is_valid(self) -> bool:
        """Check if the connection pool is valid."""
        return self._is_valid

    @property
    def last_error(self) -> str | None:
        """Get the last error message."""
        return self._last_error

    def mark_invalid(self, error: str | None = None) -> None:
        """Mark connection pool as invalid.

        Args:
            error: Error message if any.
        """
        self._is_valid = False
        self._last_error = error


class SqlDriver:
    """Adapter class that wraps a PostgreSQL connection with the interface expected by DTA."""

    @dataclass
    class RowResult:
        """Simple class to match the Griptape RowResult interface."""

        cells: dict[str, Any]

    def __init__(
        self,
        conn: DbConnPool | AsyncConnection | None = None,
        engine_url: str | None = None,
    ) -> None:
        """Initialize with a PostgreSQL connection or pool.

        Args:
            conn: PostgreSQL connection object or pool
            engine_url: Connection URL string as an alternative to providing a connection
        """
        self.conn: DbConnPool | AsyncConnection | None = None
        if conn:
            self.conn = conn
            # Check if this is a connection pool
            self.is_pool = isinstance(conn, DbConnPool)
        elif engine_url:
            # Don't connect here since we need async connection
            self.engine_url = engine_url
            self.is_pool = False
        else:
            error_msg = "Either conn or engine_url must be provided"
            raise ValueError(error_msg)

    def connect(self) -> DbConnPool | AsyncConnection:
        """Connect to the database.

        Returns:
            The connection pool or connection object.

        Raises:
            ValueError: If connection cannot be established.
        """
        if self.conn is not None:
            return self.conn
        if self.engine_url:
            self.conn = DbConnPool(self.engine_url)
            self.is_pool = True
            return self.conn
        error_msg = "Connection not established. Either conn or engine_url must be provided"
        raise ValueError(error_msg)

    async def execute_query(  # noqa: C901
        self,
        query: LiteralString,
        params: list[Any] | None = None,
        *,
        force_readonly: bool = False,
    ) -> list[RowResult] | None:
        """Execute a query and return results.

        Args:
            query: SQL query to execute
            params: Query parameters
            force_readonly: Whether to enforce read-only mode

        Returns:
            List of RowResult objects or None on error
        """

        def _raise_connection_error() -> NoReturn:
            """Raise exception about unestablished connection.

            Raises:
                ValueError: If connection is not established.
            """
            error_msg = "Connection not established"
            raise ValueError(error_msg)

        try:
            if self.conn is None:
                self.connect()
                if self.conn is None:
                    _raise_connection_error()

            # Handle connection pool vs direct connection
            if self.is_pool and isinstance(self.conn, DbConnPool):
                # For pools, get a connection from the pool
                pool = await self.conn.pool_connect()
                async with pool.connection() as connection:
                    # Set autocommit=True to avoid "transaction in progress" warnings
                    # We manage transactions explicitly in _execute_with_connection
                    await connection.set_autocommit(True)
                    return await self._execute_with_connection(connection, query, params, force_readonly=force_readonly)
            elif self.conn is not None and isinstance(self.conn, AsyncConnection):
                # Direct connection approach
                # Ensure autocommit is set for direct connections too
                if hasattr(self.conn, "set_autocommit"):
                    await self.conn.set_autocommit(True)
                return await self._execute_with_connection(self.conn, query, params, force_readonly=force_readonly)

            # If we reach here, connection type is not supported
            _raise_connection_error()
        except Exception as e:
            # Mark pool as invalid if there was a connection issue
            if self.conn and self.is_pool:
                conn_pool = self.conn
                if isinstance(conn_pool, DbConnPool):
                    conn_pool.mark_invalid(str(e))
            elif self.conn and not self.is_pool:
                self.conn = None

            raise

    async def _execute_with_connection(
        self,
        connection: AsyncConnection[Any],
        query: LiteralString,
        params: list[Any] | None,
        *,
        force_readonly: bool,
    ) -> list[RowResult] | None:
        """Execute query with the given connection.

        Manages transactions explicitly:
        - For read-only queries: uses BEGIN TRANSACTION READ ONLY / ROLLBACK
        - For write queries: uses BEGIN / COMMIT
        - With autocommit=True, we can safely start transactions without conflicts
        """
        try:
            async with connection.cursor(row_factory=dict_row) as cursor:
                # Start transaction explicitly
                if force_readonly:
                    # For read-only mode, start a read-only transaction
                    await cursor.execute("BEGIN TRANSACTION READ ONLY")
                else:
                    # For write mode, start a normal transaction
                    await cursor.execute("BEGIN")

                try:
                    # Execute the query
                    if params:
                        await cursor.execute(query, params)
                    else:
                        await cursor.execute(query)

                    # For multiple statements, move to the last statement's results
                    while cursor.nextset():
                        pass

                    # Check if there are results
                    if cursor.description is None:  # No results (like DDL statements)
                        # Commit or rollback based on mode
                        if force_readonly:
                            await cursor.execute("ROLLBACK")
                        else:
                            await cursor.execute("COMMIT")
                        return None

                    # Get results from the last statement only
                    rows = await cursor.fetchall()

                    # End the transaction appropriately
                    if force_readonly:
                        await cursor.execute("ROLLBACK")
                    else:
                        await cursor.execute("COMMIT")

                    return [SqlDriver.RowResult(cells=dict(row)) for row in rows]

                except Exception:
                    # Rollback on any error during query execution
                    try:
                        await cursor.execute("ROLLBACK")
                    except Exception as rollback_error:
                        logger.error("Error rolling back transaction: %s", rollback_error)
                    raise

        except Exception as e:
            logger.error("Error executing query (%s): %s", query, e)
            raise
