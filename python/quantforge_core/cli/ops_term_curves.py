"""Stage J curves lane verbs (rulings J-C-1 to J-C-9): financing term structure and liquidity curve."""

from typing import Any

from .inputs import Inputs
from .registry import core, op


def _curve(i: Inputs) -> Any:
    return core.term_curves.build_financing_curve(
        i.reals("funding_times"),
        i.reals("funding_zero_rates"),
        i.reals("quote_times"),
        i.reals("repo_rates"),
        i.reals("borrow_times"),
        i.reals("borrow_fees"),
    )


@op("repo.term.curve")
def repo_term_curve(i: Inputs) -> Any:
    q = i.reals("query_times")
    return core.term_curves.term_curve(_curve(i), q)


@op("eq.forward.term_financed")
def eq_forward_term_financed(i: Inputs) -> Any:
    spot, mat = i.real("spot"), i.real("maturity_years")
    dt, da = i.reals("dividend_times"), i.reals("dividend_amounts")
    return core.term_curves.forward_term_financed(_curve(i), spot, mat, dt, da)


@op("liq.curve.cost")
def liq_curve_cost(i: Inputs) -> Any:
    return core.term_curves.liquidity_cost(
        i.real("half_spread_bps"),
        i.real("daily_volume"),
        i.real("daily_vol"),
        i.opt_real("coefficient", 1.0),
        i.opt_real("exponent", 0.5),
        i.opt_real("risk_multiplier", 0.0),
        i.reals("sizes"),
        i.reals("horizons_days"),
    )
