"""SQL queries for MCP tools."""

# Query to list all schemas
QUERY_LIST_SCHEMAS = """
SELECT
    schema_name,
    schema_owner,
    CASE
        WHEN schema_name LIKE 'pg_%' THEN 'System Schema'
        WHEN schema_name = 'information_schema' THEN 'System Information Schema'
        ELSE 'User Schema'
    END as schema_type
FROM information_schema.schemata
ORDER BY schema_type, schema_name
"""

# Query to list tables/views in a schema
QUERY_LIST_TABLES_VIEWS = """
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema = {} AND table_type = {}
ORDER BY table_name
"""

# Query to list sequences in a schema
QUERY_LIST_SEQUENCES = """
SELECT sequence_schema, sequence_name, data_type
FROM information_schema.sequences
WHERE sequence_schema = {}
ORDER BY sequence_name
"""

# Query to list extensions
QUERY_LIST_EXTENSIONS = """
SELECT extname, extversion, extrelocatable
FROM pg_extension
ORDER BY extname
"""

# Query to get columns for a table/view
QUERY_GET_COLUMNS = """
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = {} AND table_name = {}
ORDER BY ordinal_position
"""

# Query to get constraints for a table/view
QUERY_GET_CONSTRAINTS = """
SELECT tc.constraint_name, tc.constraint_type, kcu.column_name
FROM information_schema.table_constraints AS tc
LEFT JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = {} AND tc.table_name = {}
"""

# Query to get indexes for a table/view
QUERY_GET_INDEXES = """
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = {} AND tablename = {}
"""

# Query to get sequence details
QUERY_GET_SEQUENCE_DETAILS = """
SELECT sequence_schema, sequence_name, data_type, start_value, increment
FROM information_schema.sequences
WHERE sequence_schema = {} AND sequence_name = {}
"""

# Query to get extension details
QUERY_GET_EXTENSION_DETAILS = """
SELECT extname, extversion, extrelocatable
FROM pg_extension
WHERE extname = {}
"""
