//! Input limits (`limits.md`). Read tolerantly, as a mistyped input is `E_SCHEMA`, which outranks
//! `E_LIMIT` and is found later, by the typed reads.
use quantforge_core::error::{QfError, err};
use quantforge_core::json::Json;

const MAX_ARRAY: usize = 100_000;
const MAX_MATRIX_ROWS: usize = 200;
const MAX_VALUE_DEPTH: usize = 64;

fn too_long(v: &Json) -> bool {
    match v {
        Json::Arr(a) => a.len() > MAX_ARRAY || a.iter().any(too_long),
        Json::Obj(o) => o.iter().any(|(_, x)| too_long(x)),
        _ => false,
    }
}

fn int(inputs: &Json, k: &str) -> Option<i128> {
    inputs.get(k).and_then(Json::as_int).map(i128::from)
}

fn len(inputs: &Json, k: &str) -> Option<i128> {
    inputs
        .get(k)
        .and_then(Json::as_array)
        .map(|a| a.len() as i128)
}

fn above(inputs: &Json, k: &str, max: i128) -> bool {
    int(inputs, k).is_some_and(|v| v > max)
}

/// A product of two sizes, where a value below 1 is left to the rule checks.
fn product_above(a: Option<i128>, b: Option<i128>, max: i128) -> bool {
    matches!((a, b), (Some(x), Some(y)) if x >= 1 && y >= 1 && x * y > max)
}

fn operation_above(op: &str, i: &Json) -> bool {
    let draws = i128::from(10_000_000);
    match op {
        "core.integrate.trapezoid" | "core.integrate.simpson" => above(i, "n", 10_000_000),
        "core.integrate.adaptive_simpson" => above(i, "max_depth", 60),
        "core.integrate.gauss_kronrod" => above(i, "max_intervals", 10_000),
        "core.root.bisection" | "core.root.brent" | "core.root.newton" => {
            above(i, "max_iter", 100_000)
        }
        "core.rng.next_u64" | "core.rng.uniforms" | "core.rng.normals" => {
            above(i, "count", 100_000) || above(i, "skip", draws)
        }
        "core.rng.set_state_next_u64" => above(i, "count", 100_000),
        "core.sobol.points" => {
            product_above(int(i, "count"), int(i, "dimensions"), 100_000) || above(i, "skip", draws)
        }
        "core.mc.gbm_european" => {
            let steps = if i.get("steps").is_none_or(|v| *v == Json::Null) {
                Some(1)
            } else {
                int(i, "steps")
            };
            product_above(int(i, "paths"), steps, 1_000_000)
        }
        "core.pde.bs_european" => {
            product_above(int(i, "space_steps"), int(i, "time_steps"), 10_000_000)
        }
        "core.cos.european" => above(i, "terms", 100_000),
        "vol.svi.surface_check" => {
            len(i, "slices").is_some_and(|n| n > 100)
                || len(i, "log_moneyness").is_some_and(|n| n > 10_000)
        }
        "vol.slv.leverage" => {
            let g = |k: &str| {
                i.get("grid")
                    .and_then(|g| g.get(k))
                    .and_then(Json::as_int)
                    .map(i128::from)
            };
            g("nx").is_some_and(|n| n > 1000)
                || g("nv").is_some_and(|n| n > 1000)
                || g("nt").is_some_and(|n| n > 10_000)
        }
        "exotic.american.crr" => above(i, "steps", 20_000),
        "exotic.american.fd" => {
            let g = |k: &str| {
                i.get("grid")
                    .and_then(|g| g.get(k))
                    .and_then(Json::as_int)
                    .map(i128::from)
            };
            g("nx").is_some_and(|n| n > 1001) || g("nt").is_some_and(|n| n > 10_000)
        }
        "vol.volofvol.measure" => len(i, "vols").is_some_and(|n| n > 10_000),
        "vol.local.dupire" => {
            len(i, "slices").is_some_and(|n| n > 100)
                || len(i, "points").is_some_and(|n| n > 10_000)
        }
        "core.calendar.add_business_days" => int(i, "days").is_some_and(|d| d.abs() > 30_000),
        "core.ts.rolling" => above(i, "window", 1_000),
        "core.ts.autocorrelation" | "core.ts.ljung_box" => above(i, "max_lag", 1_000),
        "rates.schedule.generate" => above(i, "payment_lag", 30_000),
        "usecase.rates_hedge" => len(i, "hedge_tenors").is_some_and(|n| n > 20),
        "calib.fit" => len(i, "start").is_some_and(|n| n > 20) || above(i, "max_iter", 100_000),
        "hedge.solve" => i
            .get("a")
            .and_then(Json::as_array)
            .and_then(|rows| rows.first())
            .and_then(Json::as_array)
            .is_some_and(|r| r.len() > 20),
        "core.store.replay" => {
            len(i, "checkpoints").is_some_and(|n| n > 1_000)
                || product_above(len(i, "records"), len(i, "checkpoints"), 10_000_000)
        }
        _ => false,
    }
}

