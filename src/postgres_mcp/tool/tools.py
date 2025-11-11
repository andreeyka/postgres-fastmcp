"""Module for creating and registering MCP tools."""

from types import TracebackType
from typing import Any, Literal, Self, cast

from fastmcp import Context, FastMCP
from pydantic import Field

from postgres_mcp.common import ErrorResult
from postgres_mcp.config import AVAILABLE_TOOLS, DatabaseConfig, settings
from postgres_mcp.database_health import DatabaseHealthTool
from postgres_mcp.enums import AccessMode, ToolName, UserRole
from postgres_mcp.explain import ExplainPlanArtifact, ExplainPlanTool
from postgres_mcp.index.dta_calc import DatabaseTuningAdvisor
from postgres_mcp.index.index_opt_base import MAX_NUM_INDEX_TUNING_QUERIES, IndexTuningBase
from postgres_mcp.index.llm_opt import LLMOptimizerTool
from postgres_mcp.index.presentation import TextPresentation
from postgres_mcp.logger import get_logger
from postgres_mcp.sql import DbConnPool, SafeSqlConfig, SafeSqlDriver, SqlDriver, check_hypopg_installation_status
from postgres_mcp.top_queries import TopQueriesCalc

from .constants import (
    ERROR_CANNOT_USE_ANALYZE_WITH_HYPOTHETICAL,
    ERROR_DB_NOT_INITIALIZED,
    ERROR_DB_URL_NOT_SET,
    ERROR_EMPTY_QUERIES,
    ERROR_INVALID_SORT_CRITERIA,
    ERROR_NO_RESULTS,
    ERROR_PREFIX,
    ERROR_PROCESSING_EXPLAIN_PLAN,
    ERROR_UNSUPPORTED_OBJECT_TYPE,
    HEALTH_TYPE_VALUES,
    LOG_ERROR_ANALYZING_QUERIES,
    LOG_ERROR_ANALYZING_WORKLOAD,
    LOG_ERROR_EXECUTING_QUERY,
    LOG_ERROR_EXPLAINING_QUERY,
    LOG_ERROR_GETTING_OBJECT_DETAILS,
    LOG_ERROR_GETTING_SLOW_QUERIES,
    LOG_ERROR_LISTING_OBJECTS,
    LOG_ERROR_LISTING_SCHEMAS,
    LOG_UNRESTRICTED_SQL_DRIVER,
    QUERIES_LIMIT_MESSAGE,
)
from .descriptions import (
    DESC_ANALYZE_DB_HEALTH,
    DESC_ANALYZE_QUERY_INDEXES,
    DESC_ANALYZE_WORKLOAD_INDEXES,
    DESC_EXECUTE_SQL_RESTRICTED,
    DESC_EXECUTE_SQL_UNRESTRICTED,
    DESC_EXPLAIN_QUERY,
    DESC_GET_OBJECT_DETAILS_FULL,
    DESC_GET_OBJECT_DETAILS_USER,
    DESC_GET_TOP_QUERIES,
    DESC_HYPOTHETICAL_INDEXES,
    DESC_LIST_OBJECTS_FULL,
    DESC_LIST_OBJECTS_USER,
    DESC_LIST_SCHEMAS,
)
from .queries import (
    QUERY_GET_COLUMNS,
    QUERY_GET_CONSTRAINTS,
    QUERY_GET_EXTENSION_DETAILS,
    QUERY_GET_INDEXES,
    QUERY_GET_SEQUENCE_DETAILS,
    QUERY_LIST_EXTENSIONS,
    QUERY_LIST_SCHEMAS,
    QUERY_LIST_SEQUENCES,
    QUERY_LIST_TABLES_VIEWS,
)
from .utils import decode_bytes_to_utf8


logger = get_logger(__name__)

# Type for MCP responses (FastMCP automatically converts these to MCP format)
ResponseType = str | dict[str, Any] | list[Any]


