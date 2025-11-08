"""Tool descriptions for MCP tools."""

from postgres_mcp.tool.constants import PG_STAT_STATEMENTS


# Basic tools descriptions
DESC_LIST_SCHEMAS = "List all schemas in the database"
DESC_LIST_OBJECTS = "List objects in a schema"
DESC_GET_OBJECT_DETAILS = "Show detailed information about a database object"

# Query explanation tool description
DESC_EXPLAIN_QUERY = (
    "Explains the execution plan for a SQL query, showing how the database will execute it "
    "and provides detailed cost estimates."
)

# SQL execution tool descriptions
DESC_EXECUTE_SQL_UNRESTRICTED = "Execute any SQL query"
DESC_EXECUTE_SQL_RESTRICTED = "Execute a read-only SQL query"

# Index analysis tools descriptions
DESC_ANALYZE_WORKLOAD_INDEXES = "Analyze frequently executed queries in the database and recommend optimal indexes"
DESC_ANALYZE_QUERY_INDEXES = "Analyze a list of (up to 10) SQL queries and recommend optimal indexes"

# Database health tool description
DESC_ANALYZE_DB_HEALTH = (
    "Analyzes database health. Here are the available health checks:\n"
    "- index - checks for invalid, duplicate, and bloated indexes\n"
    "- connection - checks the number of connection and their utilization\n"
    "- vacuum - checks vacuum health for transaction id wraparound\n"
    "- sequence - checks sequences at risk of exceeding their maximum value\n"
    "- replication - checks replication health including lag and slots\n"
    "- buffer - checks for buffer cache hit rates for indexes and tables\n"
    "- constraint - checks for invalid constraints\n"
    "- all - runs all checks\n"
    "You can optionally specify a single health check or a comma-separated list of health checks. "
    "The default is 'all' checks."
)

# Top queries tool description
DESC_GET_TOP_QUERIES = (
    "Reports the slowest or most resource-intensive queries using data from the '" + PG_STAT_STATEMENTS + "' extension."
)

# Parameter descriptions
DESC_HYPOTHETICAL_INDEXES = """A list of hypothetical indexes to simulate. Each index must be a dictionary with these keys:
    - 'table': The table name to add the index to (e.g., 'users')
    - 'columns': List of column names to include in the index (e.g., ['email'] or ['last_name', 'first_name'])
    - 'using': Optional index method (default: 'btree', other options include 'hash', 'gist', etc.)

Examples: [
    {"table": "users", "columns": ["email"], "using": "btree"},
    {"table": "orders", "columns": ["user_id", "created_at"]}
]
If there is no hypothetical index, you can pass an empty list."""
