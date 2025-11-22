from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IndexDefinition:
    """Immutable index configuration for hashing."""

    table: str
    columns: tuple[str, ...]
    using: str = "btree"

    def to_dict(self) -> dict[str, Any]:
        """Convert index definition to dictionary.

        Returns:
            Dictionary representation of the index definition.
        """
        return {
            "table": self.table,
            "columns": list(self.columns),
            "using": self.using,
            "definition": self.definition,
        }

    @property
    def definition(self) -> str:
        """Get SQL CREATE INDEX statement for this index.

        Returns:
            SQL CREATE INDEX statement string.
        """
        return f"CREATE INDEX {self.name} ON {self.table} USING {self.using} ({', '.join(self.columns)})"

    @property
    def name(self) -> str:
        """Generate index name from table, columns, and index method.

        Returns:
            Generated index name string.
        """
        # Clean column names for use in index naming
        # Replace special characters with underscores to avoid issues with
        # functional expressions
        cleaned_columns = []
        for col in self.columns:
            # Replace parentheses and other special characters with underscores
            # This ensures expressions like LOWER(column_name) work in
            # index names
            cleaned_col = col.replace("(", "_").replace(")", "_").replace(" ", "_").replace(",", "_")
            # Remove consecutive underscores
            while "__" in cleaned_col:
                cleaned_col = cleaned_col.replace("__", "_")
            # Remove trailing underscores
            cleaned_col = cleaned_col.rstrip("_")
            cleaned_columns.append(cleaned_col)

        column_part = "_".join(cleaned_columns)
        suffix = "" if self.using == "btree" else f"_{self.using}"
        base = f"crystaldba_idx_{self.table}_{column_part}_{len(self.columns)}"
        return f"{base}{suffix}"

    def __str__(self) -> str:
        return self.definition

    def __repr__(self) -> str:
        return f"IndexConfig(table='{self.table}', columns={self.columns}, using='{self.using}')"
