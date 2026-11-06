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
    ]
    .iter()
    .any(|k| pillars(k))
        || len(i, "quotes").is_some_and(|n| n > 100)
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

/// The `E_LIMIT` this case breaks, if any.
pub fn check(op: &str, inputs: &Json) -> Option<QfError> {
    (too_long(inputs)
        || matrix_above(op, inputs)
        || curve_points_above(inputs)
        || value_too_deep(op, inputs)
        || operation_above(op, inputs))
    .then(|| err("E_LIMIT", "an input is above its limit"))
}
