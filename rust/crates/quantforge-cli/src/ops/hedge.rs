//! `hedge.*` operations: read the inputs, call the library, shape the outputs.
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::Result;
use quantforge_core::error::err;
use quantforge_core::hedge;
use quantforge_core::hedge_solvers::{
    self as hs, Greek, IntegerProblem, Leg, LegKind, MinVarInput, QpProblem, Singular,
};
use quantforge_core::json::{Json, obj};

/// An optional key. `null` means "absent" only inside the bound lists (ruling I-12); the key
/// itself set to `null` is `E_SCHEMA`.
fn present<'a>(i: &Inputs<'a>, k: &str) -> Result<Option<&'a Json>> {
    match i.0.get(k) {
        None => Ok(None),
        Some(Json::Null) => i.fail(k, "must not be null"),
        Some(v) => Ok(Some(v)),
    }
}

fn opt_matrix(i: &Inputs, k: &str) -> Result<Option<Vec<Vec<f64>>>> {
    present(i, k)?.map(|_| i.matrix(k)).transpose()
}

fn opt_reals(i: &Inputs, k: &str) -> Result<Option<Vec<f64>>> {
    present(i, k)?.map(|_| i.reals(k)).transpose()
}

fn opt_bounds(i: &Inputs, k: &str) -> Result<Option<Vec<Option<f64>>>> {
    present(i, k)?.map(|_| i.nullable_reals(k)).transpose()
}

fn opt_lot_bounds(i: &Inputs, k: &str) -> Result<Option<Vec<Option<i64>>>> {
    let Some(v) = present(i, k)? else {
        return Ok(None);
    };
    let Some(items) = v.as_array() else {
        return i.fail(k, "expected an array");
    };
    items
        .iter()
        .map(|v| match v {
            Json::Null => Ok(None),
            _ => v
                .as_int()
                .map_or_else(|| i.fail(k, "expected integers or null"), |n| Ok(Some(n))),
        })
        .collect::<Result<Vec<_>>>()
        .map(Some)
}

fn opt_str<'a>(i: &Inputs<'a>, k: &str) -> Result<Option<&'a str>> {
    present(i, k)?.map(|_| i.str(k)).transpose()
}

fn ridge(i: &Inputs) -> Result<f64> {
    present(i, "ridge")?.map_or(Ok(0.0), |_| i.f64("ridge"))
}

/// A position (`with_quantity`) or a hedge instrument. Key presence is checked by the library.
fn leg(i: &Inputs, k: &str, v: &Json, with_quantity: bool) -> Result<(Leg, f64)> {
    let kind = match v.get("instrument").and_then(Json::as_str) {
        Some("CALL") => LegKind::Call,
        Some("PUT") => LegKind::Put,
        Some("UNDERLYING") => LegKind::Underlying,
        _ => return i.fail(k, "instrument must be CALL, PUT or UNDERLYING"),
    };
    let number = |name: &str| -> Result<Option<f64>> {
        match v.get(name) {
            None => Ok(None),
            Some(x) => x
                .as_f64()
                .map_or_else(|| i.fail(k, "expected a number"), |n| Ok(Some(n))),
        }
    };
    let quantity = if with_quantity {
        number("quantity")?.map_or_else(|| i.fail(k, "quantity is required"), Ok)?
    } else {
        0.0
    };
    let (strike, expiry) = (number("strike")?, number("expiry_years")?);
    Ok((
        Leg {
            kind,
            strike,
            expiry,
        },
        quantity,
    ))
}

fn greeks_obj(g: [f64; 3]) -> Json {
    obj([
        ("delta", g[0].into()),
        ("gamma", g[1].into()),
        ("vega", g[2].into()),
    ])
}

