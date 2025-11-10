# Docker Test Environment

**⚠️ This docker-compose setup is for TESTING ONLY.**

This directory contains configuration for running a test environment with MCP server and PostgreSQL.
For production Docker usage, see the main Dockerfile and docker-entrypoint.sh in the project root.

## Structure

- `docker-compose.yml` - main Docker Compose configuration
- `postgres/init-db.sql` - PostgreSQL initialization script with test databases
- `postgres/init-4-databases.sql` - PostgreSQL initialization script with 4 databases for different access modes
- `config.test.json` - test MCP server configuration

## Test Databases

The initialization scripts create test databases with different access modes:

1. **user_ro_db** - Read-only access, public schema only
2. **user_rw_db** - Read-write access, public schema only
3. **admin_ro_db** - Read-only access, all schemas
4. **admin_rw_db** - Full access, all schemas

## Running

```bash
# Build and start all services
docker-compose up --build

# Run in background
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Stop and remove volumes (will delete all database data)
docker-compose down -v
```

## Access

- **MCP server**: http://localhost:8000
- **PostgreSQL**: available only inside Docker network (port 5432)

## Network

All services run in an isolated Docker network `mcp-network`.
Only port 8000 for the MCP server is published externally.
PostgreSQL is available only inside the Docker network via hostname `postgres`.
