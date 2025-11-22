"""Common utility functions."""

from __future__ import annotations


# If the recommendation cost is 0.0, we can't calculate the improvement multiple.
# Return 1000000.0 to indicate infinite improvement.
INFINITE_IMPROVEMENT_MULTIPLIER = 1000000.0


def calculate_improvement_multiple(base_cost: float, rec_cost: float) -> float:
    """Calculate the improvement multiple from this recommendation.

    Args:
        base_cost: Base execution cost.
        rec_cost: Recommended execution cost.

    Returns:
        Improvement multiple (base_cost / rec_cost).
    """
    if base_cost <= 0.0:
        # base_cost or rec_cost might be zero, but as they are floats, the might be
        # represented as -0.0. That's why we compare to <= 0.0.
        return 1.0
    if rec_cost <= 0.0:
        # If the recommendation cost is 0.0, we can't calculate the improvement multiple.
        # Return INFINITE_IMPROVEMENT_MULTIPLIER to indicate infinite improvement.
        return INFINITE_IMPROVEMENT_MULTIPLIER
    return base_cost / rec_cost
