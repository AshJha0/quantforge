"""Handlers for stage G waves 3b to 4b (LMM, AAD ladder, model reserve, xVA framework) and the
stage F carry-over tools landed in stage G (F3, F4, FRTB FX and equity). A handler reads every
input first; the first call through `core` ends the E_SCHEMA stage."""
from typing import Any

from ..errors import QfError
from .inputs import Inputs
from .registry import core, op


def _schema(key: str, why: str) -> QfError:
    return QfError("E_SCHEMA", f"{key}: {why}", key)


def _items(i: Inputs, key: str) -> list[Inputs]:
    out = []
    for k, item in enumerate(i.array(key)):
        if not isinstance(item, dict):
            raise _schema(f"{key}/{k}", "not an object")
        out.append(Inputs(item, f"{key}/{k}."))
    return out


def _real_map(i: Inputs, key: str) -> dict[str, float]:
    obj = i.object(key)
    return {name: obj.real(name) for name in obj.raw}


def _curve(i: Inputs) -> tuple[list[float], list[float]]:
    c = i.object("curve")
    return c.reals("times"), c.reals("discount_factors")


def _abcd(i: Inputs) -> tuple[float, float, float, float]:
    v = i.object("abcd")
    return v.real("a"), v.real("b"), v.real("c"), v.real("d")


def _paths(i: Inputs, key: str) -> list[list[float]]:
    return i.matrix(key)


@op("rates.lmm.capfloor")
def _lmm_cap(i: Inputs) -> Any:
    times, dfs = _curve(i)
    args = (_abcd(i), i.reals("period_times"), i.real("strike"), i.string("cap_floor"),
            i.real("notional"))
    return core.lmm.capfloor(times, dfs, *args)


@op("rates.lmm.swaption_rebonato")
def _lmm_swaption(i: Inputs) -> Any:
    times, dfs = _curve(i)
    args = (_abcd(i), i.real("correlation_beta"), i.real("expiry_years"), i.reals("payment_times"),
            i.real("fixed_rate"), i.string("side"), i.real("notional"))
    return core.lmm.swaption_rebonato(times, dfs, *args)


@op("rates.shortrate.bermudan_ladder")
def _ladder(i: Inputs) -> Any:
    times, dfs = _curve(i)
    g = i.object("grid")
    args = (times, dfs, i.real("mean_reversion"), i.real("sigma"), i.has("short_rate"),
            i.real("start_years"), i.reals("payment_times"), i.real("fixed_rate"),
            i.string("swaption_type"), i.real("notional"), i.reals("exercise_times"),
            g.integer("nx"), g.integer("steps_per_year"), g.real("width"))
    return core.aad_ladder.bermudan_ladder(*args)


@op("risk.model_reserve.dispersion")
def _reserve(i: Inputs) -> Any:
    return core.xva.dispersion(_real_map(i, "prices"), i.string("reference_model"))


@op("xva.exposure.collateralised")
def _collateralised(i: Inputs) -> Any:
    times = i.reals("times")
    trades = [(t.string("netting_set"), _paths(t, "values")) for t in _items(i, "trades")]
    csa = {}
    if i.has("csa"):
        obj = i.object("csa")
        for name in obj.raw:
            c = obj.object(name)
            csa[name] = (c.real("threshold_receive"), c.real("threshold_post"),
                         c.real("minimum_transfer_amount"), c.integer("mpor_steps"),
                         c.opt_real("independent_amount", 0.0))
    q = i.real("pfe_quantile")
    built = {name: core.xva.Csa(*args) for name, args in csa.items()}
    return core.xva.collateralised(times, trades, built, q)


def _name(i: Inputs, key: str) -> tuple[float, float]:
    n = i.object(key)
    return n.real("hazard_rate"), n.real("recovery")


@op("xva.adjustments.value")
def _adjustments(i: Inputs) -> Any:
    f = i.object("funding")
    args = (i.reals("times"), i.reals("discount_factors"), i.reals("ee"), i.reals("ene"),
            _name(i, "counterparty"), _name(i, "own"), f.real("borrow_spread"),
            f.real("lend_spread"), f.boolean("exclude_dva_overlap"),
            i.reals("im") if i.has("im") else None, i.opt_real("im_spread"),
            i.reals("capital") if i.has("capital") else None, i.opt_real("hurdle_rate"))
    cp, own = args[4], args[5]
    return core.xva.adjustments(*args[:4], core.xva.Name(*cp), core.xva.Name(*own), *args[6:])


@op("xva.simm.ir_delta")
def _simm(i: Inputs) -> Any:
    return core.xva.simm_ir_delta(i.reals("sensitivities"), i.reals("risk_weights"),
                                  i.matrix("correlations"), i.real("concentration_threshold"))


@op("xva.wwr.cva_hw")
def _wwr(i: Inputs) -> Any:
    return core.xva.wwr_cva(i.reals("times"), _paths(i, "values"), i.reals("discount_factors"),
                            i.real("hazard_rate"), i.real("recovery"), i.real("wwr_b"))


# --- stage F carry-over -------------------------------------------------------------------------


