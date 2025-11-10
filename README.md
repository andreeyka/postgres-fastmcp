<div align="center">

# Postgres MCP Pro (FastMCP Fork)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![PyPI - Version](https://img.shields.io/pypi/v/postgres-mcp)](https://pypi.org/project/postgres-mcp/)

<h3>A Postgres MCP server with index tuning, explain plans, health checks, and safe SQL execution. Built on FastMCP.</h3>

<p><em>Fork of <a href="https://github.com/crystaldba/postgres-mcp">postgres-mcp</a> rewritten to use <a href="https://gofastmcp.com/">FastMCP</a> framework</em></p>

<div class="toc">
  <a href="#overview">Overview</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#technical-details">Technical Details</a> •
  <a href="#mcp-api">MCP API</a> •
  <a href="#development">Development</a>
</div>

</div>

## Overview

**Postgres MCP Pro** is an open-source MCP (Model Context Protocol) server built on top of [FastMCP](https://gofastmcp.com/) that supports you and your AI agents throughout the entire development process—from initial coding, through testing and deployment, to production tuning and maintenance.

This fork of the original [postgres-mcp](https://github.com/crystaldba/postgres-mcp) project has been rewritten to use FastMCP, providing:

- **🚀 Enhanced Performance** — FastMCP is optimized for high performance
- **🔧 Flexible Configuration** — support for multiple databases simultaneously via `config.json`
- **🌐 Multiple Transports** — support for HTTP, stdio, and streamable-http
- **🔐 Granular Access Control** — four access modes for different use cases
- **📦 Server Composition** — ability to mount multiple servers with prefixes

### Key Features

- **🔍 Database Health** — analyze index health, connection utilization, buffer cache, vacuum health, sequence limits, replication lag, and more
- **⚡ Index Tuning** — explore thousands of possible indexes to find the best solution for your workload, using industrial-strength algorithms
- **📈 Query Plans** — validate and optimize performance by reviewing EXPLAIN plans and simulating the impact of hypothetical indexes
- **🧠 Schema Intelligence** — context-aware SQL generation based on detailed understanding of the database schema
- **🛡️ Safe SQL Execution** — configurable access control, including support for read-only mode and safe SQL parsing, making it usable for both development and production

## Quick Start

### Prerequisites

Before getting started, ensure you have:
1. Access credentials for your database
2. Python 3.12 or higher
3. `uv` for dependency management (recommended)

### Installation

#### Install via uv

```bash
# Install uv if not already installed
curl -sSL https://astral.sh/uv/install.sh | sh

# Install postgres-mcp
uv pip install postgres-mcp
```

#### Install from source

```bash
# Clone the repository
git clone https://github.com/your-username/postgres-fastmcp.git
cd postgres-fastmcp

# Install dependencies
uv sync

# Install package in development mode
uv pip install -e .
```

### Running the Server

#### Single Database Mode (CLI)

For quick start with a single database:

```bash
uv run postgres-mcp \
  --database-uri "postgresql://user:password@localhost:5432/dbname" \
  --transport http \
  --port 8000
```

#### Configuration File Mode

Create a `config.json` file:

```json
{
    "name": "postgres-fastmcp",
    "transport": "http",
    "host": "0.0.0.0",
    "port": 8000,
    "endpoint": "mcp",
    "databases": {
        "production": {
            "database_uri": "postgresql://user:password@localhost:5432/production",
            "access_mode": "admin_ro",
            "streamable": false
        },
        "development": {
            "database_uri": "postgresql://user:password@localhost:5432/development",
            "access_mode": "admin_rw",
            "streamable": false
        }
    }
}
```

Then run:

```bash
uv run postgres-mcp
```

## Configuration

### Access Modes

The project supports four access modes for flexible security control:

| Mode | Schemas | Access | Tools | Description |
|------|---------|--------|-------|-------------|
| `USER_RO` | Only `public` | Read-only | Basic | User mode with access limited to public schema |
| `USER_RW` | Only `public` | Read/write (DML) | Basic | User mode with ability to modify data |
| `ADMIN_RO` | All schemas | Read-only | All | Administrative mode with access to all schemas |
| `ADMIN_RW` | All schemas | Full access (including DDL) | All | Full administrative access |

### Transports

#### HTTP Transport

HTTP transport allows running the server as a web application:

```bash
uv run postgres-mcp --transport http --port 8000
```

The server will be available at `http://localhost:8000/mcp` (or at the specified endpoint).

#### Streamable-HTTP Transport

Streamable-HTTP provides streaming data transfer:

```json
{
    "transport": "http",
    "databases": {
        "db1": {
            "database_uri": "postgresql://...",
            "streamable": true
        }
    }
}
```

#### STDIO Transport

STDIO transport is used for integration with MCP clients via standard input/output:

```bash
uv run postgres-mcp --transport stdio
```

### Configuration via Environment Variables

You can use environment variables for configuration:

```bash
export TRANSPORT=http
export HOST=0.0.0.0
export PORT=8000
export DATABASES__PRODUCTION__DATABASE_URI=postgresql://user:pass@localhost:5432/prod
export DATABASES__PRODUCTION__ACCESS_MODE=admin_ro
```

### MCP Client Integration

#### Cursor

In `~/.cursor/mcp.json`:

```json
{
    "mcpServers": {
        "postgres": {
            "type": "sse",
            "url": "http://localhost:8000/mcp"
        }
    }
}
```

#### Claude Desktop

In `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
    "mcpServers": {
        "postgres": {
            "command": "uv",
            "args": ["run", "postgres-mcp", "--transport", "stdio"],
            "env": {
                "DATABASES__DEFAULT__DATABASE_URI": "postgresql://user:pass@localhost:5432/dbname"
            }
        }
    }
}
```

## Technical Details

### FastMCP

This fork has been completely rewritten on top of [FastMCP](https://gofastmcp.com/), a modern framework for building MCP servers. FastMCP provides:

- High performance thanks to asynchronous architecture
- Built-in support for HTTP and stdio transports
- Server Composition for mounting multiple servers
- Simplified API for tool registration

### Multiple Databases

The project supports working with multiple databases simultaneously. Each database is configured separately with its own access mode and connection parameters.

When using HTTP transport with multiple databases configured, tools will be available with server name prefixes (Server Composition).

### Lifecycle Management

The server uses FastMCP lifespan for managing database connection lifecycles:

- Automatic connection pool creation on startup
- Proper connection closure on shutdown
- Signal handling (SIGINT, SIGTERM)

### Safe SQL Execution

The project uses multi-layered protection for safe SQL execution:

1. **SQL Parsing** — uses `pglast` library to analyze SQL before execution
2. **Read-only Transactions** — for read-only modes, PostgreSQL read-only transactions are used
3. **COMMIT/ROLLBACK Checks** — blocks attempts to bypass read-only mode
4. **Timeouts** — limits query execution time in restricted modes

## MCP API

The server provides functionality via [MCP tools](https://modelcontextprotocol.io/docs/concepts/tools).

### Available Tools

| Tool Name | Description |
|-----------|-------------|
| `list_schemas` | Lists all database schemas available in the PostgreSQL instance |
| `list_objects` | Lists database objects (tables, views, sequences, extensions) within a specified schema |
| `get_object_details` | Provides information about a specific database object, for example, a table's columns, constraints, and indexes |
| `execute_sql` | Executes SQL statements on the database, with read-only limitations when connected in restricted modes |
| `explain_query` | Gets the execution plan for a SQL query describing how PostgreSQL will process it. Can be invoked with hypothetical indexes to simulate the behavior after adding indexes |
| `get_top_queries` | Reports the slowest SQL queries based on total execution time using `pg_stat_statements` data |
| `analyze_workload_indexes` | Analyzes the database workload to identify resource-intensive queries, then recommends optimal indexes for them |
| `analyze_query_indexes` | Analyzes a list of specific SQL queries (up to 10) and recommends optimal indexes for them |
| `analyze_db_health` | Performs comprehensive health checks including: buffer cache hit rates, connection health, constraint validation, index health (duplicate/unused/invalid), sequence limits, and vacuum health |

### Access Mode Limitations

- **USER_RO/USER_RW**: Only basic tools available (`list_schemas`, `list_objects`, `get_object_details`, `execute_sql`)
- **ADMIN_RO/ADMIN_RW**: All tools available, including performance analysis and index tuning

## PostgreSQL Extension Installation (Optional)

To enable index tuning and comprehensive performance analysis, you need to install the `pg_stat_statements` and `hypopg` extensions in your database.

### Installing Extensions

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS hypopg;
```

**Important**: For `pg_stat_statements`, you must add it to `shared_preload_libraries` in PostgreSQL configuration and restart the server.

### Installing Extensions on Cloud Providers

If your Postgres database is running on a cloud provider managed service (AWS RDS, Azure SQL, Google Cloud SQL), the `pg_stat_statements` and `hypopg` extensions should already be available. You can just run the `CREATE EXTENSION` commands using a role with sufficient privileges.

### Installing Extensions on Self-Managed Postgres

If you are managing your own Postgres installation, you may need to do additional work:
- Before loading the `pg_stat_statements` extension, ensure it is listed in `shared_preload_libraries` in the Postgres configuration file
- The `hypopg` extension may require additional system-level installation (e.g., via your package manager) because it does not always ship with Postgres

## Usage Examples

### Get Database Health Overview

Ask your AI agent:
> Check the health of my database and identify any issues.

### Analyze Slow Queries

> What are the slowest queries in my database? And how can I speed them up?

### Get Performance Recommendations

> My app is slow. How can I make it faster?

### Generate Index Recommendations

> Analyze my database workload and suggest indexes to improve performance.

### Optimize a Specific Query

> Help me optimize this query: SELECT * FROM orders JOIN customers ON orders.customer_id = customers.id WHERE orders.created_at > '2023-01-01';

## Development

### Local Development Setup

1. **Install uv**:

   ```bash
   curl -sSL https://astral.sh/uv/install.sh | sh
   ```

2. **Clone the repository**:

   ```bash
   git clone https://github.com/your-username/postgres-fastmcp.git
   cd postgres-fastmcp
   ```

3. **Install dependencies**:

   ```bash
   uv sync
   ```

4. **Install package in development mode**:

   ```bash
   uv pip install -e .
   ```

### Running Tests

**Prerequisites:**
- Docker must be installed and running
- Docker images will be built automatically on first test run, or you can prepare them manually:

```bash
# Prepare Docker images for testing (optional, but recommended for faster test runs)
uv run python tests/prepare_docker_images.py
```

**Run all tests:**
```bash
uv run python -m pytest
```

**Run specific test file:**
```bash
uv run python -m pytest tests/unit/index/test_dta_calc.py -v
```

**Run tests with real database (integration tests):**
```bash
uv run python -m pytest tests/integration/ -v
```

### Code Formatting

The project uses `ruff` for formatting and linting:

```bash
uv run ruff format .
uv run ruff check .
```

### Type Checking

The project uses `mypy` for type checking:

```bash
uv run mypy src/
```

## Differences from Original Project

This fork differs from the original [postgres-mcp](https://github.com/crystaldba/postgres-mcp) with the following key changes:

| Original Project | This Fork |
|------------------|-----------|
| Standard MCP implementation | FastMCP framework |
| Single database per server | Multiple databases |
| Modes: restricted/unrestricted | Modes: USER_RO, USER_RW, ADMIN_RO, ADMIN_RW |
| SSE transport only | HTTP, stdio, streamable-http |
| Configuration via CLI/env | Configuration via config.json + env |

## Technical Notes

### Index Tuning

The index tuning implementation follows the same approach as the original project, using the [Anytime Algorithm of Database Tuning Advisor for Microsoft SQL Server](https://www.microsoft.com/en-us/research/wp-content/uploads/2020/06/Anytime-Algorithm-of-Database-Tuning-Advisor-for-Microsoft-SQL-Server.pdf).

### Database Health

Database health checks are adapted from [PgHero](https://github.com/ankane/pghero) and include:
- Index Health (unused, duplicate, bloated indexes)
- Buffer Cache Hit Rate
- Connection Health
- Vacuum Health (transaction ID wraparound prevention)
- Replication Health
- Constraint Health
- Sequence Health

### Postgres Client Library

The project uses [psycopg3](https://www.psycopg.org/) for asynchronous I/O connections to Postgres, providing access to the full Postgres feature set.

### Protected SQL Execution

The project implements multi-layered SQL protection:
- SQL parsing using `pglast` to detect and reject unsafe statements
- Read-only transactions for restricted modes
- Timeout limits for query execution
- Schema restrictions for user modes

## License

MIT License

## Acknowledgments

This project is a fork of [postgres-mcp](https://github.com/crystaldba/postgres-mcp) by [Crystal DBA](https://www.crystaldba.ai), rewritten to use [FastMCP](https://gofastmcp.com/).
