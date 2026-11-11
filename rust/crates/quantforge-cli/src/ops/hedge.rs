//! `hedge.*` operations: read the inputs, call the library, shape the outputs.
use super::credit::{credit_discount, hazard_input};
use super::eq::items;
use super::rates::curve_input;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::credit::{CdsTrade, Hazard};
use quantforge_core::error::Result;
use quantforge_core::error::err;
use quantforge_core::hedge;
use quantforge_core::hedge_cross::{
    self as hx, CorrKind, CorrLeg, CorrMarket, CorrTarget, CreditMarket, CreditRisk,
};
use quantforge_core::hedge_crossasset::{self as xa, XaKind, XaLeg, XaMarket, ZeroCurve};
use quantforge_core::hedge_dynamic::{self as hd, BacktestOption, BacktestSetup, Effectiveness};
use quantforge_core::hedge_solvers::{
    self as hs, Costs, Greek, IntegerProblem, Leg, LegKind, MinVarInput, QpProblem, Singular,
};
use quantforge_core::json::{Json, obj};

fn effectiveness_fields(e: &Effectiveness) -> [(&'static str, Json); 4] {
    [
        ("dollar_offset", e.dollar_offset.into()),
        ("regression_slope", e.regression_slope.into()),
        ("regression_r2", e.regression_r2.into()),
        ("variance_reduction", e.variance_reduction.into()),
    ]
}

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

fn opt_f64(i: &Inputs, k: &str) -> Result<Option<f64>> {
    present(i, k)?.map(|_| i.f64(k)).transpose()
}

/// The wave 4a cost lists, read before the gate.
struct CostLists {
    half_spreads: Option<Vec<f64>>,
    impact: Option<Vec<f64>>,
    margin_rates: Option<Vec<f64>>,
    margin_limit: Option<f64>,
}

impl CostLists {
    fn read(i: &Inputs) -> Result<CostLists> {
        Ok(CostLists {
            half_spreads: opt_reals(i, "half_spreads")?,
            impact: opt_reals(i, "impact")?,
            margin_rates: opt_reals(i, "margin_rates")?,
            margin_limit: opt_f64(i, "margin_limit")?,
        })
    }

    fn costs(&self, cost_weight: Option<f64>) -> Costs<'_> {
        Costs {
            half_spreads: self.half_spreads.as_deref(),
            impact: self.impact.as_deref(),
            cost_weight,
            margin_rates: self.margin_rates.as_deref(),
            margin_limit: self.margin_limit,
        }
    }
}

