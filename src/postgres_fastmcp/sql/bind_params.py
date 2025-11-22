# --- Parameter replacement ---

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from pglast import parse_sql
from pglast.ast import A_Expr, ColumnRef, JoinExpr, Node, RangeVar, SelectStmt, SortBy, SortGroupClause
from pglast.visitors import Visitor


if TYPE_CHECKING:
    from .sql_driver import SqlDriver

from .safe_sql import SafeSqlDriver


logger = logging.getLogger(__name__)

# Error messages
_TARGET_LIST_NONE_ERROR = "targetList cannot be None after validation"
_REPLACE_PARAMETERS_ERROR = "Error replacing parameters"

# Column reference field counts
_QUALIFIED_COLUMN_FIELDS = 2  # Qualified column reference (e.g., table.column or table.*)

# Histogram bounds constants
_MIN_HISTOGRAM_BOUNDS = 3  # Minimum number of histogram bounds needed for median calculation


# --- Visitor Classes ---


class TableAliasVisitor(Visitor):  # type: ignore[misc]
    """Extracts table aliases and names from the SQL AST."""

    def __init__(self) -> None:
        super().__init__()  # Initialize the base Visitor class
        self.aliases: dict[str, str] = {}
        self.tables: set[str] = set()

    def __call__(self, node: Node) -> tuple[dict[str, str], set[str]]:
        """Visit the AST node and return aliases and tables.

        Args:
            node: The AST node to visit.

        Returns:
            A tuple of (aliases dict, tables set).
        """
        super().__call__(node)
        return self.aliases, self.tables

    def visit_RangeVar(self, _ancestors: list[Node], node: Node) -> None:  # noqa: N802
        """Visit table references, including those in FROM clause."""
        if isinstance(node, RangeVar):  # Type narrowing for RangeVar
            if node.relname is not None:
                self.tables.add(node.relname)
            if node.alias and node.alias.aliasname is not None:
                self.aliases[node.alias.aliasname] = str(node.relname)

    def visit_JoinExpr(self, _ancestors: list[Node], node: Node) -> None:  # noqa: N802
        """Visit both sides of JOIN expressions."""
        if isinstance(node, JoinExpr):  # Type narrowing for JoinExpr
            if node.larg is not None:
                self(node.larg)
            if node.rarg is not None:
                self(node.rarg)


