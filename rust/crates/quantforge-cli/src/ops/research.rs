//! `research.*` operations (stage J wave 1): read the inputs, call the library, shape the outputs.
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::{Result, fail};
use quantforge_core::json::{Json, obj};
use quantforge_core::portfolio_opt as po;
use quantforge_core::research::{self, Costs, Engine, Metric};

super::registry! {
(op, i)
        "research.backtest.run" => backtest(i),
        "research.cv.purged_kfold" => {
            let (t0, t1) = (i.reals("t0")?, i.reals("t1")?);
            let (k, e) = (i.int("n_splits")?, i.f64_or("embargo_pct", 0.0)?);
            i.gate()?;
            let (folds, h) = research::purged_kfold(&t0, &t1, k, e)?;
            let ints = |v: Vec<usize>| Json::from(v.into_iter().map(|x| x as i64).collect::<Vec<_>>());
            let folds: Vec<Json> = folds
                .into_iter()
                .map(|f| obj([("test", ints(f.test)), ("train", ints(f.train))]))
                .collect();
            plain(obj([("folds", folds.into()), ("embargo_count", (h as i64).into())]))
        },
        "research.cv.cpcv_paths" => {
            let (n, k) = (i.int("n_groups")?, i.int("n_test_groups")?);
            i.gate()?;
            let (s, p) = research::cpcv_paths(n, k)?;
            plain(obj([("n_splits", s.into()), ("n_paths", p.into())]))
        },
        "research.regime.viterbi" => viterbi(i),
        "research.regime.baum_welch" => baum_welch(i),
        "research.portfolio.mean_variance" => {
            let (mu, s) = (i.reals("expected_returns")?, i.matrix("covariance")?);
            let g = i.f64("risk_aversion")?;
            let read = |k: &str| i.opt(k).map(|_| i.reals(k)).transpose();
            let (lo, hi) = (read("lower")?, read("upper")?);
            i.gate()?;
            let r = po::mean_variance(&mu, &s, g, lo.as_deref(), hi.as_deref())?;
            plain(obj([
                ("weights", r.weights.into()),
                ("expected_return", r.expected_return.into()),
                ("volatility", r.volatility.into()),
                ("objective", r.objective.into()),
                ("at_bound", r.at_bound.into()),
            ]))
        },
        "research.portfolio.risk_parity" => {
            let s = i.matrix("covariance")?;
            let b = i.opt("budgets").map(|_| i.reals("budgets")).transpose()?;
            i.gate()?;
            let (w, v, c) = po::risk_parity(&s, b.as_deref())?;
            plain(obj([("weights", w.into()), ("volatility", v.into()), ("contributions", c.into())]))
        },
        "research.estimate.ledoit_wolf" => {
            let x = i.matrix("returns")?;
            i.gate()?;
            let (c, d, m) = po::ledoit_wolf(&x)?;
            plain(obj([("covariance", c.into()), ("shrinkage", d.into()), ("mu", m.into())]))
        },
        "research.estimate.black_litterman" => {
            let (s, pi) = (i.matrix("covariance")?, i.reals("prior_returns")?);
            let (p, q) = (i.matrix("pick")?, i.reals("views")?);
            let (om, tau) = (i.matrix("view_covariance")?, i.f64("tau")?);
            i.gate()?;
            let (m, pc, pr) = po::black_litterman(&s, &pi, &p, &q, &om, tau)?;
            plain(obj([
                ("posterior_returns", m.into()),
                ("posterior_covariance", pc.into()),
                ("predictive_covariance", pr.into()),
            ]))
        },
        "research.stats.psr" => {
            let (sr, n) = (i.f64("sr")?, i.int("n_obs")?);
            let (s, k, b) = (i.f64_or("skew", 0.0)?, i.f64_or("kurtosis", 3.0)?, i.f64_or("sr_benchmark", 0.0)?);
            let (z, p) = research::psr(sr, n, s, k, b)?;
            plain(obj([("z", z.into()), ("psr", p.into())]))
        },
        "research.stats.dsr" => {
            let (sr, n) = (i.f64("sr")?, i.int("n_obs")?);
            let (s, k) = (i.f64_or("skew", 0.0)?, i.f64_or("kurtosis", 3.0)?);
            let (nt, v) = (i.int("n_trials")?, i.f64("sr_variance")?);
            let (sr0, z, d) = research::dsr(sr, n, s, k, nt, v)?;
            plain(obj([("sr0", sr0.into()), ("z", z.into()), ("dsr", d.into())]))
        },
        "research.stats.power" => {
            let y = i.f64("years")?;
            let (a, p) = (i.f64_or("alpha", 0.05)?, i.f64_or("power", 0.8)?);
            let r = research::power(y, a, p, i.opt_f64("sr_target")?)?;
            let mut out = vec![
                ("z_sum".to_string(), r.z_sum.into()),
                ("mds".to_string(), r.mds.into()),
                ("se_at_zero".to_string(), r.se_at_zero.into()),
            ];
            if let Some((yr, se)) = r.target {
                out.push(("years_required".to_string(), yr.into()));
                out.push(("se_at_target".to_string(), se.into()));
            }
            plain(Json::Obj(out))
        },
        "research.stats.pbo" => {
            let perf = i.matrix("performance")?;
            let s = i.int("n_partitions")?;
            let m = match i.opt("metric").map(|_| i.str("metric")).transpose()? {
                None | Some("SHARPE") => Metric::Sharpe,
                Some("MEAN") => Metric::Mean,
                Some(_) => return i.fail("metric", "expected SHARPE or MEAN"),
            };
            i.gate()?;
            let (p, l) = research::pbo(&perf, s, m)?;
            let n = l.len() as i64;
            plain(obj([("pbo", p.into()), ("logits", l.into()), ("n_combinations", n.into())]))
        },
}

