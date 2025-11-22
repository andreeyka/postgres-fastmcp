# Multi-Endpoint Server Architecture

## Overview

The architecture allows creating a single HTTP server with multiple independent MCP endpoints, each connected to its own database with unique access rights.

## Components

### 1. Main Server

**Purpose:**
- Entry point for all requests
- Lifecycle management for all sub-servers
- Providing common endpoints (e.g., health check)

**Characteristics:**
- FastMCP server for lifecycle management and routing
- Has its own custom routes (e.g., `/health`)
- Uses Starlette for HTTP routing
- No custom tools (only health endpoint)

**Endpoints:**
- `/mcp` - main server (MCP endpoint, used for Server Composition when `endpoint=False`)
- `/health` - health check endpoint

### 2. Sub Servers

**Purpose:**
- Independent MCP servers, each with its own set of tools
- Each server is connected to its own database
- Each server has its own set of tools depending on access rights

**Characteristics:**
- FastMCP server with tools from ToolManager
- Unique database configuration for each server
- Unique set of tools depending on `access_mode`

**Endpoints:**
- `/app1/mcp` - server for app1
- `/app2/mcp` - server for app2
- `/app3/mcp` - server for app3
- `/app4/mcp` - server for app4

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    HTTP Server (Port 8000)                   │
│                    (Starlette Application)                   │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ Main Server  │   │  Sub Server  │   │  Sub Server  │
│  (FastMCP)   │   │  app1 (MCP)  │   │  app2 (MCP)  │
│              │   │              │   │              │
│ - /mcp       │   │ - /app1/mcp  │   │ - /app2/mcp  │
│ - /health    │   │              │   │              │
│              │   │ Tools:       │   │ Tools:       │
│ (no tools)   │   │ - list_*     │   │ - list_*     │
│              │   │ - execute_sql│   │ - execute_sql│
│              │   │ - ...        │   │ - ...        │
└──────────────┘   └──────┬───────┘   └──────┬───────┘
                          │                  │
                          ▼                  ▼
                    ┌──────────┐      ┌──────────┐
                    │   DB1    │      │   DB2    │
                    │ (user_ro)│      │ (user_rw)│
                    └──────────┘      └──────────┘