@op("risk.stress.reverse")
def _reverse(i: Inputs) -> Any:
    return core.risk_tools.reverse_stress(i.reals("direction"), i.reals("delta"),
                                          i.matrix("gamma"), i.real("target_loss"))


@op("risk.limits.check")
def _limits(i: Inputs) -> Any:
    measures = _real_map(i, "measures")
    obj = i.object("limits")
    limits = {}
    for name in obj.raw:
        lim = obj.object(name)
        limits[name] = (lim.real("soft"), lim.real("hard"))
    return core.risk_tools.limits_check(measures, limits)


@op("risk.concentration.measures")
def _concentration(i: Inputs) -> Any:
    return core.risk_tools.concentration(i.reals("exposures"), i.integer("top_n"))


@op("risk.var.liquidity_adjusted")
def _lvar(i: Inputs) -> Any:
    return core.risk_tools.liquidity_adjusted(i.real("var"), i.real("z"),
                                              i.reals("position_values"), i.reals("spread_mean"),
                                              i.reals("spread_vol"))


@op("risk.vol.horizon")
def _horizon(i: Inputs) -> Any:
    return core.risk_tools.vol_horizon(i.real("daily_vol"), i.real("ar1"),
                                       i.integer("horizon_days"))


@op("risk.sens.inflation01")
def _inflation01(i: Inputs) -> Any:
    return core.risk_tools.inflation01(i.real("notional"), i.integer("years"),
                                       i.real("fixed_rate"), i.real("market_rate"),
                                       i.real("discount_factor"))


@op("risk.sens.dividend_borrow")
def _dividend_borrow(i: Inputs) -> Any:
    return core.risk_tools.dividend_borrow(i.real("spot"), i.real("strike"), i.real("expiry_years"),
                                           i.real("rate"), i.real("dividend_yield"),
                                           i.real("borrow_rate"), i.real("vol"),
                                           i.string("option_type"))


@op("risk.sens.correlation")
def _correlation(i: Inputs) -> Any:
    return core.risk_tools.correlation01(i.real("spot1"), i.real("spot2"), i.real("quantity1"),
                                         i.real("quantity2"), i.real("yield1"), i.real("yield2"),
                                         i.real("vol1"), i.real("vol2"), i.real("correlation"),
                                         i.real("expiry_years"))


@op("risk.frtb.fx_delta")
def _fx_delta(i: Inputs) -> Any:
    rows = [(s.string("pair"), s.real("sensitivity")) for s in _items(i, "sensitivities")]
    listed = [str(p) for p in i.array("specified_pairs")] if i.has("specified_pairs") else []
    return core.frtb.fx_delta(rows, listed)


@op("risk.frtb.equity_delta")
def _equity_delta(i: Inputs) -> Any:
    rows = [(s.string("issuer"), s.integer("bucket"), s.string("kind"), s.real("sensitivity"))
            for s in _items(i, "sensitivities")]
    return core.frtb.equity_delta(rows)


@op("risk.frtb.csr_delta")
def _csr_delta(i: Inputs) -> Any:
    rows = [(s.string("issuer"), s.integer("bucket"), s.string("tenor"), s.string("curve"),
             s.real("sensitivity")) for s in _items(i, "sensitivities")]
    return core.frtb.csr_delta(rows)


@op("risk.frtb.commodity_delta")
def _commodity_delta(i: Inputs) -> Any:
    rows = [(s.string("commodity"), s.integer("bucket"), s.string("tenor"), s.string("location"),
             s.real("sensitivity")) for s in _items(i, "sensitivities")]
    return core.frtb.commodity_delta(rows)


def _bucket(s: Inputs) -> object:
    value = s.raw.get("bucket")
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise _schema("bucket", "not an integer or a string")
    return value


@op("risk.frtb.vega")
def _vega(i: Inputs) -> Any:
    rows = [(_bucket(s), s.opt_string("name"), s.real("option_maturity"),
             s.opt_real("underlying_maturity"), s.real("vega")) for s in _items(i, "sensitivities")]
    return core.frtb.vega(i.string("risk_class"), rows)


@op("risk.frtb.curvature")
def _curvature(i: Inputs) -> Any:
    rows = [(_bucket(s), s.opt_string("name"), s.real("cvr_up"), s.real("cvr_down"))
            for s in _items(i, "factors")]
    given = i.has("fx_scalar")
    scalar = i.boolean("fx_scalar") if given else False
    return core.frtb.curvature(i.string("risk_class"), rows, scalar or (
        given and i.string("risk_class") != "FX"))


@op("xva.exposure.portfolio_hw")
def _portfolio_hw(i: Inputs) -> Any:
    times, dfs = _curve(i)
    trades = [(t.real("notional"), t.real("fixed_rate"), t.string("side"), t.real("start_years"),
               t.reals("payment_times")) for t in _items(i, "trades")]
    return core.portfolio_exposure.portfolio_hw(
        times, dfs, i.real("mean_reversion"), i.real("sigma"), trades, i.reals("exposure_times"),
        i.reals("pfe_quantiles"), i.real("hazard_rate"), i.real("recovery"))