fn singular_policy(i: &Inputs) -> Result<Singular> {
    match opt_str(i, "singular")? {
        None | Some("ERROR") => Ok(Singular::Error),
        Some("MIN_NORM") => Ok(Singular::MinNorm),
        Some(_) => i.fail("singular", "must be ERROR or MIN_NORM"),
    }
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

/// An instrument with a fixed key set (waves 2 and 3): its kind, every other key as a number,
/// and the book `quantity`. The key set is checked by the library (`E_INPUT`); a non-number or
/// an unknown kind is `E_SCHEMA`. A book position without `quantity` gets a placeholder key so
/// that it fails the key-set check like any other missing key.
type Keyed<K> = (K, Vec<(String, f64)>, f64);

fn keyed<K>(
    i: &Inputs,
    k: &str,
    v: &Json,
    in_book: bool,
    kind_of: impl Fn(&str) -> Option<K>,
) -> Result<Keyed<K>> {
    let Json::Obj(keys) = v else {
        return i.fail(k, "expected objects");
    };
    let Some(kind) = v.get("instrument").and_then(Json::as_str).and_then(kind_of) else {
        return i.fail(k, "unknown instrument");
    };
    let mut fields = Vec::new();
    let mut quantity = None;
    for (name, x) in keys {
        if name == "instrument" {
            continue;
        }
        let Some(n) = x.as_f64() else {
            return i.fail(k, "expected a number");
        };
        if in_book && name == "quantity" {
            quantity = Some(n);
        } else {
            fields.push((name.clone(), n));
        }
    }
    if in_book && quantity.is_none() {
        fields.push(("quantity".to_string(), 1.0));
    }
    Ok((kind, fields, quantity.unwrap_or(0.0)))
}

fn corr_kind(s: &str) -> Option<CorrKind> {
    Some(match s {
        "EXCHANGE" => CorrKind::Exchange,
        "CALL_1" => CorrKind::Call1,
        "PUT_1" => CorrKind::Put1,
        "CALL_2" => CorrKind::Call2,
        "PUT_2" => CorrKind::Put2,
        "UNDERLYING_1" => CorrKind::Underlying1,
        "UNDERLYING_2" => CorrKind::Underlying2,
        _ => return None,
    })
}

fn corr_leg(i: &Inputs, k: &str, v: &Json, in_book: bool) -> Result<(CorrLeg, f64)> {
    let (kind, fields, q) = keyed(i, k, v, in_book, corr_kind)?;
    Ok((CorrLeg { kind, fields }, q))
}

fn xa_kind(s: &str) -> Option<XaKind> {
    Some(match s {
        "CALL" => XaKind::Call,
        "PUT" => XaKind::Put,
        "FORWARD" => XaKind::Forward,
        "ZCB" => XaKind::Zcb,
        "UNDERLYING" => XaKind::Underlying,
        _ => return None,
    })
}

fn xa_leg(i: &Inputs, k: &str, v: &Json, in_book: bool) -> Result<(XaLeg, f64)> {
    let (kind, fields, q) = keyed(i, k, v, in_book, xa_kind)?;
    Ok((XaLeg { kind, fields }, q))
}

fn corr_greeks(g: [f64; 5]) -> Json {
    obj([
        ("delta_1", g[0].into()),
        ("delta_2", g[1].into()),
        ("vega_1", g[2].into()),
        ("vega_2", g[3].into()),
        ("correlation01", g[4].into()),
    ])
}

fn credit_risk(r: &CreditRisk, with_pv: bool) -> Json {
    let (cs01, jtd, buckets) = (r.cs01.into(), r.jtd.into(), r.buckets.clone().into());
    if with_pv {
        obj([
            ("pv", r.pv.into()),
            ("cs01", cs01),
            ("jtd", jtd),
            ("buckets", buckets),
        ])
    } else {
        obj([("cs01", cs01), ("jtd", jtd), ("buckets", buckets)])
    }
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
            let singular = singular_policy(i)?;
            let lists = CostLists::read(i)?;
            let cost_weight = opt_f64(i, "cost_weight")?;
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
                costs: lists.costs(cost_weight),
            })?;
            let mut out = vec![
                ("x", s.x.into()),
                ("residual", s.residual.into()),
                ("objective", s.objective.into()),
                ("rank", Json::Int(i64::try_from(s.rank).unwrap_or(i64::MAX))),
            ];
            for (k, v) in [("risk", s.risk), ("cost", s.cost), ("margin", s.margin)] {
                if let Some(v) = v {
                    out.push((k, v.into()));
                }
            }
            plain(Json::Obj(out.into_iter().map(|(k, v)| (k.to_string(), v)).collect()))
        },
        "hedge.frontier.solve" => {
            let (a, b, w) = (i.matrix("a")?, i.reals("b")?, i.reals("weights")?);
            let ridge = ridge(i)?;
            let (e, r) = (opt_matrix(i, "eq_matrix")?, opt_reals(i, "eq_rhs")?);
            let (lo, hi) = (opt_bounds(i, "lower")?, opt_bounds(i, "upper")?);
            let singular = singular_policy(i)?;
            let lists = CostLists::read(i)?;
            let cost_weight = opt_f64(i, "cost_weight")?;
            let weights = i.reals("cost_weights")?;
            i.gate()?;
            let points = hs::frontier_solve(
                &QpProblem {
                    a: &a,
                    b: &b,
                    weights: &w,
                    ridge,
                    eq_matrix: e.as_ref(),
                    eq_rhs: r.as_deref(),
                    lower: lo.as_deref(),
                    upper: hi.as_deref(),
                    singular,
                    costs: lists.costs(cost_weight),
                },
                &weights,
            )?;
            let rows: Vec<Json> = points
                .into_iter()
                .map(|p| {
                    obj([
                        ("cost_weight", p.cost_weight.into()),
                        ("x", p.x.into()),
                        ("risk", p.risk.into()),
                        ("cost", p.cost.into()),
                    ])
                })
                .collect();
            plain(obj([("points", Json::Arr(rows))]))
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
        "hedge.credit.cds" => {
            let (t, d) = (i.date("trade_date")?, curve_input(i, "discount")?);
            let h = hazard_input(i, "hazard")?;
            let r = i.f64("recovery")?;
            let mut book = Vec::new();
            for x in items(i, "book")? {
                book.push(CdsTrade {
                    maturity: x.date("maturity")?,
                    coupon: x.f64("coupon")?,
                    notional: x.f64("notional")?,
                    buy: match x.str("side")? {
                        "BUY_PROTECTION" => true,
                        "SELL_PROTECTION" => false,
                        _ => return x.fail("side", "unknown side"),
                    },
                });
            }
            let mut hedges = Vec::new();
            for x in items(i, "hedges")? {
                hedges.push((x.date("maturity")?, x.f64("coupon")?));
            }
            let targets = i
                .array("targets")?
                .iter()
                .map(|v| v.as_str().map_or_else(|| i.fail("targets", "expected strings"), Ok))
                .collect::<Result<Vec<_>>>()?;
            i.gate()?;
            let (curve, pillars) = credit_discount(&d)?;
            let hazard = Hazard::new(h.0, &h.1)?;
            let market = CreditMarket {
                trade_date: t,
                discount: &curve,
                discount_pillars: &pillars,
                hazard: &hazard,
                recovery: r,
            };
            let s = hx::credit_hedge(&market, &book, &hedges, &targets)?;
            plain(obj([
                ("notionals", s.notionals.into()),
                ("book", credit_risk(&s.book, true)),
                ("after", credit_risk(&s.after, false)),
                ("hedge_upfront", s.hedge_upfront.into()),
            ]))
        },
        "hedge.correlation.neutralise" => {
            let market = CorrMarket {
                spot1: i.f64("spot1")?,
                spot2: i.f64("spot2")?,
                rate: i.f64("rate")?,
                yield1: i.f64("yield1")?,
                yield2: i.f64("yield2")?,
                vol1: i.f64("vol1")?,
                vol2: i.f64("vol2")?,
                correlation: i.f64("correlation")?,
            };
            let book = i
                .array("book")?
                .iter()
                .map(|v| corr_leg(i, "book", v, true))
                .collect::<Result<Vec<_>>>()?;
            let hedges = i
                .array("hedges")?
                .iter()
                .map(|v| corr_leg(i, "hedges", v, false).map(|l| l.0))
                .collect::<Result<Vec<_>>>()?;
            let targets = i
                .array("targets")?
                .iter()
                .map(|t| match t.as_str() {
                    Some("DELTA_1") => Ok(CorrTarget::Delta1),
                    Some("DELTA_2") => Ok(CorrTarget::Delta2),
                    Some("VEGA_1") => Ok(CorrTarget::Vega1),
                    Some("VEGA_2") => Ok(CorrTarget::Vega2),
                    Some("CORRELATION") => Ok(CorrTarget::Correlation),
                    _ => i.fail("targets", "unknown target"),
                })
                .collect::<Result<Vec<_>>>()?;
            i.gate()?;
            let r = hx::correlation_hedge(&market, &book, &hedges, &targets)?;
            plain(obj([
                ("quantities", r.quantities.into()),
                ("greeks_before", corr_greeks(r.before)),
                ("greeks_after", corr_greeks(r.after)),
            ]))
        },
        "hedge.crossasset.solve" => {
            let (spot, q, vol) = (i.f64("spot")?, i.f64("dividend_yield")?, i.f64("volatility")?);
            let c = super::rates::sub(i, "curve")?;
            let curve = ZeroCurve {
                times: c.reals("times")?,
                zero_rates: c.reals("zero_rates")?,
            };
            let book = i
                .array("book")?
                .iter()
                .map(|v| xa_leg(i, "book", v, true))
                .collect::<Result<Vec<_>>>()?;
            let hedges = i
                .array("hedges")?
                .iter()
                .map(|v| xa_leg(i, "hedges", v, false).map(|l| l.0))
                .collect::<Result<Vec<_>>>()?;
            let (w, ridge) = (i.reals("weights")?, ridge(i)?);
            i.gate()?;
            let market = XaMarket {
                spot,
                dividend_yield: q,
                volatility: vol,
                curve,
            };
            let r = xa::crossasset_solve(&market, &book, &hedges, &w, ridge)?;
            plain(obj([
                ("positions", r.positions.into()),
                ("book_risk", r.book_risk.into()),
                ("residual_risk", r.residual_risk.into()),
                ("objective", r.objective.into()),
            ]))
        },
        "hedge.effectiveness" => {
            let (x, y) = (i.reals("item_changes")?, i.reals("hedge_changes")?);
            i.gate()?;
            plain(obj(effectiveness_fields(&hd::effectiveness(&x, &y)?)))
        },
        "hedge.backtest.delta" => {
            let o = super::rates::sub(i, "option")?;
            let option = BacktestOption {
                call: match o.str("type")? {
                    "CALL" => true,
                    "PUT" => false,
                    _ => return o.fail("type", "must be CALL or PUT"),
                },
                strike: o.f64("strike")?,
                expiry: o.f64("expiry_years")?,
            };
            let setup = BacktestSetup {
                quantity: i.f64("quantity")?,
                rate: i.f64("rate")?,
                dividend_yield: i.f64("dividend_yield")?,
                hedge_volatility: i.f64("hedge_volatility")?,
            };
            let (times, spots) = (i.reals("times")?, i.reals("spots")?);
            i.gate()?;
            let r = hd::backtest_delta(&option, &setup, &times, &spots)?;
            let [d, s, r2, v] = effectiveness_fields(&r.effectiveness);
            plain(obj([
                ("option_values", r.option_values.into()),
                ("shares", r.shares.into()),
                ("portfolio_values", r.portfolio_values.into()),
                ("final_pnl", r.final_pnl.into()),
                d,
                s,
                r2,
                v,
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
