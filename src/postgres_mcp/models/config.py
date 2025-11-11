"""Configuration models for database and tools."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr, model_validator

from postgres_mcp.enums import AccessMode, ToolName, UserRole


# Convenience constants for backward compatibility and easier access
AVAILABLE_TOOLS: list[ToolName] = ToolName.available_tools()
ADMIN_TOOLS: list[ToolName] = ToolName.admin_tools()

# Note: Basic tools (available for both USER and FULL roles) can be computed as:
# BASIC_TOOLS = AVAILABLE_TOOLS - ADMIN_TOOLS = [LIST_OBJECTS, GET_OBJECT_DETAILS, EXPLAIN_QUERY, EXECUTE_SQL]


class ToolsConfig(BaseModel):
    """Configuration for available tools.

    Each tool can be enabled or disabled individually.
    Fields are automatically generated from AVAILABLE_TOOLS to ensure consistency.
    """

    list_schemas: bool = Field(default=True, description="Enable list_schemas tool")
    list_objects: bool = Field(default=True, description="Enable list_objects tool")
    get_object_details: bool = Field(default=True, description="Enable get_object_details tool")
    explain_query: bool = Field(default=True, description="Enable explain_query tool")
    execute_sql: bool = Field(default=True, description="Enable execute_sql tool")
    analyze_workload_indexes: bool = Field(default=True, description="Enable analyze_workload_indexes tool")
    analyze_query_indexes: bool = Field(default=True, description="Enable analyze_query_indexes tool")
    analyze_db_health: bool = Field(default=True, description="Enable analyze_db_health tool")
    get_top_queries: bool = Field(default=True, description="Enable get_top_queries tool")

    @model_validator(mode="after")
    def validate_tool_fields(self) -> ToolsConfig:
        """Validate that all tools from AVAILABLE_TOOLS have corresponding fields.

        Returns:
            ToolsConfig instance.

        Raises:
            ValueError: If any tool from AVAILABLE_TOOLS is missing a field.
        """
        model_fields = set(self.__class__.model_fields.keys())
        available_tool_values = {tool.value for tool in AVAILABLE_TOOLS}

        missing_fields = available_tool_values - model_fields
        if missing_fields:
            missing_list = sorted(missing_fields)
            error_msg = (
                f"ToolsConfig is missing fields for tools: {missing_list}. "
                f"All tools from AVAILABLE_TOOLS must have corresponding fields in ToolsConfig."
            )
            raise ValueError(error_msg)

        extra_fields = model_fields - available_tool_values
        if extra_fields:
            extra_list = sorted(extra_fields)
            error_msg = (
                f"ToolsConfig has extra fields that are not in AVAILABLE_TOOLS: {extra_list}. "
                f"All fields in ToolsConfig must correspond to tools in AVAILABLE_TOOLS."
            )
            raise ValueError(error_msg)

        return self

    def get_enabled_tools(self) -> set[ToolName]:
        """Get set of enabled tool names.

        Returns:
            Set of enabled tool names.
        """
        enabled = set()
        for tool_name in AVAILABLE_TOOLS:
            if getattr(self, tool_name.value, False):
                enabled.add(tool_name)
        return enabled


class DatabaseConfig(BaseModel):
    """Database server configuration."""

    database_uri: SecretStr = Field(description="Database connection URL")
    endpoint: bool = Field(
        default=False,
        description=(
            "If True, server is mounted as a separate HTTP endpoint at path `/{server_name}/mcp`. "
            "If False, server is mounted in the main endpoint via FastMCP mount() (Server Composition)."
        ),
    )
    transport: str | None = Field(
        default=None,
        description=(
            "HTTP transport type for this database server: 'http' or 'streamable-http'. "
            "Only used when endpoint=True and main transport is 'http'. "
            "If None and endpoint=True, uses global transport (default: 'http'). "
            "If endpoint=False, this parameter is ignored."
        ),
    )
    extra_kwargs: dict[str, str] = Field(default_factory=dict, description="Extra keyword arguments")
    access_mode: AccessMode = Field(
        default=AccessMode.RESTRICTED,
        description=(
            "SQL access level for the server. "
            "Available modes: 'restricted' (read-only, SELECT only), "
            "'unrestricted' (read-write, DML: INSERT/UPDATE/DELETE, or full access with DDL for full role)."
        ),
    )
    role: UserRole = Field(
        default=UserRole.USER,
        description=(
            "User role that determines schema access and available tools. "
            "Available roles: 'user' (only public schema, basic tools - 4 tools), "
            "'full' (all schemas, all tools - 9 tools, extended privileges)."
        ),
    )
    # Connection pool settings
    pool_min_size: int = Field(default=1, description="Minimum number of connections in the pool")
    pool_max_size: int = Field(default=5, description="Maximum number of connections in the pool")
    safe_sql_timeout: int = Field(
        default=30,
        description=(
            "Timeout in seconds for SafeSqlDriver. "
            "Used for all modes except 'full' role with 'unrestricted' access_mode."
        ),
    )
    table_prefix: str | None = Field(
        default=None,
        description=(
            "Optional table name prefix for 'user' role. "
            "If set, only tables/views/sequences with names starting with this prefix are accessible. "
            "Works only for 'user' role. Ignored for 'full' role."
        ),
    )
    tools: ToolsConfig | None = Field(
        default=None,
        description=(
            "Optional tools configuration. "
            "If None, default tools configuration is used based on role "
            "(admin tools are disabled for 'user' role). "
            "If specified, tools are enabled/disabled according to this configuration."
        ),
    )
    tool_prefix: str | None = Field(
        default=None,
        description=(
            "Optional prefix for tool names. "
            "If specified, all tools will be prefixed with this name (e.g., 'myprefix_list_objects'). "
            "Works in both HTTP and stdio modes. "
            "If not specified, uses default behavior: no prefix for single server, server name as prefix for multiple servers."
        ),
    )

    def get_enabled_tools(self) -> set[ToolName]:
        """Get set of enabled tool names based on role and tools configuration.

        If tools config is specified, merges explicit settings with role-based defaults.
        If tools config is not specified, uses role-based defaults only.

        Returns:
            Set of enabled tool names.
        """
        # Get role-based defaults
        role_defaults = {tool for tool in AVAILABLE_TOOLS if self.role == UserRole.FULL or tool not in ADMIN_TOOLS}

        if self.tools is not None:
            # Get only explicitly configured tools (exclude_unset=True returns only fields set in config)
            explicit_tools_config = self.tools.model_dump(exclude_unset=True)
            tools_to_enable = set()
            for tool_name in AVAILABLE_TOOLS:
                # Check if tool was explicitly configured using its string value
                if tool_name.value in explicit_tools_config:
                    # Tool was explicitly configured, use its value
                    if explicit_tools_config[tool_name.value]:
                        tools_to_enable.add(tool_name)
                elif tool_name in role_defaults:
                    # Tool was not explicitly configured, use role-based default
                    tools_to_enable.add(tool_name)
            return tools_to_enable

        # Use default: all tools except admin tools for USER role
        return role_defaults