super::registry! {
(op, i)
        "hedge.solve" => {
            let (a, b) = (i.matrix("a")?, i.reals("b")?);
            let (w, c, l) = (i.reals("weights")?, i.reals("costs")?, i.f64("lambda")?);
            i.gate()?;
            let h = hedge::solve_hedge(&a, &b, &w, &c, l)?;
            plain(obj([
                ("x", h.x.into()),
                ("residual", h.residual.into()),
                ("objective", h.objective.into()),
            ]))
        },
        "hedge.spread_cost" => {
            let (q, h) = (i.reals("quantities")?, i.reals("half_spreads")?);
            i.gate()?;
            plain(obj([("cost", hedge::spread_cost(&q, &h)?.into())]))
        },
        "hedge.qp.solve" => {
            let (a, b, w) = (i.matrix("a")?, i.reals("b")?, i.reals("weights")?);
            let ridge = ridge(i)?;
            let (e, r) = (opt_matrix(i, "eq_matrix")?, opt_reals(i, "eq_rhs")?);
            let (lo, hi) = (opt_bounds(i, "lower")?, opt_bounds(i, "upper")?);
            let singular = match opt_str(i, "singular")? {
                None | Some("ERROR") => Singular::Error,
                Some("MIN_NORM") => Singular::MinNorm,
                Some(_) => return i.fail("singular", "must be ERROR or MIN_NORM"),
            };
            i.gate()?;
            let s = hs::qp_solve(&QpProblem {
                a: &a,
                b: &b,
                weights: &w,
                ridge,
                eq_matrix: e.as_ref(),
                eq_rhs: r.as_deref(),
                lower: lo.as_deref(),
                upper: hi.as_deref(),
                singular,
            })?;
            plain(obj([
                ("x", s.x.into()),
                ("residual", s.residual.into()),
                ("objective", s.objective.into()),
                ("rank", Json::Int(i64::try_from(s.rank).unwrap_or(i64::MAX))),
            ]))
        },
        "hedge.integer.solve" => {
            let (a, b, w) = (i.matrix("a")?, i.reals("b")?, i.reals("weights")?);
            let (ridge, lots) = (ridge(i)?, i.reals("lot_sizes")?);
            let lo = opt_lot_bounds(i, "lower_lots")?;
            let hi = opt_lot_bounds(i, "upper_lots")?;
            i.gate()?;
            let s = hs::integer_solve(&IntegerProblem {
                a: &a,
                b: &b,
                weights: &w,
                ridge,
                lot_sizes: &lots,
                lower_lots: lo.as_deref(),
                upper_lots: hi.as_deref(),
            })?;
            plain(obj([
                ("lots", Json::Arr(s.lots.into_iter().map(Json::Int).collect())),
                ("x", s.x.into()),
                ("residual", s.residual.into()),
                ("objective", s.objective.into()),
                ("continuous_objective", s.continuous_objective.into()),
                ("rounding_cost", s.rounding_cost.into()),
            ]))
        },
        "hedge.minvar.ratio" => {
            let cov = opt_matrix(i, "covariance")?;
            let e = opt_reals(i, "exposure_changes")?;
            let h = opt_matrix(i, "hedge_changes")?;
            i.gate()?;
            let input = match (&cov, &e, &h) {
                (Some(c), None, None) => MinVarInput::Covariance(c),
                (None, Some(e), Some(h)) => MinVarInput::Series(e, h),
                _ => return Err(err("E_INPUT", "give either covariance or both series")),
            };
            let r = hs::minvar_ratio(input)?;
            plain(obj([
                ("hedge", r.hedge.into()),
                ("variance_before", r.variance_before.into()),
                ("variance_after", r.variance_after.into()),
                ("effectiveness", r.effectiveness.into()),
            ]))
        },
        "hedge.greeks.neutralise" => {
            let market = hs::GreekMarket {
                spot: i.f64("spot")?,
                rate: i.f64("rate")?,
                dividend_yield: i.f64("dividend_yield")?,
                volatility: i.f64("volatility")?,
            };
            let portfolio = i
                .array("portfolio")?
                .iter()
                .map(|v| leg(i, "portfolio", v, true))
                .collect::<Result<Vec<_>>>()?;
            let hedges = i
                .array("hedges")?
                .iter()
                .map(|v| leg(i, "hedges", v, false).map(|l| l.0))
                .collect::<Result<Vec<_>>>()?;
            let targets = i
                .array("targets")?
                .iter()
                .map(|t| match t.as_str() {
                    Some("DELTA") => Ok(Greek::Delta),
                    Some("GAMMA") => Ok(Greek::Gamma),
                    Some("VEGA") => Ok(Greek::Vega),
                    _ => i.fail("targets", "must be DELTA, GAMMA or VEGA"),
                })
                .collect::<Result<Vec<_>>>()?;
            i.gate()?;
            let r = hs::greeks_neutralise(&market, &portfolio, &hedges, &targets)?;
            plain(obj([
                ("quantities", r.quantities.into()),
                ("greeks_before", greeks_obj(r.before)),
                ("greeks_after", greeks_obj(r.after)),
            ]))
        },
        "hedge.beta.futures" => {
            let (v, beta) = (i.f64("portfolio_value")?, i.f64("portfolio_beta")?);
            let target = i.f64("target_beta")?;
            let (f, m) = (i.f64("futures_price")?, i.f64("multiplier")?);
            let round = match opt_str(i, "rounding")? {
                None | Some("NEAREST") => true,
                Some("NONE") => false,
                Some(_) => return i.fail("rounding", "must be NEAREST or NONE"),
            };
            i.gate()?;
            let r = hs::beta_futures(v, beta, target, f, m, round)?;
            plain(obj([
                ("contracts", r.contracts.into()),
                ("contracts_held", r.contracts_held.into()),
                ("beta_after", r.beta_after.into()),
            ]))
        },
        "hedge.residual.report" => {
            let (a, b, x) = (i.matrix("a")?, i.reals("b")?, i.reals("x")?);
            let s = i.matrix("covariance")?;
            i.gate()?;
            let r = hs::residual_report(&a, &b, &x, &s)?;
            plain(obj([
                ("residual", r.residual.into()),
                ("variance_before", r.variance_before.into()),
                ("variance_after", r.variance_after.into()),
                ("volatility_after", r.volatility_after.into()),
                ("effectiveness", r.effectiveness.into()),
                ("contributions", r.contributions.into()),
            ]))
        }
}
