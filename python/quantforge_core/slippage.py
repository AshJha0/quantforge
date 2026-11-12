"""Hedge slippage: implementation shortfall against the cost model
(specifications/08-hedging/hedge-slippage.md, rulings I-36 to I-38)."""
import math
from collections.abc import Sequence
from typing import Any

from .errors import QfError
from .finite import guard

Fill = tuple[float, float]  # (quantity, price)
Order = tuple[float, float, float, float, float, Sequence[Fill]]
# (quantity, decision_price, final_price, half_spread, impact, fills)
TOTALS = ("execution_cost", "opportunity_cost", "shortfall", "model_cost", "slippage")


def slippage_report(orders: Sequence[Order]) -> dict[str, Any]:
    """`hedge.slippage.report`: per order, the filled size and average price, execution and
    opportunity cost against the decision price, their sum (the shortfall), the wave 4a model
    cost on the filled size, and the slippage over that model (I-36, I-37); plus the totals.
    Positive costs are costs for buys and sells alike."""
    if not orders:
        raise QfError("E_INPUT", "no orders", "orders")
    for quantity, _, _, _, _, fills in orders:
        if quantity == 0:
            raise QfError("E_INPUT", "an order quantity is 0", "quantity")
        if any(q == 0 or (q > 0) != (quantity > 0) for q, _ in fills):
            raise QfError("E_INPUT", "a fill is 0 or of the other sign", "fills")
        if abs(math.fsum(q for q, _ in fills)) > abs(quantity):
            raise QfError("E_INPUT", "the fills add up to more than the order", "fills")
    for _, decision, final, spread, impact, fills in orders:
        if decision <= 0 or final <= 0 or any(p <= 0 for _, p in fills):
            raise QfError("E_DOMAIN", "prices must be positive", "price")
        if spread < 0 or impact < 0:
            raise QfError("E_DOMAIN", "half_spread and impact must not be negative", "impact")

    rows: list[dict[str, Any]] = []
    sums: dict[str, list[float]] = {k: [] for k in TOTALS}
    for quantity, decision, final, spread, impact, fills in orders:
        filled = math.fsum(q for q, _ in fills)
        execution = math.fsum(q * (p - decision) for q, p in fills)
        opportunity = (quantity - filled) * (final - decision)
        model = spread * abs(filled) + impact * filled * filled
        rows.append({
            "filled_quantity": filled + 0.0,
            "average_price": math.fsum(q * p for q, p in fills) / filled if fills else None,
            "execution_cost": execution + 0.0, "opportunity_cost": opportunity + 0.0,
            "shortfall": execution + opportunity + 0.0, "model_cost": model + 0.0,
            "slippage": execution - model + 0.0})
        for k in TOTALS:
            sums[k].append(rows[-1][k])
    total = {k: math.fsum(v) + 0.0 for k, v in sums.items()}
    return {"orders": rows, "total": total}


guard(globals())