fn curve_points_above(i: &Json) -> bool {
    let pillars = |k: &str| {
        i.get(k)
            .is_some_and(|c| len(c, "pillars").is_some_and(|n| n > 100))
    };
    [
        "curve",
        "discount",
        "projection",
        "base_curve",
        "quote_curve",
        "projection_a",
        "projection_b",
    ]
    .iter()
    .any(|k| pillars(k))
        || ["quotes", "ois_quotes", "term_quotes"]
            .iter()
            .any(|k| len(i, k).is_some_and(|n| n > 100))
        || len(i, "points").is_some_and(|n| n > 100)
}

fn matrix_above(op: &str, i: &Json) -> bool {
    op.starts_with("core.linalg.") && len(i, "a").is_some_and(|n| n > MAX_MATRIX_ROWS as i128)
}

fn value_too_deep(op: &str, i: &Json) -> bool {
    op.starts_with("core.store.")
        && i.get("records").and_then(Json::as_array).is_some_and(|rs| {
            rs.iter().any(|r| match r {
                Json::Obj(keys) => keys.iter().any(|(_, v)| v.depth() > MAX_VALUE_DEPTH),
                _ => false,
            })
        })
}

/// Stage C: 100 for any quote, strike, point, dividend or position list, and per surface grid
/// (ruling C10); 20,000 cells or steps.
fn stage_c_above(op: &str, i: &Json) -> bool {
    if !(op.starts_with("eq.")
        || op.starts_with("vol.")
        || op.starts_with("exotic.")
        || op.starts_with("risk.vol.")
        || op == "usecase.vol_surface")
    {
        return false;
    }
    let long = |v: &Json, k: &str| len(v, k).is_some_and(|n| n > 100);
    let lists = [
        "dividends",
        "quotes",
        "strikes",
        "vols",
        "weights",
        "points",
        "positions",
        "thetas",
        "log_moneyness",
        "total_variance",
        "slices",
        "k_grid",
        "expiry_years",
        "u",
        "fixing_years",
        "forwards",
        "correlation",
    ];
    // Stated stage E limits win over C10 (ruling E-A35); they are checked in `operation_above`.
    let stated: &[&str] = match op {
        "vol.svi.surface_check" => &["log_moneyness"],
        "vol.local.dupire" => &["points"],
        "vol.volofvol.measure" => &["vols"],
        _ => &[],
    };
    let surface = i
        .get("surface")
        .is_some_and(|s| long(s, "expiry_years") || long(s, "log_moneyness"));
    let slices = i
        .get("slices")
        .and_then(Json::as_array)
        .is_some_and(|a| a.iter().any(|s| long(s, "quotes")));
    let curves = ["funding_curve", "borrow_curve"]
        .iter()
        .any(|k| i.get(k).is_some_and(|c| long(c, "pillars")));
    lists
        .iter()
        .filter(|k| !stated.contains(k))
        .any(|k| long(i, k))
        || surface
        || slices
        || curves
        || above(i, "cells", 20_000)
        || above(i, "steps", 20_000)
}

/// Stage F lists whose stated limit (ruling F-42) is above the generic 100,000.
fn stage_f_raised(op: &str) -> &'static [&'static str] {
    match op {
        "risk.var.historical" => &["pnl"],
        "risk.var.filtered_historical" => &["returns"],
        "risk.backtest.christoffersen" => &["exceptions"],
        "book.lifecycle.apply" => &["events"],
        _ => &[],
    }
}