class ColumnCollector(Visitor):  # type: ignore[misc]
    """Collects columns used in WHERE, JOIN, ORDER BY, GROUP BY, HAVING, and SELECT clauses."""

    def __init__(self, sql_driver: SqlDriver | None = None, column_cache: dict[str, set[str]] | None = None) -> None:
        """Initialize ColumnCollector.

        Args:
            sql_driver: Optional SQL driver to use for database queries.
                Not used directly in this class, but may be needed by subclasses.
            column_cache: Optional cache of table -> set of column names.
                If provided, used to verify column existence. If None, falls back to
                permissive behavior (returns True for all checks).
        """
        self.sql_driver = sql_driver
        super().__init__()
        self.context_stack: list[tuple[set[str], dict[str, str]]] = []  # Stack of (tables, aliases) for each scope
        self.columns: dict[str, set[str]] = {}  # Collected columns, keyed by table
        self.target_list: list[Any] | None = None
        self.inside_select = False
        self.column_aliases: dict[str, dict[str, Any]] = {}  # Track column aliases and their definitions
        self.current_query_level = 0  # Track nesting level for subqueries
        self.column_cache: dict[str, set[str]] = column_cache or {}

    def __call__(self, node: Node) -> dict[str, set[str]]:
        """Visit the AST node and return collected columns.

        Args:
            node: The AST node to visit.

        Returns:
            A dictionary of columns keyed by table name.
        """
        super().__call__(node)
        return self.columns

    def visit_SelectStmt(self, _ancestors: list[Node], node: Node) -> None:  # noqa: N802
        """Visit a SelectStmt node and process its targetList for column aliases.

        Args:
            _ancestors: List of ancestor nodes in the AST (unused).
            node: The SelectStmt AST node to visit.
        """
        if isinstance(node, SelectStmt):
            self.inside_select = True
            self.current_query_level += 1
            query_level = self.current_query_level

            # Collect tables and aliases
            alias_visitor = TableAliasVisitor()
            if hasattr(node, "fromClause") and node.fromClause:
                for from_item in node.fromClause:
                    alias_visitor(from_item)
            scope_tables = alias_visitor.tables
            scope_aliases = alias_visitor.aliases

            # Push new context for this scope
            self.context_stack.append((scope_tables, scope_aliases))

            # First pass: collect column aliases from targetList
            if hasattr(node, "targetList") and node.targetList:
                self.target_list = node.targetList
                if self.target_list is None:
                    raise ValueError(_TARGET_LIST_NONE_ERROR)
                for target_entry in self.target_list:
                    if hasattr(target_entry, "name") and target_entry.name:
                        # This is a column alias
                        col_alias = target_entry.name
                        # Store the expression node for this alias
                        if hasattr(target_entry, "val"):
                            self.column_aliases[col_alias] = {
                                "node": target_entry.val,
                                "level": query_level,
                            }

            # Second pass: process the rest of the query
            self._process_query_clauses(node)

            # Pop context after processing
            self.context_stack.pop()
            self.inside_select = False
            self.current_query_level -= 1

    def _process_query_clauses(self, node: SelectStmt) -> None:  # noqa: C901
        """Process various query clauses for column collection.

        Args:
            node: The SelectStmt node to process.
        """
        # Process targetList expressions
        if hasattr(node, "targetList") and node.targetList:
            self.target_list = node.targetList
            if self.target_list is None:
                raise ValueError(_TARGET_LIST_NONE_ERROR)
            for target_entry in self.target_list:
                if hasattr(target_entry, "val"):
                    self(target_entry.val)

        # Handle GROUP BY clause
        if hasattr(node, "groupClause") and node.groupClause:
            for group_item in node.groupClause:
                if isinstance(group_item, SortGroupClause) and isinstance(group_item.tleSortGroupRef, int):
                    ref_index = group_item.tleSortGroupRef
                    if self.target_list is not None and ref_index <= len(self.target_list):
                        target_entry = self.target_list[ref_index - 1]  # 1-based index
                        if hasattr(target_entry, "val"):
                            self(target_entry.val)
                        if hasattr(target_entry, "expr"):
                            self(target_entry.expr)  # Visit the expression

        # Process WHERE clause (including subqueries)
        if hasattr(node, "whereClause") and node.whereClause:
            self(node.whereClause)

        # Process FROM clause (may contain subqueries)
        if hasattr(node, "fromClause") and node.fromClause:
            for from_item in node.fromClause:
                self(from_item)

        # Process HAVING clause
        if hasattr(node, "havingClause") and node.havingClause:
            self(node.havingClause)

        # Handle ORDER BY clause
        if hasattr(node, "sortClause") and node.sortClause:
            for sort_item in node.sortClause:
                self._process_sort_item(sort_item)

    def _process_sort_item(self, sort_item: SortBy) -> None:
        """Process a sort item, resolving column aliases if needed.

        Args:
            sort_item: The SortBy node to process.
        """
        if not hasattr(sort_item, "node"):
            return

        # If it's a simple column reference, it might be an alias
        if isinstance(sort_item.node, ColumnRef) and hasattr(sort_item.node, "fields") and sort_item.node.fields:
            fields = [f.sval for f in sort_item.node.fields if hasattr(f, "sval")]
            if len(fields) == 1:
                col_name = fields[0]
                # Check if this is a known alias
                if col_name in self.column_aliases:
                    # Process the original expression instead
                    alias_info = self.column_aliases[col_name]
                    if alias_info["level"] == self.current_query_level:
                        self(alias_info["node"])
                        return

        # Regular processing for non-alias sort items
        self(sort_item.node)

    def visit_ColumnRef(self, _ancestors: list[Node], node: Node) -> None:  # noqa: C901, N802
        """Visit a ColumnRef node and collect column names, skipping aliases."""
        if isinstance(node, ColumnRef) and self.inside_select:
            if not hasattr(node, "fields") or not node.fields:
                return

            fields = [f.sval if hasattr(f, "sval") else "*" for f in node.fields]

            # Skip collecting if this is a reference to a column alias
            if len(fields) == 1 and (fields[0] == "*" or fields[0] in self.column_aliases):
                return

            if len(fields) == _QUALIFIED_COLUMN_FIELDS and fields[1] == "*":
                return

            # Use current scope's tables and aliases
            current_tables, current_aliases = self.context_stack[-1] if self.context_stack else ({}, {})

            if len(fields) == _QUALIFIED_COLUMN_FIELDS:  # Qualified column (e.g., u.name)
                table_or_alias, column = fields
                table = current_aliases.get(table_or_alias, table_or_alias)
                if table not in self.columns:
                    self.columns[table] = set()
                self.columns[table].add(column)
            elif len(fields) == 1:  # Unqualified column
                column = fields[0]
                if len(current_tables) == 1:  # Only one table in scope
                    table = next(iter(current_tables))
                    if table not in self.columns:
                        self.columns[table] = set()
                    self.columns[table].add(column)
                else:
                    # Try to find which table this column belongs to
                    for table in current_tables:
                        if self._column_exists(table, column):
                            if table not in self.columns:
                                self.columns[table] = set()
                            self.columns[table].add(column)
                            break

    def _column_exists(self, table: str, column: str) -> bool:
        """Check if column exists in table.

        Args:
            table: Table name.
            column: Column name.

        Returns:
            True if column exists in the table according to column_cache,
            False otherwise. If column_cache is empty, returns True to avoid
            false negatives (permissive behavior for backward compatibility).
        """
        if not self.column_cache:
            # If cache is not provided, return True for permissive behavior
            # This maintains backward compatibility
            return True

        # Check if table exists in cache
        table_columns = self.column_cache.get(table.lower())
        if table_columns is None:
            return False

        # Check if column exists in table
        return column.lower() in {col.lower() for col in table_columns}

    def visit_A_Expr(self, _ancestors: list[Node], node: Node) -> None:  # noqa: N802
        """Visit an A_Expr node (arithmetic or comparison expression)."""
        if isinstance(node, A_Expr) and self.inside_select:
            # Process left expression
            if hasattr(node, "lexpr") and node.lexpr:
                self(node.lexpr)
                if isinstance(node.lexpr, SelectStmt):
                    alias_visitor = TableAliasVisitor()
                    alias_visitor(node.lexpr)
                    self.context_stack.append((alias_visitor.tables, alias_visitor.aliases))
                    self(node.lexpr)
                    self.context_stack.pop()

            # Process right expression
            if hasattr(node, "rexpr") and node.rexpr:
                if isinstance(node.rexpr, SelectStmt):
                    alias_visitor = TableAliasVisitor()
                    alias_visitor(node.rexpr)
                    self.context_stack.append((alias_visitor.tables, alias_visitor.aliases))
                    self(node.rexpr)
                    self.context_stack.pop()
                else:
                    self(node.rexpr)

            # Special handling for IN clauses with subqueries
            if (
                hasattr(node, "kind")
                and node.kind == 0  # 0 is the kind for IN operator
                and hasattr(node, "rexpr")
                and node.rexpr
                and isinstance(node.rexpr, SelectStmt)
            ):
                # Process the subquery in the IN clause
                alias_visitor = TableAliasVisitor()
                alias_visitor(node.rexpr)
                self.context_stack.append((alias_visitor.tables, alias_visitor.aliases))
                self(node.rexpr)
                self.context_stack.pop()

    def visit_JoinExpr(self, _ancestors: list[Node], node: Node) -> None:  # noqa: N802
        """Visit a JoinExpr node to handle JOIN conditions."""
        if isinstance(node, JoinExpr) and self.inside_select:  # Type narrowing for JoinExpr
            if hasattr(node, "larg") and node.larg:
                self(node.larg)
            if hasattr(node, "rarg") and node.rarg:
                self(node.rarg)
            if hasattr(node, "quals") and node.quals:
                self(node.quals)

    def visit_SortBy(self, _ancestors: list[Node], node: Node) -> None:  # noqa: N802
        """Visit a SortBy node (ORDER BY expression)."""
        if (
            isinstance(node, SortBy) and self.inside_select and hasattr(node, "node") and node.node
        ):  # Type narrowing for SortBy
            self(node.node)