fn backtest(i: &Inputs) -> Result<Outcome> {
    let (p, q) = (i.reals("prices")?, i.reals("targets")?);
    let lag = i.int_or("lag", 1)?;
    let c = Costs {
        half_spread_bps: i.f64_or("half_spread_bps", 0.0)?,
        commission_per_unit: i.f64_or("commission_per_unit", 0.0)?,
        fixed_per_trade: i.f64_or("fixed_per_trade", 0.0)?,
        multiplier: i.f64_or("multiplier", 1.0)?,
    };
    let engine = match i.opt("engine").map(|_| i.str("engine")).transpose()? {
        None | Some("EVENT") => Engine::Event,
        Some("VECTOR") => Engine::Vector,
        Some(_) => return i.fail("engine", "expected EVENT or VECTOR"),
    };
    i.gate()?;
    let r = research::backtest(&p, &q, lag, c, engine)?;
    plain(obj([
        ("positions", r.positions.into()),
        ("trades", r.trades.into()),
        ("pnl_gross", r.pnl_gross.into()),
        ("cost", r.cost.into()),
        ("pnl_net", r.pnl_net.into()),
        ("equity", r.equity.into()),
        ("total_gross", r.total_gross.into()),
        ("total_spread_cost", r.total_spread_cost.into()),
        ("total_commission", r.total_commission.into()),
        ("total_fixed_cost", r.total_fixed_cost.into()),
        ("total_net", r.total_net.into()),
        ("turnover", r.turnover.into()),
        ("trade_count", r.trade_count.into()),
        ("max_drawdown", r.max_drawdown.into()),
    ]))
}

fn viterbi(i: &Inputs) -> Result<Outcome> {
    let init = i.reals("initial")?;
    let a = i.matrix("transition")?;
    let e = i
        .opt("emission")
        .map(|_| i.matrix("emission"))
        .transpose()?;
    let read = |k: &str| i.opt(k).map(|_| i.reals(k)).transpose();
    let (y, m, s) = (read("observations")?, read("means")?, read("sds")?);
    i.gate()?;
    let gauss = match (&y, &m, &s) {
        (None, None, None) => None,
        (Some(y), Some(m), Some(s)) => Some((y.as_slice(), m.as_slice(), s.as_slice())),
        _ => return fail("E_INPUT", "observations, means and sds go together"),
    };
    let (states, lp) = research::regime_viterbi(&init, &a, e.as_deref(), gauss)?;
    let states: Vec<i64> = states.into_iter().map(|x| x as i64).collect();
    plain(obj([
        ("states", states.into()),
        ("log_probability", lp.into()),
    ]))
}

fn baum_welch(i: &Inputs) -> Result<Outcome> {
    let y = i.reals("observations")?;
    let start = po::Hmm {
        initial: i.reals("initial")?,
        transition: i.matrix("transition")?,
        means: i.reals("means")?,
        sds: i.reals("sds")?,
    };
    let tol = i.f64_or("tolerance", 1e-10)?;
    let max = i.int_or("max_iterations", 1000)?;
    i.gate()?;
    let r = po::baum_welch(&y, start, tol, max)?;
    plain(obj([
        ("initial", r.params.initial.into()),
        ("transition", r.params.transition.into()),
        ("means", r.params.means.into()),
        ("sds", r.params.sds.into()),
        ("log_likelihood", r.log_likelihood.into()),
        ("iterations", r.iterations.into()),
        ("converged", r.converged.into()),
    ]))
}