/// The generic array rule, with the F-42 raised lists judged at 1,000,000 instead.
fn too_long_stage_f(op: &str, i: &Json) -> bool {
    let raised = stage_f_raised(op);
    let Json::Obj(keys) = i else {
        return too_long(i);
    };
    keys.iter().any(|(k, v)| {
        if raised.contains(&k.as_str()) {
            return match v {
                Json::Arr(a) => a.len() > 1_000_000 || a.iter().any(too_long),
                _ => false,
            };
        }
        if op == "book.marks.resolve" && k == "sources" {
            return match v {
                Json::Arr(a) => {
                    a.len() > MAX_ARRAY
                        || a.iter().any(|src| match src {
                            Json::Obj(f) => f.iter().any(|(n, q)| match q {
                                Json::Arr(qs) if n == "quotes" => {
                                    qs.len() > 1_000_000 || qs.iter().any(too_long)
                                }
                                _ => too_long(q),
                            }),
                            _ => false,
                        })
                }
                _ => too_long(v),
            };
        }
        too_long(v)
    })
}

/// Ruling F-42: stated sizes of the stage F operations.
fn stage_f_above(op: &str, i: &Json) -> bool {
    let over = |k: &str, n: i128| len(i, k).is_some_and(|m| m > n);
    let first_row = |k: &str| {
        i.get(k)
            .and_then(Json::as_array)
            .and_then(|a| a.first())
            .and_then(Json::as_array)
            .map(|r| r.len() as i128)
    };
    match op {
        "risk.book.ois_sensitivity" => over("swaps", 10_000),
        "risk.curve.pca" => {
            over("changes", 100_000) || first_row("changes").is_some_and(|n| n > 200)
        }
        "risk.curve.cross_gamma" => i
            .get("curve")
            .is_some_and(|c| len(c, "pillars").is_some_and(|n| n > 100)),
        "risk.var.monte_carlo" => above(i, "paths", 10_000_000) || over("mean", 100),
        "risk.frtb.girr_delta" => over("sensitivities", 100_000),
        "book.lifecycle.apply" => over("positions", 100_000),
        "book.marks.resolve" => over("instruments", 100_000),
        "usecase.factor_attribution" => {
            over("portfolio_returns", 100_000) || over("factor_names", 50)
        }
        _ => false,
    }
}

/// Ruling I-4: stated sizes of the stage I wave 1 operations.
fn stage_i_above(op: &str, i: &Json) -> bool {
    let over = |k: &str, n: i128| len(i, k).is_some_and(|m| m > n);
    let columns_over = |n: i128| {
        i.get("a")
            .and_then(Json::as_array)
            .and_then(|a| a.first())
            .and_then(Json::as_array)
            .is_some_and(|r| r.len() as i128 > n)
    };
    match op {
        "hedge.qp.solve" => over("a", 1_000) || columns_over(200) || over("eq_matrix", 200),
        "hedge.integer.solve" => over("a", 1_000) || columns_over(12),
        "hedge.residual.report" => over("a", 1_000) || columns_over(200),
        "hedge.minvar.ratio" => over("covariance", 201) || over("hedge_changes", 200),
        "hedge.greeks.neutralise" => over("portfolio", 1_000) || over("hedges", 3),
        // Ruling I-19.
        "hedge.credit.cds" => over("book", 1_000) || over("hedges", 50),
        "hedge.correlation.neutralise" => over("book", 1_000) || over("hedges", 5),
        // Ruling I-23.
        "hedge.crossasset.solve" => {
            over("book", 1_000)
                || over("hedges", 200)
                || i.get("curve")
                    .is_some_and(|c| len(c, "times").is_some_and(|n| n > 100))
        }
        _ => false,
    }
}

/// The `E_LIMIT` this case breaks, if any.
pub fn check(op: &str, inputs: &Json) -> Option<QfError> {
    (too_long_stage_f(op, inputs)
        || stage_f_above(op, inputs)
        || stage_i_above(op, inputs)
        || matrix_above(op, inputs)
        || curve_points_above(inputs)
        || value_too_deep(op, inputs)
        || operation_above(op, inputs)
        || stage_c_above(op, inputs))
    .then(|| err("E_LIMIT", "an input is above its limit"))
}
