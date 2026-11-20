"""FRTB correlation scenarios shared by the sensitivities-based method (MAR21.6).

The capital charge is computed three times, with every correlation scaled up ("high"), kept ("medium") or scaled
down ("low"), and the largest of the three is taken. var_risk.py (GIRR delta) and frtb.py (the other risk classes)
both use this module (K-9 review finding 19: frtb.py used private names of var_risk.py).
"""

from .finite import guard

SCENARIOS = ("high", "medium", "low")


def scale_correlation(x: float, scenario: str) -> float:
    """MAR21.6: high min(1.25 x, 1); low max(2 x - 1, 0.75 x); medium x."""
    if scenario == "high":
        return min(1.25 * x, 1.0)
    if scenario == "low":
        return max(2 * x - 1, 0.75 * x)
    return x


guard(globals())
