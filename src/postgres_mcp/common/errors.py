"""Error result classes."""

from __future__ import annotations


class ErrorResult:
    """Simple error result class."""

    def __init__(self, message: str) -> None:
        """Initialize error result.

        Args:
            message: Error message text.
        """
        self.value = message

    def to_text(self) -> str:
        """Convert error result to text representation.

        Returns:
            Error message text.
        """
        return self.value
