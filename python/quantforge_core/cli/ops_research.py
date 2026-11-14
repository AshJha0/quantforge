"""Stage J wave 1 research verbs (specifications/11-research/, rulings J-1 to J-19)."""
from typing import Any

from .inputs import Inputs
from .registry import core, op

_ENGINES = ("EVENT", "VECTOR")
_METRICS = ("SHARPE", "MEAN")


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