```

## Data Structure

### Sub-Server Configuration

```python
SUB_SERVERS_CONFIG = {
    "app1": DatabaseConfig(
        database_uri=SecretStr("postgresql://...@localhost:5432/db1"),
        access_mode="user_ro",  # Only basic tools (4 tools)
        endpoint=True,  # Mounted as separate endpoint /app1/mcp
        transport=None,  # Uses global transport (default: "http")
    ),
    "app2": DatabaseConfig(
        database_uri=SecretStr("postgresql://...@localhost:5432/db2"),
        access_mode="user_rw",  # Basic tools + write access (4 tools)
        endpoint=True,  # Mounted as separate endpoint /app2/mcp
        transport="http",  # Explicitly specified transport
    ),
    "app3": DatabaseConfig(
        database_uri=SecretStr("postgresql://...@localhost:5432/db3"),
        access_mode="admin_ro",  # All tools (9 tools)
        endpoint=True,  # Mounted as separate endpoint /app3/mcp
        transport="streamable-http",  # Uses streamable-http
    ),
    "app4": DatabaseConfig(
        database_uri=SecretStr("postgresql://...@localhost:5432/db4"),
        access_mode="admin_rw",  # All tools + unrestricted execute_sql (9 tools)
        endpoint=True,  # Mounted as separate endpoint /app4/mcp
        # transport not specified - uses global transport
    ),
}
```

**`endpoint` parameter:**
- `True`: Server is mounted as a separate HTTP endpoint at path `/{server_name}/mcp`
- `False` (default): Server is mounted in the main endpoint via FastMCP mount() (Server Composition)

**`transport` parameter:**
- Only used when `endpoint=True` and global transport = `'http'`
- If `transport` is not specified (None) and `endpoint=True`: uses global transport (default: `'http'`)
- If `transport` is explicitly specified and `endpoint=True`: uses the specified value (`'http'` or `'streamable-http'`)
- If `endpoint=False`: `transport` parameter is ignored
- Valid values: `'http'`, `'streamable-http'`, or `None` (default)

**Tool prefixes:**
A prefix is automatically added to tool names based on the server name. This prevents name conflicts when multiple MCP servers are connected to a single agent.

## Access Modes and Tool Sets

### Tool Name Prefixes

A prefix is automatically added to tool names based on the server name from the configuration. This prevents name conflicts when multiple MCP servers are connected to a single agent.

**Example:**
- Server `app1` with tool `list_objects` → tool name: `app1_list_objects`
- Server `app2` with tool `list_objects` → tool name: `app2_list_objects`

### user role (4 tools)

**Tools with prefix:**
- `{prefix}_list_objects` - list objects in public schema
- `{prefix}_get_object_details` - object details
- `{prefix}_explain_query` - query execution plan
- `{prefix}_execute_sql` - SQL execution (read-only for restricted, read-write for unrestricted)

**Disabled tools:**
- `list_schemas` - unavailable (only public schema)
- `analyze_workload_indexes` - unavailable
- `analyze_query_indexes` - unavailable
- `analyze_db_health` - unavailable
- `get_top_queries` - unavailable

### full role (9 tools)

**Tools with prefix:**
- All basic tools (4 tools) with prefix
- `{prefix}_list_schemas` - list all schemas
- `{prefix}_analyze_workload_indexes` - index analysis by workload
- `{prefix}_analyze_query_indexes` - index analysis by queries
- `{prefix}_analyze_db_health` - database health analysis
- `{prefix}_get_top_queries` - top slow queries

**Difference between restricted vs unrestricted:**
- restricted: `{prefix}_execute_sql` is limited (SELECT only)
- unrestricted: `{prefix}_execute_sql` is unrestricted (DDL, DML, DCL allowed for full role)

## Lifecycle (Lifespan)

### Initialization (Startup)

1. **Create ToolManager for each sub-server**
   - Each ToolManager is created with a unique database configuration
   - Each ToolManager has its own connection pool

2. **Register tools on FastMCP servers**
   - Tools are registered via `tool_manager.register_tools(sub_mcp, prefix=app_name)`
   - Each tool automatically receives a prefix to identify the database
   - For servers with `endpoint=True`, separate FastMCP servers are created
   - For servers with `endpoint=False`, tools are registered on the main server

3. **Create HTTP applications**
   - Each FastMCP server is converted to a Starlette application via `http_app(path="/mcp")`
   - The main server is also converted to a Starlette application

4. **Mounting via Starlette Mount**
   - Servers with `endpoint=True` are mounted as separate endpoints: `Mount(f"/{app_name}", app=sub_app)`
   - Servers with `endpoint=False` are mounted in the main endpoint via FastMCP mount() (Server Composition)
   - The main server is mounted at the root path: `Mount("/", app=main_app)`

5. **Initialize database connections**
   - For each ToolManager, a database connection is established
   - Verify that the connection is established to the correct database

### Shutdown

1. **Close database connections**
   - Each ToolManager closes its connection pool
   - AsyncExitStack is used for proper cleanup of all resources

## Key Principles

### 1. Server Isolation

Each sub-server is completely isolated:
- Its own ToolManager instance
- Its own database connection pool
- Its own set of tools
- Its own HTTP endpoint

### 2. Using Starlette Mount and FastMCP mount()

**Important:**
- FastMCP `mount()` - for Server Composition (servers with `endpoint=False`, tool/resource/prompt prefixes in one endpoint)
- Starlette `Mount` - for different HTTP endpoints (servers with `endpoint=True`, different paths)

### 3. Lifecycle Management

All components are managed through a single `lifespan` context manager:
- ToolManagers enter context via `async with tool_manager`
- HTTP applications enter context via `async with app.lifespan(app)`
- `AsyncExitStack` is used for proper cleanup of all resources

### 4. Security

- Each server has its own access rights via `access_mode`
- SafeSqlDriver restricts access to schemas and operations in user mode
- Access to `information_schema.schemata` is blocked in user mode

## Usage Example

### Creating a Sub-Server

```python
def create_sub_server(app_name: str, config: DatabaseConfig) -> tuple[FastMCP, ToolManager]:
    """Create a sub-server with tools from ToolManager."""
    sub_mcp = FastMCP(name=f"SubServer-{app_name}")
    tool_manager = ToolManager(config)
    tool_manager.register_tools(sub_mcp, prefix=app_name)
    return sub_mcp, tool_manager
