"""Common utilities and types."""

from .errors import ErrorResult
from .utils import INFINITE_IMPROVEMENT_MULTIPLIER, calculate_improvement_multiple


__all__ = [
    "INFINITE_IMPROVEMENT_MULTIPLIER",
    "ErrorResult",
    "calculate_improvement_multiple",
]