class ToolManager:
    """Class for creating and managing MCP tools.

    Encapsulates all tools for working with PostgreSQL through the MCP protocol.
    """

    # Tools configuration will be set from DatabaseConfig.tools in __init__

    def _get_tool_description(self, tool_name: ToolName) -> str:
        """Get tool description based on role and access_mode.

        Args:
            tool_name: Name of the tool.

        Returns:
            Tool description string.
        """
        # Role-specific descriptions
        if tool_name == ToolName.LIST_OBJECTS:
            return DESC_LIST_OBJECTS_USER if self.role == UserRole.USER else DESC_LIST_OBJECTS_FULL

        if tool_name == ToolName.GET_OBJECT_DETAILS:
            return DESC_GET_OBJECT_DETAILS_USER if self.role == UserRole.USER else DESC_GET_OBJECT_DETAILS_FULL

        if tool_name == ToolName.EXECUTE_SQL:
            if self.role == UserRole.FULL and self.access_mode == AccessMode.UNRESTRICTED:
                return DESC_EXECUTE_SQL_UNRESTRICTED
            return DESC_EXECUTE_SQL_RESTRICTED

        # Static descriptions (same for all roles)
        descriptions_map: dict[ToolName, str] = {
            ToolName.LIST_SCHEMAS: DESC_LIST_SCHEMAS,
            ToolName.EXPLAIN_QUERY: DESC_EXPLAIN_QUERY,
            ToolName.ANALYZE_WORKLOAD_INDEXES: DESC_ANALYZE_WORKLOAD_INDEXES,
            ToolName.ANALYZE_QUERY_INDEXES: DESC_ANALYZE_QUERY_INDEXES,
            ToolName.ANALYZE_DB_HEALTH: DESC_ANALYZE_DB_HEALTH,
            ToolName.GET_TOP_QUERIES: DESC_GET_TOP_QUERIES,
        }

        return descriptions_map.get(tool_name, "")

    def __init__(
        self,
        config: DatabaseConfig,
    ) -> None:
        """Initialize the ToolManager class.

        Args:
            config: Database configuration.
        """
        self.config = config
        self.access_mode = config.access_mode
        self.role = config.role
        # Create database connection pool from config
        self.db_connection = DbConnPool(
            connection_url=config.database_uri.get_secret_value(),
            min_size=config.pool_min_size,
            max_size=config.pool_max_size,
        )
        # Build tools mapping with dynamic descriptions based on role and access_mode
        # All descriptions are set through _get_tool_description method for consistency
        self._tools: dict[str, dict[str, Any]] = {}

        # Get enabled tools from config (config handles role-based defaults and explicit settings)
        tools_to_enable = self.config.get_enabled_tools()

        # Build tools configuration with descriptions
        # Use tool_name.value as key for compatibility with FastMCP (expects string keys)
        for tool_name in AVAILABLE_TOOLS:
            is_enabled = tool_name in tools_to_enable

            self._tools[tool_name.value] = {
                "description": self._get_tool_description(tool_name),
                "enabled": is_enabled,
            }
        # Lazy-loaded SQL driver (created on first access)
        self._sql_driver: SqlDriver | SafeSqlDriver | None = None

    async def __aenter__(self) -> Self:
        """Async context manager entry.

        Returns:
            Self instance for use in async with statement.
        """
        logger.debug("Entering ToolManager context manager")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit.

        Closes database connection pool on exit.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        logger.debug("Exiting ToolManager context manager, closing database connections")
        if self.db_connection:
            try:
                await self.db_connection.close()
                logger.debug("Database connection pool closed successfully")
            except Exception as e:
                logger.error("Error closing database connection pool: %s", e)

    @property
    def sql_driver(self) -> SqlDriver | SafeSqlDriver:
        """Get the appropriate SQL driver based on the current access mode.

        Uses lazy loading - creates driver on first access and reuses the same instance.
        Connection to database pool will be established automatically on first query execution.

        Returns:
            SqlDriver or SafeSqlDriver depending on the access mode.

        Raises:
            ValueError: If database connection is not available.
        """
        # Return cached driver if it exists
        if self._sql_driver is not None:
            return self._sql_driver

        # Driver doesn't exist - create new one
        if self.db_connection is None:
            logger.error(ERROR_DB_NOT_INITIALIZED)
            raise ValueError(ERROR_DB_NOT_INITIALIZED)

        if not self.db_connection.connection_url:
            logger.error(ERROR_DB_URL_NOT_SET)
            raise ValueError(ERROR_DB_URL_NOT_SET)

        base_driver = SqlDriver(conn=self.db_connection)

        # FULL role with UNRESTRICTED access_mode uses unrestricted SqlDriver
        if self.role == UserRole.FULL and self.access_mode == AccessMode.UNRESTRICTED:
            logger.debug(LOG_UNRESTRICTED_SQL_DRIVER)
            self._sql_driver = base_driver
        else:
            # All other modes use SafeSqlDriver with different restrictions
            safe_config = SafeSqlConfig(
                timeout=self.config.safe_sql_timeout,
                allowed_schema=self._allowed_schema(),
                read_only=self._is_read_only(),
                query_tag=settings.name,
                table_prefix=self.config.table_prefix if self.role == UserRole.USER else None,
            )

            logger.debug(
                "Using SafeSqlDriver (role=%s, access_mode=%s, allowed_schema=%s, "
                "read_only=%s, timeout=%ss, table_prefix=%s)",
                self.role.value,
                self.access_mode.value,
                safe_config.allowed_schema,
                safe_config.read_only,
                safe_config.timeout,
                safe_config.table_prefix,
            )
            self._sql_driver = SafeSqlDriver(
                sql_driver=base_driver,
                config=safe_config,
            )

        return self._sql_driver

    def _is_user_mode(self) -> bool:
        """Check if the role is user mode (limited to public schema).

        Returns:
            True if role is USER, False otherwise.
        """
        return self.role == UserRole.USER

    def _is_read_only(self) -> bool:
        """Check if the access mode is read-only.

        Returns:
            True if access_mode is RESTRICTED, False otherwise.
        """
        return self.access_mode == AccessMode.RESTRICTED

    def _allowed_schema(self) -> str | None:
        """Get the allowed schema for this role.

        Returns:
            'public' for USER role, None for FULL role (all schemas allowed).
        """
        if self.role == UserRole.USER:
            return "public"
        return None

    def _has_full_access(self) -> bool:
        """Check if the role has full access (all schemas, all tools).

        Returns:
            True if role is FULL, False otherwise.
        """
        return self.role == UserRole.FULL

    def _format_error_response(self, error: str) -> ResponseType:
        """Format an error response.

        Args:
            error: Error message.

        Returns:
            Formatted error response with prefix.
        """
        return ERROR_PREFIX + error

    async def list_schemas(self) -> ResponseType:
        """List all schemas in the database."""
        try:
            # USER role: return only public schema
            if self._is_user_mode():
                return [
                    {
                        "schema_name": "public",
                        "schema_owner": "postgres",  # Default owner, actual value may vary
                        "schema_type": "User Schema",
                    }
                ]

            # FULL role: return all schemas
            sql_driver = self.sql_driver
            rows = await sql_driver.execute_query(QUERY_LIST_SCHEMAS)
            schemas = [decode_bytes_to_utf8(row.cells) for row in rows] if rows else []
        except Exception as e:
            logger.error(LOG_ERROR_LISTING_SCHEMAS.format(str(e)))
            return self._format_error_response(str(e))
        else:
            return schemas

    async def list_objects(
        self,
        schema_name: str = Field(
            description="Schema name as string value for filtering objects by database schema location"
        ),
        object_type: str = Field(
            default="table",
            description=(
                "Object type as string value: 'table' for tables, 'view' for views, "
                "'sequence' for sequences, or 'extension' for PostgreSQL extensions"
            ),
        ),
    ) -> ResponseType:
        """List objects of a given type in a schema."""
        try:
            # USER role: force schema to public
            if self._is_user_mode():
                if schema_name and schema_name.lower() != "public":
                    return self._format_error_response(
                        f"Access to schema '{schema_name}' is not allowed. Only 'public' schema is permitted."
                    )
                schema_name = "public"

            sql_driver = self.sql_driver

            if object_type in ("table", "view"):
                table_type = "BASE TABLE" if object_type == "table" else "VIEW"
                rows = await SafeSqlDriver.execute_param_query(
                    sql_driver,
                    QUERY_LIST_TABLES_VIEWS,
                    [schema_name, table_type],
                )
                objects = (
                    [
                        {
                            "schema": decode_bytes_to_utf8(row.cells["table_schema"]),
                            "name": decode_bytes_to_utf8(row.cells["table_name"]),
                            "type": decode_bytes_to_utf8(row.cells["table_type"]),
                        }
                        for row in rows
                    ]
                    if rows
                    else []
                )
                # Filter by table_prefix in user role
                if self._is_user_mode() and self.config.table_prefix:
                    prefix_lower = self.config.table_prefix.lower()
                    objects = [obj for obj in objects if obj["name"].lower().startswith(prefix_lower)]

            elif object_type == "sequence":
                rows = await SafeSqlDriver.execute_param_query(
                    sql_driver,
                    QUERY_LIST_SEQUENCES,
                    [schema_name],
                )
                objects = (
                    [
                        {
                            "schema": decode_bytes_to_utf8(row.cells["sequence_schema"]),
                            "name": decode_bytes_to_utf8(row.cells["sequence_name"]),
                            "data_type": decode_bytes_to_utf8(row.cells["data_type"]),
                        }
                        for row in rows
                    ]
                    if rows
                    else []
                )
                # Filter by table_prefix in user role
                if self._is_user_mode() and self.config.table_prefix:
                    prefix_lower = self.config.table_prefix.lower()
                    objects = [obj for obj in objects if obj["name"].lower().startswith(prefix_lower)]

            elif object_type == "extension":
                # Extensions are not schema-specific
                rows = await sql_driver.execute_query(QUERY_LIST_EXTENSIONS)
                objects = (
                    [
                        {
                            "name": decode_bytes_to_utf8(row.cells["extname"]),
                            "version": decode_bytes_to_utf8(row.cells["extversion"]),
                            "relocatable": decode_bytes_to_utf8(row.cells["extrelocatable"]),
                        }
                        for row in rows
                    ]
                    if rows
                    else []
                )

            else:
                return self._format_error_response(ERROR_UNSUPPORTED_OBJECT_TYPE.format(object_type))

        except Exception as e:
            logger.error(LOG_ERROR_LISTING_OBJECTS.format(str(e)))
            return self._format_error_response(str(e))
        else:
            return objects

    async def get_object_details(  # noqa: C901
        self,
        schema_name: str = Field(
            description="Schema name as string value for identifying the database schema containing the object"
        ),
        object_name: str = Field(
            description=(
                "Object name as string value for identifying the specific database object "
                "(table, view, sequence, or extension)"
            )
        ),
        object_type: str = Field(
            default="table",
            description=(
                "Object type as string value: 'table' for tables, 'view' for views, "
                "'sequence' for sequences, or 'extension' for PostgreSQL extensions"
            ),
        ),
    ) -> ResponseType:
        """Get detailed information about a database object."""
        try:
            # USER role: validate and force schema to public
            if self._is_user_mode():
                if schema_name and schema_name.lower() != "public":
                    return self._format_error_response(
                        f"Access to schema '{schema_name}' is not allowed. Only 'public' schema is permitted."
                    )
                schema_name = "public"

            sql_driver = self.sql_driver

            if object_type in ("table", "view"):
                # Get columns
                col_rows = await SafeSqlDriver.execute_param_query(
                    sql_driver,
                    QUERY_GET_COLUMNS,
                    [schema_name, object_name],
                )
                columns = (
                    [
                        {
                            "column": decode_bytes_to_utf8(r.cells["column_name"]),
                            "data_type": decode_bytes_to_utf8(r.cells["data_type"]),
                            "is_nullable": decode_bytes_to_utf8(r.cells["is_nullable"]),
                            "default": decode_bytes_to_utf8(r.cells["column_default"]),
                        }
                        for r in col_rows
                    ]
                    if col_rows
                    else []
                )

                # Get constraints
                con_rows = await SafeSqlDriver.execute_param_query(
                    sql_driver,
                    QUERY_GET_CONSTRAINTS,
                    [schema_name, object_name],
                )

                constraints: dict[str, dict[str, Any]] = {}
                if con_rows:
                    for row in con_rows:
                        cname = decode_bytes_to_utf8(row.cells["constraint_name"])
                        ctype = decode_bytes_to_utf8(row.cells["constraint_type"])
                        col = decode_bytes_to_utf8(row.cells["column_name"])

                        if isinstance(cname, str) and isinstance(ctype, (str, int, float, bool, type(None))):
                            if cname not in constraints:
                                constraints[cname] = {"type": ctype, "columns": []}
                            if col and isinstance(col, str):
                                constraints[cname]["columns"].append(col)

                constraints_list = [{"name": name, **data} for name, data in constraints.items()]

                # Get indexes
                idx_rows = await SafeSqlDriver.execute_param_query(
                    sql_driver,
                    QUERY_GET_INDEXES,
                    [schema_name, object_name],
                )

                indexes = (
                    [
                        {
                            "name": decode_bytes_to_utf8(r.cells["indexname"]),
                            "definition": decode_bytes_to_utf8(r.cells["indexdef"]),
                        }
                        for r in idx_rows
                    ]
                    if idx_rows
                    else []
                )

                result = {
                    "basic": {"schema": schema_name, "name": object_name, "type": object_type},
                    "columns": columns,
                    "constraints": constraints_list,
                    "indexes": indexes,
                }

            elif object_type == "sequence":
                rows = await SafeSqlDriver.execute_param_query(
                    sql_driver,
                    QUERY_GET_SEQUENCE_DETAILS,
                    [schema_name, object_name],
                )

                if rows and rows[0]:
                    row = rows[0]
                    result = {
                        "schema": cast("str", decode_bytes_to_utf8(row.cells["sequence_schema"])),
                        "name": cast("str", decode_bytes_to_utf8(row.cells["sequence_name"])),
                        "data_type": cast("str", decode_bytes_to_utf8(row.cells["data_type"])),
                        "start_value": cast("str | int", decode_bytes_to_utf8(row.cells["start_value"])),  # type: ignore[dict-item]
                        "increment": cast("str | int", decode_bytes_to_utf8(row.cells["increment"])),  # type: ignore[dict-item]
                    }
                else:
                    result = {}

            elif object_type == "extension":
                rows = await SafeSqlDriver.execute_param_query(
                    sql_driver,
                    QUERY_GET_EXTENSION_DETAILS,
                    [object_name],
                )

                if rows and rows[0]:
                    row = rows[0]
                    result = {
                        "name": cast("str", decode_bytes_to_utf8(row.cells["extname"])),
                        "version": cast("str", decode_bytes_to_utf8(row.cells["extversion"])),
                        "relocatable": cast("str | bool", decode_bytes_to_utf8(row.cells["extrelocatable"])),  # type: ignore[dict-item]
                    }
                else:
                    result = {}

            else:
                return self._format_error_response(ERROR_UNSUPPORTED_OBJECT_TYPE.format(object_type))

        except Exception as e:
            logger.error(LOG_ERROR_GETTING_OBJECT_DETAILS.format(str(e)))
            return self._format_error_response(str(e))
        else:
            # Decode the entire result for correct JSON serialization
            decoded_result = decode_bytes_to_utf8(result)
            return cast("ResponseType", decoded_result)

    async def explain_query(
        self,
        sql: str = Field(description="SQL query as string value to explain and analyze execution plan"),
        *,
        analyze: bool = Field(
            default=False,
            description=(
                "Analyze flag as boolean value: when True, actually runs the query to show real execution "
                "statistics instead of estimates. Takes longer but provides more accurate information. "
                "Cannot be used together with hypothetical_indexes"
            ),
        ),
        hypothetical_indexes: list[dict[str, Any]] = Field(  # noqa: B008
            default_factory=list,
            description=DESC_HYPOTHETICAL_INDEXES,
        ),
    ) -> ResponseType:
        """Explain the execution plan for a SQL query.

        Args:
            sql: SQL query to explain.
            analyze: When True, actually runs the query for real statistics.
            hypothetical_indexes: Optional list of indexes to simulate.
        """
        try:
            sql_driver = self.sql_driver
            explain_tool = ExplainPlanTool(sql_driver=sql_driver)
            result: ExplainPlanArtifact | ErrorResult | None = None

            # If hypothetical indexes are specified, check for HypoPG extension
            if hypothetical_indexes and len(hypothetical_indexes) > 0:
                if analyze:
                    return self._format_error_response(ERROR_CANNOT_USE_ANALYZE_WITH_HYPOTHETICAL)
                # Use the common utility function to check if hypopg is installed
                (
                    is_hypopg_installed,
                    hypopg_message,
                ) = await check_hypopg_installation_status(sql_driver)

                # If hypopg is not installed, return the message
                if not is_hypopg_installed:
                    return hypopg_message

                # HypoPG is installed, proceed with explaining with hypothetical indexes
                result = await explain_tool.explain_with_hypothetical_indexes(sql, hypothetical_indexes)
            elif analyze:
                # Use EXPLAIN ANALYZE
                result = await explain_tool.explain_analyze(sql)
            else:
                # Use basic EXPLAIN
                result = await explain_tool.explain(sql)

            if result and isinstance(result, ExplainPlanArtifact):
                return result.to_text()
            error_message = ERROR_PROCESSING_EXPLAIN_PLAN
            if isinstance(result, ErrorResult):
                error_message = result.to_text()
            return self._format_error_response(error_message)
        except Exception as e:
            logger.error(LOG_ERROR_EXPLAINING_QUERY.format(str(e)))
            return self._format_error_response(str(e))

    async def execute_sql(
        self,
        sql: str = Field(
            default="all",
            description=(
                "SQL query as string value to execute against the database. For read-only modes, "
                "only SELECT queries are allowed. For 'full' role with 'unrestricted' access_mode, "
                "any SQL statement (DDL, DML, DCL) is permitted"
            ),
        ),
    ) -> ResponseType:
        """Execute a SQL query against the database."""
        try:
            sql_driver = self.sql_driver
            rows = await sql_driver.execute_query(sql)
            if rows is None:
                return ERROR_NO_RESULTS
            # Decode bytes to UTF-8 before returning for correct JSON serialization
            return [decode_bytes_to_utf8(r.cells) for r in rows]
        except Exception as e:
            logger.error(LOG_ERROR_EXECUTING_QUERY.format(str(e)))
            return self._format_error_response(str(e))

    async def analyze_workload_indexes(
        self,
        max_index_size_mb: int = Field(
            default=10000,
            description=(
                "Maximum index size in megabytes as integer value for limiting recommended index sizes "
                "(default 10000, must be greater than 0)"
            ),
            ge=1,
        ),
        method: Literal["dta", "llm"] = Field(
            default="dta",
            description=(
                "Analysis method as string value: 'dta' for Database Tuning Advisor algorithm "
                "or 'llm' for LLM-based optimization"
            ),
        ),
        ctx: Context | None = None,
    ) -> ResponseType:
        """Analyze frequently executed queries in the database and recommend optimal indexes."""
        try:
            sql_driver = self.sql_driver
            if method == "dta":
                index_tuning: IndexTuningBase = DatabaseTuningAdvisor(sql_driver)
            else:
                if ctx is None:
                    error_msg = "Context is required for LLM optimization method"
                    logger.error(error_msg)
                    return self._format_error_response(error_msg)
                index_tuning = LLMOptimizerTool(sql_driver, ctx=ctx)
            dta_tool = TextPresentation(sql_driver, index_tuning)
            result = await dta_tool.analyze_workload(max_index_size_mb=max_index_size_mb)
            return cast("ResponseType", result)
        except Exception as e:
            logger.error(LOG_ERROR_ANALYZING_WORKLOAD.format(str(e)))
            return self._format_error_response(str(e))

    async def analyze_query_indexes(
        self,
        queries: list[str] = Field(  # noqa: B008
            description=f"List of SQL query strings to analyze (up to {MAX_NUM_INDEX_TUNING_QUERIES} queries allowed)"
        ),
        max_index_size_mb: int = Field(
            default=10000,
            description=(
                "Maximum index size in megabytes as integer value for limiting recommended index sizes "
                "(default 10000, must be greater than 0)"
            ),
            ge=1,
        ),
        method: Literal["dta", "llm"] = Field(
            default="dta",
            description=(
                "Analysis method as string value: 'dta' for Database Tuning Advisor algorithm "
                "or 'llm' for LLM-based optimization"
            ),
        ),
        ctx: Context | None = None,
    ) -> ResponseType:
        """Analyze a list of SQL queries and recommend optimal indexes."""
        if len(queries) == 0:
            return self._format_error_response(ERROR_EMPTY_QUERIES)
        if len(queries) > MAX_NUM_INDEX_TUNING_QUERIES:
            return self._format_error_response(QUERIES_LIMIT_MESSAGE.format(MAX_NUM_INDEX_TUNING_QUERIES))

        try:
            sql_driver = self.sql_driver
            if method == "dta":
                index_tuning: IndexTuningBase = DatabaseTuningAdvisor(sql_driver)
            else:
                if ctx is None:
                    error_msg = "Context is required for LLM optimization method"
                    logger.error(error_msg)
                    return self._format_error_response(error_msg)
                index_tuning = LLMOptimizerTool(sql_driver, ctx=ctx)
            dta_tool = TextPresentation(sql_driver, index_tuning)
            result = await dta_tool.analyze_queries(queries=queries, max_index_size_mb=max_index_size_mb)
            return cast("ResponseType", result)
        except Exception as e:
            logger.error(LOG_ERROR_ANALYZING_QUERIES.format(str(e)))
            return self._format_error_response(str(e))

    async def analyze_db_health(
        self,
        health_type: str = Field(
            default="all",
            description=(
                f"Health check type as string value: single check or comma-separated list. "
                f"Valid values are: {HEALTH_TYPE_VALUES}. Use 'all' for comprehensive health check, "
                f"or specify individual checks like 'index,connection' for targeted analysis"
            ),
        ),
    ) -> ResponseType:
        """Analyze database health for specified components.

        Args:
            health_type: Comma-separated list of health check types to perform.
                        Valid values: index, connection, vacuum, sequence, replication, buffer, constraint, all
        """
        health_tool = DatabaseHealthTool(self.sql_driver)
        return await health_tool.health(health_type=health_type)

    async def get_top_queries(
        self,
        sort_by: str = Field(
            default="resources",
            description=(
                "Ranking criteria as string value: 'total_time' for total execution time across all calls, "
                "'mean_time' for mean execution time per call, or 'resources' for resource-intensive queries "
                "based on I/O, WAL, and execution time"
            ),
        ),
        limit: int = Field(
            default=10,
            description=(
                "Number of queries to return as integer value when ranking based on mean_time or total_time "
                "(default 10, must be greater than 0)"
            ),
            ge=1,
        ),
    ) -> ResponseType:
        """Reports the slowest or most resource-intensive queries using data from the 'pg_stat_statements' extension."""
        try:
            sql_driver = self.sql_driver
            top_queries_tool = TopQueriesCalc(sql_driver=sql_driver)

            if sort_by == "resources":
                return await top_queries_tool.get_top_resource_queries()
            if sort_by in {"mean_time", "total_time"}:
                # Map the sort_by values to what get_top_queries_by_time expects
                result = await top_queries_tool.get_top_queries_by_time(
                    limit=limit, sort_by="mean" if sort_by == "mean_time" else "total"
                )
            else:
                return self._format_error_response(ERROR_INVALID_SORT_CRITERIA)
        except Exception as e:
            logger.error(LOG_ERROR_GETTING_SLOW_QUERIES.format(str(e)))
            return self._format_error_response(str(e))
        else:
            return result

    def register_tools(self, mcp: FastMCP, prefix: str | None = None) -> int:
        """Register all tools directly with FastMCP server using mcp.tool().

        Automatically registers all enabled methods listed in _tools with their
        corresponding descriptions. Only enabled tools are registered.

        Args:
            mcp: FastMCP server instance to register tools with.
            prefix: Optional prefix for the database server. If provided, adds prefix
                to tool names (e.g., 'list_schemas' becomes 'app1_list_schemas') and
                adds prefix information to tool descriptions to indicate which database
                the tool belongs to and that tools with the same prefix should be used together.

        Returns:
            Number of registered tools.
        """
        registered_count = 0

        for method_name, tool_config in self._tools.items():
            if not tool_config.get("enabled", True):
                continue

            method = getattr(self, method_name)
            base_description = tool_config["description"]

            # Determine tool name: add prefix if provided
            tool_name: str | None = None
            if prefix:
                tool_name = f"{prefix}_{method_name}"

            # Add prefix information to description if prefix is provided
            if prefix:
                prefix_info = (
                    f"\n\nIMPORTANT: This tool belongs to database '{prefix}'. "
                    f"All tools with the same prefix '{prefix}' must be used together for operations on this database. "
                    f"Tools may differ only by their prefix (database identifier). "
                    f"Always use tools with the same prefix together and do not mix tools from different prefixes."
                )
                description = base_description + prefix_info
            else:
                description = base_description

            # Register tool with optional custom name
            if tool_name:
                mcp.tool(method, name=tool_name, description=description)
            else:
                mcp.tool(method, description=description)
            registered_count += 1

        return registered_count
