"""Stage J research verbs (waves 1 to 3) (specifications/11-research/, rulings J-1 to J-19)."""
from typing import Any

from .inputs import Inputs
from .registry import core, op

_ENGINES = ("EVENT", "VECTOR")
_METRICS = ("SHARPE", "MEAN")
_LOO = ("linear", "log_linear", "cubic_natural", "monotone_pchip")
_SURFACE = ("linear", "cubic_natural", "monotone_pchip")


@op("research.backtest.run")
def research_backtest_run(i: Inputs) -> Any:
    engine = i.enum("engine", _ENGINES) if i.has("engine") else "EVENT"
    return core.research.backtest_run(
        i.reals("prices"), i.reals("targets"), i.opt_integer("lag", 1),
        i.opt_real("half_spread_bps", 0.0), i.opt_real("commission_per_unit", 0.0),
        i.opt_real("fixed_per_trade", 0.0), i.opt_real("multiplier", 1.0), engine)


@op("research.cv.purged_kfold")
def research_cv_purged_kfold(i: Inputs) -> Any:
    return core.research.cv_purged_kfold(i.reals("t0"), i.reals("t1"), i.integer("n_splits"),
                                         i.opt_real("embargo_pct", 0.0))


@op("research.cv.cpcv_paths")
def research_cv_cpcv_paths(i: Inputs) -> Any:
    return core.research.cv_cpcv_paths(i.integer("n_groups"), i.integer("n_test_groups"))


@op("research.regime.viterbi")
def research_regime_viterbi(i: Inputs) -> Any:
    def maybe_reals(key: str) -> list[float] | None:
        return i.reals(key) if i.has(key) else None

    return core.research.regime_viterbi(
        i.reals("initial"), i.matrix("transition"),
        i.matrix("emission") if i.has("emission") else None,
        maybe_reals("observations"), maybe_reals("means"), maybe_reals("sds"))


@op("research.stats.psr")
def research_stats_psr(i: Inputs) -> Any:
    return core.research.stats_psr(i.real("sr"), i.integer("n_obs"), i.opt_real("skew", 0.0),
                                   i.opt_real("kurtosis", 3.0), i.opt_real("sr_benchmark", 0.0))


@op("research.stats.dsr")
def research_stats_dsr(i: Inputs) -> Any:
    return core.research.stats_dsr(i.real("sr"), i.integer("n_obs"), i.integer("n_trials"),
                                   i.real("sr_variance"), i.opt_real("skew", 0.0),
                                   i.opt_real("kurtosis", 3.0))


@op("research.stats.power")
def research_stats_power(i: Inputs) -> Any:
    return core.research.stats_power(i.real("years"), i.opt_real("alpha", 0.05),
                                     i.opt_real("power", 0.8), i.opt_real("sr_target"))


@op("research.stats.pbo")
def research_stats_pbo(i: Inputs) -> Any:
    metric = i.enum("metric", _METRICS) if i.has("metric") else "SHARPE"
    return core.research.stats_pbo(i.matrix("performance"), i.integer("n_partitions"), metric)


# --- Stage J wave 2 (rulings J-W2-1 to J-W2-15) --------------------------------------------------

def _opt_reals(i: Inputs, key: str) -> list[float] | None:
    return i.reals(key) if i.has(key) else None


@op("research.portfolio.mean_variance")
def research_portfolio_mean_variance(i: Inputs) -> Any:
    return core.research_w2.portfolio_mean_variance(
        i.reals("expected_returns"), i.matrix("covariance"), i.real("risk_aversion"),
        _opt_reals(i, "lower"), _opt_reals(i, "upper"))


@op("research.portfolio.risk_parity")
def research_portfolio_risk_parity(i: Inputs) -> Any:
    return core.research_w2.portfolio_risk_parity(i.matrix("covariance"),
                                                  _opt_reals(i, "budgets"))


@op("risk.contrib.euler")
def risk_contrib_euler(i: Inputs) -> Any:
    return core.research_w2.contrib_euler(i.reals("weights"), i.matrix("covariance"))


@op("research.estimate.ledoit_wolf")
def research_estimate_ledoit_wolf(i: Inputs) -> Any:
    return core.research_w2.estimate_ledoit_wolf(i.matrix("returns"))


@op("research.estimate.black_litterman")
def research_estimate_black_litterman(i: Inputs) -> Any:
    return core.research_w2.estimate_black_litterman(
        i.matrix("covariance"), i.reals("prior_returns"), i.matrix("pick"), i.reals("views"),
        i.matrix("view_covariance"), i.real("tau"))


@op("risk.backtest.es_z2")
def risk_backtest_es_z2(i: Inputs) -> Any:
    return core.research_w2.backtest_es_z2(i.reals("losses"), i.reals("var"), i.reals("es"),
                                           i.real("alpha"))


@op("research.regime.baum_welch")
def research_regime_baum_welch(i: Inputs) -> Any:
    return core.research_w2.regime_baum_welch(
        i.reals("observations"), i.reals("initial"), i.matrix("transition"), i.reals("means"),
        i.reals("sds"), i.opt_real("tolerance", 1e-10), i.opt_integer("max_iterations", 1000))


# --- Stage J wave 3 (rulings J-W3-1 to J-W3-14) ------------------------------------------------

@op("risk.scenario.historical_shock")
def risk_scenario_historical_shock(i: Inputs) -> Any:
    return core.research_w3.scenario_historical_shock(i.dates("dates"), i.reals("tenors"),
                                                      i.matrix("yields"), i.date("start_date"),
                                                      i.date("end_date"))


@op("risk.scenario.replay")
def risk_scenario_replay(i: Inputs) -> Any:
    return core.research_w3.scenario_replay(i.reals("base_tenors"), i.reals("base_yields"),
                                            i.reals("shock_tenors"), i.reals("shock_bp"),
                                            i.opt_real("scale", 1.0), _opt_reals(i, "dv01"))


@op("research.backtest.interp_loo")
def research_backtest_interp_loo(i: Inputs) -> Any:
    return core.research_w3.backtest_interp_loo(i.enum("method", _LOO), i.reals("x"),
                                                i.reals("y"))


@op("research.backtest.surface_holdout")
def research_backtest_surface_holdout(i: Inputs) -> Any:
    return core.research_w3.backtest_surface_holdout(
        i.enum("method", _SURFACE), i.reals("expiries"), i.reals("strikes"), i.matrix("vols"),
        i.integer_list("holdout"))


@op("research.drift.cusum")
def research_drift_cusum(i: Inputs) -> Any:
    return core.drift.cusum(i.reals("x"), i.real("k"), i.real("h"), i.opt_real("mu0", 0.0),
                            i.opt_real("sigma", 1.0), i.opt_boolean("reset", True))


@op("research.drift.page_hinkley")
def research_drift_page_hinkley(i: Inputs) -> Any:
    direction = i.enum("direction", ("up", "down", "both")) if i.has("direction") else "both"
    return core.drift.page_hinkley(i.reals("x"), i.real("delta"), i.real("lambda"), direction,
                                   i.opt_boolean("reset", True))


@op("research.drift.psi")
def research_drift_psi(i: Inputs) -> Any:
    return core.drift.psi(i.reals("reference"), i.reals("test"), i.opt_integer("bins", 10),
                          i.opt_real("threshold", 0.25))


@op("research.drift.ks")
def research_drift_ks(i: Inputs) -> Any:
    return core.drift.ks(i.reals("a"), i.reals("b"), i.opt_real("level", 0.05))