class SqlBindParams:
    """Replaces parameter placeholders with appropriate values based on column statistics."""

    def __init__(self, sql_driver: SqlDriver) -> None:
        """Initialize SqlBindParams.

        Args:
            sql_driver: The SQL driver to use for database queries.
        """
        self.sql_driver = sql_driver
        self._column_stats_cache: dict[str, dict[str, Any] | None] = {}

    def _extract_tables_from_query(self, query: str) -> set[str]:
        """Extract table names from a SQL query.

        Args:
            query: SQL query string.

        Returns:
            Set of table names found in the query.
        """
        try:
            parsed = parse_sql(query)
            if not parsed:
                return set()
            stmt = parsed[0].stmt
            if not isinstance(stmt, SelectStmt):
                return set()

            visitor = TableAliasVisitor()
            visitor(stmt)
        except Exception:
            logger.debug("Error extracting tables from query: %s", query[:50])
            return set()
        else:
            return visitor.tables

    async def replace_parameters(self, query: str) -> str:  # noqa: C901
        """Replace parameter placeholders with appropriate values based on column statistics.

        This handles queries from pg_stat_statements where literals
        have been replaced with $1, $2, etc.
        """
        try:
            modified_query = query
            # Find all parameter placeholders
            param_matches = list(re.finditer(r"\$\d+", query))
            if not param_matches:
                logger.debug("No parameters found for query: %s...", query[:50])
                return query

            # Extract tables and build column cache for accurate column existence checks
            tables = self._extract_tables_from_query(query)
            column_cache = await self.build_column_cache(tables) if tables else None

            # Handle common special cases in a specific order to prevent incorrect replacements

            # 1. Handle LIMIT clauses - these should always be replaced with integers
            limit_pattern = re.compile(r"limit\s+\$(\d+)", re.IGNORECASE)
            modified_query = limit_pattern.sub(r"limit 100", modified_query)

            # 2. Handle static INTERVAL expressions
            interval_pattern = re.compile(r"interval\s+'(\d+)\s+([a-z]+)'", re.IGNORECASE)
            modified_query = interval_pattern.sub(lambda m: f"interval '2 {m.group(2)}'", modified_query)

            # 3. Handle parameterized INTERVAL expressions (INTERVAL $1)
            param_interval_pattern = re.compile(r"interval\s+\$(\d+)", re.IGNORECASE)
            modified_query = param_interval_pattern.sub("interval '2 days'", modified_query)

            # 4. Handle OFFSET clauses - similar to LIMIT
            offset_pattern = re.compile(r"offset\s+\$(\d+)", re.IGNORECASE)
            modified_query = offset_pattern.sub(r"offset 0", modified_query)

            # Find all remaining parameter placeholders
            param_matches = list(re.finditer(r"\$\d+", modified_query))
            if not param_matches:
                return modified_query

            # Then, handle BETWEEN clauses as special cases
            between_pattern = re.compile(r"(\w+(?:\.\w+)?)\s+between\s+\$(\d+)\s+and\s+\$(\d+)", re.IGNORECASE)
            for match in between_pattern.finditer(query):
                column_ref, param1, param2 = match.groups()
                # Extract table and column name from the reference
                if "." in column_ref:
                    parts = column_ref.split(".")
                    alias = parts[0]
                    col_name = parts[1]
                    # Resolve the table alias
                    table_columns = self.extract_columns(query, column_cache=column_cache)
                    table_name = None
                    for tbl in table_columns:
                        if any(alias == a for a in self._get_table_aliases(query, tbl)):
                            table_name = tbl
                            break
                else:
                    # No alias, try to find the column in any table
                    col_name = column_ref
                    table_columns = self.extract_columns(query, column_cache=column_cache)
                    table_name = None
                    for tbl, cols in table_columns.items():
                        if col_name in cols:
                            table_name = tbl
                            break

                # Default numeric bounds if statistics not available
                lower_bound = 10
                upper_bound = 100
                if table_name and col_name:
                    stats = await self._get_column_statistics(table_name, col_name)
                    if stats:
                        # Get appropriate values for both bounds
                        lower_bound = self._get_bound_values(stats, is_lower=True)
                        upper_bound = self._get_bound_values(stats, is_lower=False)

                # Replace both parameters in the BETWEEN clause
                param1_pattern = r"\$" + param1
                param2_pattern = r"\$" + param2
                modified_query = re.sub(param1_pattern, str(lower_bound), modified_query)
                modified_query = re.sub(param2_pattern, str(upper_bound), modified_query)

            # Now handle remaining parameters normally
            # Recompute matches after BETWEEN replacements
            param_matches = list(re.finditer(r"\$\d+", modified_query))
            if not param_matches:
                return modified_query

            table_columns = self.extract_columns(query, column_cache=column_cache)
            if not table_columns:
                return self._replace_parameters_generic(modified_query)

            # Process each remaining parameter
            for match in reversed(param_matches):
                param_position = match.start()

                # Extract a narrower context
                clause_start = max(
                    modified_query.rfind(" where ", 0, param_position),
                    modified_query.rfind(" and ", 0, param_position),
                    modified_query.rfind(" or ", 0, param_position),
                    modified_query.rfind(",", 0, param_position),
                    modified_query.rfind("(", 0, param_position),
                    -1,
                )

                if clause_start == -1:
                    clause_start = max(0, param_position - 100)

                preceding_text = modified_query[clause_start : param_position + 2]

                # Try to identify which column this parameter belongs to
                column_info = self._identify_parameter_column(preceding_text, table_columns)
                if column_info:
                    table_name, column_name = column_info
                    stats = await self._get_column_statistics(table_name, column_name)
                    if stats:
                        replacement = self._get_replacement_value(stats, preceding_text)
                    else:
                        replacement = self._get_generic_replacement(preceding_text)
                else:
                    replacement = self._get_generic_replacement(preceding_text)

                modified_query = modified_query[: match.start()] + replacement + modified_query[match.end() :]

        except Exception as e:
            raise ValueError(_REPLACE_PARAMETERS_ERROR) from e
        else:
            return modified_query

    def _get_bound_values(self, stats: dict[str, Any], *, is_lower: bool = True) -> Any:  # noqa: C901, PLR0911, ANN401
        """Get appropriate bound values for range queries based on column statistics.

        Args:
            stats: Column statistics from pg_stats
            is_lower: True if we want the lower bound, False for upper bound

        Returns:
            Appropriate tight bound value based on available statistics
        """
        data_type = stats.get("data_type", "").lower()

        # First check for most common values - these are statistically most relevant
        common_vals = stats.get("common_vals")
        common_freqs = stats.get("common_freqs")

        if common_vals and common_freqs and len(common_vals) == len(common_freqs) and len(common_vals) > 0:
            # Use the most common value if available
            common_vals_list = list(common_vals)  # make sure it's a list
            common_freqs_list = list(common_freqs)  # make sure it's a list
            # Find the most frequent value
            max_freq_idx = common_freqs_list.index(max(common_freqs_list))
            most_common = common_vals_list[max_freq_idx]

            # For tight bounds, use the most common value with small adjustment
            try:
                if isinstance(most_common, float):
                    # Small +/- adjustment around most common value
                    adjustment = abs(most_common) * 0.05 if most_common != 0 else 1
                    return most_common - adjustment if is_lower else most_common + adjustment
                if isinstance(most_common, int):
                    # Small +/- adjustment around most common value
                    adjustment = abs(most_common) * 0.05 if most_common != 0 else 1
                    return int(most_common - adjustment) if is_lower else int(most_common + adjustment)
                if isinstance(most_common, str) and most_common.isdigit():
                    # For string digits, convert and adjust
                    num_val = float(most_common)
                    adjustment = abs(num_val) * 0.05 if num_val != 0 else 1
                    return str(int(num_val - adjustment)) if is_lower else str(int(num_val + adjustment))
            except (TypeError, ValueError):
                logger.warning("Error adapting most common value: %s", most_common)
                # If adaptation fails, just use the value
                return most_common
            else:
                return most_common

        # Next, try histogram bounds focusing on central values
        histogram_bounds = stats.get("histogram_bounds")
        if histogram_bounds and len(histogram_bounds) >= _MIN_HISTOGRAM_BOUNDS:
            # For tight bounds, use values very close to median
            median_idx = len(histogram_bounds) // 2
            # Only move 10% away from median in either direction for tight bounds
            idx_offset = max(1, len(histogram_bounds) // 10)

            if is_lower:
                bound_idx = max(0, median_idx - idx_offset)
            else:
                bound_idx = min(len(histogram_bounds) - 1, median_idx + idx_offset)

            return histogram_bounds[bound_idx]

        # Fall back to standard statistics if available
        most_common = stats.get("most_common_vals", [None])[0] if stats.get("most_common_vals") else None
        if most_common is not None:
            return most_common

        # Use very conservative defaults as last resort
        if "int" in data_type or data_type in ["smallint", "integer", "bigint"]:
            return 10 if is_lower else 20  # Very tight range
        if data_type in ["numeric", "decimal", "real", "double precision", "float"]:
            return 10.0 if is_lower else 20.0  # Very tight range
        if "date" in data_type or "time" in data_type:
            return "'2023-01-01'" if is_lower else "'2023-01-31'"  # Just one month
        if data_type == "boolean":
            return "true"  # Same value for both bounds for boolean
        # Default string-like behavior - narrow range
        return "'m'" if is_lower else "'n'"  # Just two adjacent letters

    def _get_table_aliases(self, query: str, table_name: str) -> list[str]:
        """Extract table aliases for a given table using SQL parser.

        Args:
            query: The SQL query to parse
            table_name: The name of the table to find aliases for

        Returns:
            List of aliases (including the table name itself)
        """
        try:
            # Parse the query
            parsed = parse_sql(query)
            if not parsed:
                return [table_name]  # Return just the table name if parsing fails

            # Get the statement tree
            stmt = parsed[0].stmt

            # Use TableAliasVisitor to extract aliases
            alias_visitor = TableAliasVisitor()
            alias_visitor(stmt)

            # Find all aliases for this table
            aliases = [table_name]  # Always include the table name itself

            for alias, table in alias_visitor.aliases.items():
                if table.lower() == table_name.lower():
                    aliases.append(alias)

        except Exception:
            logger.exception("Error extracting table aliases")
            return [table_name]  # Fallback to just the table name
        else:
            return aliases

    def _identify_parameter_column(self, context: str, table_columns: dict[str, set[str]]) -> tuple[str, str] | None:
        """Identify which column a parameter likely belongs to based on context."""
        # Look for patterns like "column_name = $1" or "column_name IN ($1)"
        for table, columns in table_columns.items():
            for column in columns:
                # Various patterns to match column references
                patterns = [
                    rf"{column}\s*=\s*\$\d+",  # column = $1
                    rf"{column}\s+in\s+\([^)]*\$\d+[^)]*\)",  # column in (...$1...)
                    rf"{column}\s+like\s+\$\d+",  # column like $1
                    rf"{column}\s*>\s*\$\d+",  # column > $1
                    rf"{column}\s*<\s*\$\d+",  # column < $1
                    rf"{column}\s*>=\s*\$\d+",  # column >= $1
                    rf"{column}\s*<=\s*\$\d+",  # column <= $1
                    rf"{column}\s+between\s+\$\d+\s+and\s+\$\d+",  # column between $1 and $2
                ]

                for pattern in patterns:
                    if re.search(pattern, context, re.IGNORECASE):
                        return (table, column)

        return None

    async def _get_column_statistics(self, table_name: str, column_name: str) -> dict[str, Any] | None:
        """Get statistics for a column from pg_stats."""
        # Create a cache key from table and column name
        cache_key = f"{table_name}.{column_name}"

        # Check if we already have this in cache
        if cache_key in self._column_stats_cache:
            return self._column_stats_cache[cache_key]

        # Not in cache, query the database
        try:
            query = """
            SELECT
                data_type,
                most_common_vals as common_vals,
                most_common_freqs as common_freqs,
                histogram_bounds,
                null_frac,
                n_distinct,
                correlation
            FROM pg_stats
            JOIN information_schema.columns
                ON pg_stats.tablename = information_schema.columns.table_name
                AND pg_stats.attname = information_schema.columns.column_name
            WHERE pg_stats.tablename = {}
            AND pg_stats.attname = {}
            """

            result = await SafeSqlDriver.execute_param_query(
                self.sql_driver,
                query,
                [table_name, column_name],
            )
            if not result or not result[0]:
                self._column_stats_cache[cache_key] = None
                return None

            stats = dict(result[0].cells)

            # Convert PostgreSQL arrays to Python lists for easier handling
            for key in ["common_vals", "common_freqs", "histogram_bounds"]:
                if key in stats and stats[key] is not None and isinstance(stats[key], str):
                    # Parse array literals like '{val1,val2}' into Python lists
                    array_str = stats[key].strip("{}")
                    if array_str:
                        stats[key] = [self._parse_pg_array_value(val) for val in array_str.split(",")]
                    else:
                        stats[key] = []

            # Cache the processed results
            self._column_stats_cache[cache_key] = stats
        except Exception as e:
            logger.warning("Error getting column statistics for %s.%s: %s", table_name, column_name, e)
            self._column_stats_cache[cache_key] = None
            return None
        else:
            return stats

    def _parse_pg_array_value(self, value: str) -> Any:  # noqa: ANN401
        """Parse a single value from a PostgreSQL array representation."""
        value = value.strip()

        # Try to convert to appropriate type
        if value == "null":
            return None
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]  # Strip quotes for string values

        # Try numeric conversion
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            # Return as string if not a number
            return value

    def _get_replacement_value(self, stats: dict[str, Any], context: str) -> str:  # noqa: C901, PLR0911
        """Generate an appropriate replacement value based on column statistics."""
        data_type = stats.get("data_type", "").lower()
        common_vals = stats.get("common_vals")
        histogram_bounds = stats.get("histogram_bounds")

        # If we have common values, use the most common one for equality,
        # or a value in the middle of the range for range queries

        # Detect query operator context
        is_equality = "=" in context and "!=" not in context and "<>" not in context
        is_range = any(op in context for op in [">", "<", ">=", "<=", "between"])
        is_like = "like" in context

        # For string types
        if "char" in data_type or data_type == "text":
            if is_like:
                return "'%test%'"
            if common_vals and is_equality:
                # Use the most common value for equality
                sample = common_vals[0]
                return f"'{sample}'"
            if common_vals:
                # Use any sample value
                sample = common_vals[0]
                return f"'{sample}'"
            # Default string
            return "'sample_value'"

        # For numeric types
        if "int" in data_type or data_type in [
            "numeric",
            "decimal",
            "real",
            "double",
        ]:
            if histogram_bounds and is_range:
                # For range queries, use a value in the middle
                bounds = histogram_bounds
                if isinstance(bounds, list) and len(bounds) > 1:
                    middle_idx = len(bounds) // 2
                    value = bounds[middle_idx]
                    return str(value)
            elif common_vals and is_equality:
                # Use most common value for equality
                return str(common_vals[0])
            elif histogram_bounds:
                # Use a reasonable value from histogram
                bounds = histogram_bounds
                if isinstance(bounds, list) and len(bounds) > 0:
                    return str(bounds[0])

            # Default numeric values by type
            if "int" in data_type:
                return "41"
            return "41.5"

        # For date/time types
        if "date" in data_type or "time" in data_type:
            if is_range:
                return "'2023-01-15'"  # Middle of the month
            return "'2023-01-01'"

        # For boolean
        if data_type == "boolean":
            return "true"

        # Default fallback
        return "'sample_value'"

    def _get_generic_replacement(self, context: str) -> str:
        """Provide a generic replacement when we can't determine the specific column type."""
        context = context.lower()

        # Try to guess based on context
        if any(date_word in context.split() for date_word in ["date", "timestamp", "time"]):
            return "'2023-01-01'"

        if any(word in context for word in ["id", "key", "code", "num"]):
            return "43"

        if "like" in context:
            return "'%sample%'"

        if any(word in context for word in ["amount", "price", "cost", "fee"]):
            return "99.99"

        # If in comparison context, use a number
        if any(op in context for op in ["=", ">", "<", ">=", "<="]):
            return "44"

        # Default to string
        return "'sample_value'"

    def _replace_parameters_generic(self, query: str) -> str:
        """Fallback generic parameter replacement when catalog lookup fails."""
        try:
            modified_query = query

            # Replace string parameters
            modified_query = re.sub(r"like \$\d+", "like '%'", modified_query)

            # Context-aware replacements
            modified_query = re.sub(
                r"(\w+)\s*=\s*\$\d+",
                lambda m: self._context_replace(m, "="),
                modified_query,
            )
            modified_query = re.sub(
                r"(\w+)\s*<\s*\$\d+",
                lambda m: self._context_replace(m, "<"),
                modified_query,
            )
            modified_query = re.sub(
                r"(\w+)\s*>\s*\$\d+",
                lambda m: self._context_replace(m, ">"),
                modified_query,
            )

            # Replace numeric parameters in inequalities
            modified_query = re.sub(r"(\d+) and \$\d+", r"\1 and 100", modified_query)
            modified_query = re.sub(r"\$\d+ and (\d+)", r"1 and \1", modified_query)
            modified_query = re.sub(r">\s*\$\d+", "> 1", modified_query)
            modified_query = re.sub(r"<\s*\$\d+", "< 100", modified_query)
            modified_query = re.sub(r"=\s*\$\d+\b", "= 45", modified_query)

            # For any remaining parameters, use a generic replacement
            modified_query = re.sub(r"\$\d+", "'sample_value'", modified_query)

        except Exception:
            logger.exception("Error in generic parameter replacement")
            return query
        else:
            return modified_query

    def _context_replace(self, match: re.Match[str], op: str) -> str:
        """Replace parameters based on column name context.

        Args:
            match: The regex match object.
            op: The operator to use.

        Returns:
            The replacement string.
        """
        col_name = match.group(1).lower()

        # ID-like columns (numeric)
        if col_name.endswith(("id", "_id")) or col_name == "id":
            return f"{col_name} {op} 46"

        # Date/time columns
        if any(word in col_name for word in ["date", "time", "created", "updated"]):
            return f"{col_name} {op} '2023-01-01'"

        # Numeric-looking columns
        if any(word in col_name for word in ["amount", "price", "cost", "count", "num", "qty"]):
            return f"{col_name} {op} 46.5"

        # Status-like columns (likely string enums)
        if "status" in col_name or "type" in col_name or "state" in col_name:
            return f"{col_name} {op} 'active'"

        # Default to string for other columns
        return f"{col_name} {op} 'sample_value'"

    def extract_columns(self, query: str, column_cache: dict[str, set[str]] | None = None) -> dict[str, set[str]]:
        """Extract columns from a query using improved visitors.

        Args:
            query: SQL query string.
            column_cache: Optional cache of table -> set of column names.
                If provided, used to verify column existence. If None, falls back to
                permissive behavior (returns True for all checks).
        """
        try:
            parsed = parse_sql(query)
            if not parsed:
                return {}
            stmt = parsed[0].stmt
            if not isinstance(stmt, SelectStmt):
                return {}

            return self.extract_stmt_columns(stmt, column_cache=column_cache)

        except Exception:
            logger.warning("Error extracting columns from query: %s", query)
            return {}

    async def build_column_cache(self, tables: set[str], schema: str = "public") -> dict[str, set[str]]:
        """Build a cache of table -> set of column names from the database.

        Args:
            tables: Set of table names to cache columns for.
            schema: Schema name (default: 'public').

        Returns:
            Dictionary mapping table names (lowercase) to sets of column names (lowercase).
        """
        if not tables:
            return {}

        column_cache: dict[str, set[str]] = {}

        # Build query to get all columns for the tables
        tables_list = list(tables)

        query = """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = {}
            AND table_name = ANY({})
            ORDER BY table_name, ordinal_position
        """

        try:
            result = await SafeSqlDriver.execute_param_query(self.sql_driver, query, [schema, tables_list])
            if result:
                for row in result:
                    table_name = row.cells["table_name"].lower()
                    column_name = row.cells["column_name"].lower()
                    if table_name not in column_cache:
                        column_cache[table_name] = set()
                    column_cache[table_name].add(column_name)
        except Exception as e:
            logger.warning("Error building column cache: %s. Continuing without cache.", e)
            return {}

        return column_cache

    def extract_stmt_columns(
        self, stmt: SelectStmt, column_cache: dict[str, set[str]] | None = None
    ) -> dict[str, set[str]]:
        """Extract columns from a query using improved visitors.

        Args:
            stmt: The SelectStmt AST node to extract columns from.
            column_cache: Optional cache of table -> set of column names.
                If provided, used to verify column existence. If None, falls back to
                permissive behavior (returns True for all checks).
        """
        try:
            # Second pass: collect columns with table context
            collector = ColumnCollector(self.sql_driver, column_cache=column_cache)
            collector(stmt)

        except Exception:
            logger.warning("Error extracting columns from query: %s", stmt)
            return {}
        else:
            return collector.columns