```

### Creating the Main Server

```python
def create_main_server() -> Starlette:
    """Create the main server with health endpoint and mounted sub-servers."""
    main_mcp = FastMCP(name="MainServer")
    
    # Health check endpoint
    @main_mcp.custom_route("/health", methods=["GET"])
    async def health_check(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "healthy", "service": "main-server"})
    
    # Create sub-servers
    tool_managers: dict[str, ToolManager] = {}
    sub_apps: list[tuple[str, Starlette]] = []
    
    for app_name, config in SUB_SERVERS_CONFIG.items():
        sub_mcp, tool_manager = create_sub_server(app_name, config)
        tool_managers[app_name] = tool_manager
        sub_app = sub_mcp.http_app(path="/mcp")
        sub_apps.append((app_name, sub_app))
    
    main_app = main_mcp.http_app(path="/mcp")
    
    # Combined lifespan
    @asynccontextmanager
    async def combined_lifespan(_app: Starlette) -> AsyncIterator[dict[str, Any]]:
        async with AsyncExitStack() as stack:
            # Enter ToolManager context
            for tool_manager in tool_managers.values():
                await stack.enter_async_context(tool_manager)
            
            # Initialize database connections
            for app_name, tool_manager in tool_managers.items():
                await tool_manager.db_connection.pool_connect()
            
            # Enter HTTP application context
            for app_name, sub_app in sub_apps:
                if hasattr(sub_app, "lifespan") and sub_app.lifespan:
                    await stack.enter_async_context(sub_app.lifespan(_app))
            
            if hasattr(main_app, "lifespan") and main_app.lifespan:
                await stack.enter_async_context(main_app.lifespan(_app))
            
            yield {}
    
    # Mounting via Starlette Mount
    routes = [
        Mount(f"/{app_name}", app=sub_app)
        for app_name, sub_app in sub_apps
    ]
    routes.append(Mount("/", app=main_app))
    
    return Starlette(routes=routes, lifespan=combined_lifespan)
```

### Running the Server

```python
async def run_server() -> None:
    """Run the server."""
    app = create_main_server()
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
```

## MCP Client Configuration

To connect to each server via an MCP client (e.g., Cursor):

```json
{
  "mcpServers": {
    "main": {
      "url": "http://localhost:8000/mcp",
      "transport": "http"
    },
    "app1": {
      "url": "http://localhost:8000/app1/mcp",
      "transport": "http"
    },
    "app2": {
      "url": "http://localhost:8000/app2/mcp",
      "transport": "http"
    },
    "app3": {
      "url": "http://localhost:8000/app3/mcp",
      "transport": "http"
    },
    "app4": {
      "url": "http://localhost:8000/app4/mcp",
      "transport": "http"
    }
  }
}
```

**Note:** The main server (`main`) only provides a health check endpoint (`/health`). All database tools are provided by sub-servers (`app1`, `app2`, `app3`, `app4`). When using Server Composition (servers with `endpoint=False`), tools are available at the main endpoint with prefixes.

## Architecture Benefits

1. **Scalability**: Easy to add new sub-servers
2. **Isolation**: Each server is independent and isolated
3. **Flexibility**: Different access rights for different servers
4. **Single entry point**: One HTTP server for all endpoints
5. **Resource management**: Centralized lifecycle management

## Limitations

1. **Single port**: All endpoints run on one port
2. **Single process**: All servers run in one process
3. **Shared configuration**: Some settings (e.g., timeout) are shared across all servers

## Extensions

### Possible Improvements:

1. **Dynamic configuration**: Load configuration from file or database
2. **Monitoring**: Add metrics and logging for each server
3. **Authentication**: Add authentication for each endpoint
4. **Rate limiting**: Request limiting for each server
5. **Health checks**: Individual health checks for each server
