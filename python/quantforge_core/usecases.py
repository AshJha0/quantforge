"""Use cases 1 and 2 (specifications/04-pricing/use-cases.md): only the sums are new here."""
from collections.abc import Sequence
from datetime import date
from typing import cast

from . import curves, fx, hedging, ois, sensitivities
from .errors import QfError
from .numeric import ordered_sum
from .ois import OisTrade, Quote


def fx_hedge(
    market: fx.FxMarket, book: Sequence[fx.FxForward], half_spread: float
) -> dict[str, float]:
    if half_spread < 0:
        raise QfError("E_DOMAIN", "half_spread must not be negative", "half_spread")
    legs = [fx.forward_pv(market, trade) for trade in book]
    delta = ordered_sum(d for _, d in legs)
    hedge = -delta
    return {
        "pv": ordered_sum(cast(float, v["pv"]) for v, _ in legs),
        "fx_delta": delta,
        "hedge_spot_base": hedge,
        "residual_delta": 0.0,
        "hedge_cost": abs(hedge) * half_spread,
    }


def rates_hedge(
    as_of: date, quotes: Sequence[Quote], interpolation: str, trade: OisTrade,
    hedge_tenors: Sequence[str], hedge_unit_notional: float, half_spread_bp: float,
) -> dict[str, object]:
    if half_spread_bp < 0:
        raise QfError("E_DOMAIN", "half_spread_bp must not be negative", "half_spread_bp")
    data, _ = ois.bootstrap(trade.convention, as_of, quotes, interpolation)
    curve = curves.build(data)
    pv = ois.trade_pv(trade, ois.periods(trade.convention, as_of, trade.tenor), curve)[0]
    bumped = sensitivities.bump_curves(trade.convention, as_of, quotes, interpolation)
    dv01, key_rate = sensitivities.dv01_on(trade, as_of, bumped)

    columns = []
    for tenor in hedge_tenors:
        ps = ois.periods(trade.convention, as_of, tenor)
        par = ois.par_rate(trade.convention, ps, curve)
        hedge = OisTrade(trade.convention, tenor, par, hedge_unit_notional, "PAY")
        columns.append(sensitivities.dv01_on(hedge, as_of, bumped)[1])
    n = len(columns)
    matrix = [[column[i] for column in columns] for i in range(len(key_rate))]
    units, residual, _ = hedging.solve(
        matrix, key_rate, [1.0] * len(key_rate), [0.0] * n, 0.0
    )
    cost = ordered_sum(
        abs(x) * abs(ordered_sum(c)) * half_spread_bp
        for x, c in zip(units, columns, strict=True)
    )
    return {
        "pv": pv, "dv01": dv01, "key_rate": key_rate, "hedge_units": units,
        "residual_key_rate": residual, "hedge_cost": cost,
    }
