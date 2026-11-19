//! Stage H wave 1 operations (rulings HR-1 to HR-10): execution schedules, Almgren-Chriss,
//! impact and implementation-shortfall TCA (`exec.*`), and Avellaneda-Stoikov quotes
//! (`micro.*`). Each domain has its own registry, as `ops/mod.rs` requires.
use super::eq::items;
use super::{Outcome, plain};
use crate::input::Inputs;
use crate::input::schema;
use quantforge_core::adaptive_exec as ae;
use quantforge_core::error::Result;
use quantforge_core::execution as ex;
use quantforge_core::json::{Json, obj};

/// `mode` is `UNITS` or `CONTINUOUS` (HR-3); absent means `CONTINUOUS`. True for `UNITS`.
fn units(i: &Inputs) -> Result<bool> {
    match i.opt("mode").map(|_| i.str("mode")).transpose()? {
        None | Some("CONTINUOUS") => Ok(false),
        Some("UNITS") => Ok(true),
        Some(_) => i.fail("mode", "unknown mode"),
    }
}

fn amount(a: ex::Amount) -> Json {
    match a {
        ex::Amount::Units(n) => Json::Int(n),
        ex::Amount::Real(x) => x.into(),
    }
}

fn amounts(v: Vec<ex::Amount>) -> Json {
    Json::Arr(v.into_iter().map(amount).collect())
}

/// `side` is `BUY` or `SELL`; true for `BUY`.
fn buy(i: &Inputs) -> Result<bool> {
    match i.str("side")? {
        "BUY" => Ok(true),
        "SELL" => Ok(false),
        _ => i.fail("side", "unknown side"),
    }
}

/// A nested object input, such as `leg_a` or `params`.
fn object<'a>(i: &Inputs<'a>, k: &str) -> Result<Inputs<'a>> {
    match i.req(k)? {
        v @ Json::Obj(_) => Ok(Inputs::new(v)),
        _ => i.fail(k, "expected an object"),
    }
}

fn leg(i: &Inputs, with_quantity: bool) -> Result<ae::Leg> {
    Ok(ae::Leg {
        buy: buy(i)?,
        quantity: if with_quantity {
            i.f64("quantity")?
        } else {
            0.0
        },
        price: i.f64("price")?,
    })
}

/// `books`: an array of buckets, each an array of `[price, size]` levels.
fn books(i: &Inputs) -> Result<Vec<Vec<[f64; 2]>>> {
    i.array("books")?
        .iter()
        .map(|b| {
            b.as_array()
                .ok_or_else(|| schema("books", "expected an array of arrays"))?
                .iter()
                .map(|l| match l.as_array() {
                    Some([p, q]) => match (p.as_f64(), q.as_f64()) {
                        (Some(p), Some(q)) => Ok([p, q]),
                        _ => Err(schema("books", "expected numbers")),
                    },
                    _ => Err(schema("books", "expected [price, size] pairs")),
                })
                .collect()
        })
        .collect()
}

fn opt_real(x: Option<f64>) -> Json {
    x.map_or(Json::Null, Json::from)
}

fn ac_params(i: &Inputs) -> Result<ex::AcParams> {
    Ok(ex::AcParams {
        quantity: i.f64("quantity")?,
        horizon: i.f64("horizon")?,
        n_steps: i.int("n_steps")?,
        sigma: i.f64("sigma")?,
        epsilon: i.f64("epsilon")?,
        eta: i.f64("eta")?,
        gamma: i.f64("gamma")?,
    })
}

pub mod exec {
    use super::{
        Inputs, Json, Outcome, Result, ac_params, ae, amount, amounts, books, buy, ex, items, leg,
        obj, object, opt_real, plain, units,
    };

    super::super::registry! {
    (op, i)
        "exec.schedule.twap" => {
            let (x, n, u) = (i.f64("quantity")?, i.int("n_buckets")?, units(i)?);
            i.gate()?;
            plain(obj([("slices", amounts(ex::schedule_twap(x, n, u)?))]))
        },
        "exec.schedule.vwap" => {
            let (x, w, u) = (i.f64("quantity")?, i.reals("profile")?, units(i)?);
            i.gate()?;
            plain(obj([("slices", amounts(ex::schedule_vwap(x, &w, u)?))]))
        },
        "exec.schedule.pov" => {
            let (x, p) = (i.f64("quantity")?, i.f64("participation")?);
            let (v, u) = (i.reals("market_volume")?, units(i)?);
            i.gate()?;
            let r = ex::schedule_pov(x, p, &v, u)?;
            plain(obj([
                ("slices", amounts(r.slices)),
                ("filled", amount(r.filled)),
                ("residual", amount(r.residual)),
            ]))
        },
        "exec.ac.trajectory" => {
            let (p, lam) = (ac_params(i)?, i.f64("risk_aversion")?);
            i.gate()?;
            let r = ex::ac_trajectory(&p, lam)?;
            plain(obj([
                ("holdings", r.holdings.into()),
                ("trades", r.trades.into()),
                ("kappa", r.kappa.into()),
                ("expected_cost", r.expected_cost.into()),
                ("variance", r.variance.into()),
                ("objective", r.objective.into()),
            ]))
        },
        "exec.ac.frontier" => {
            let (p, lams) = (ac_params(i)?, i.reals("risk_aversions")?);
            i.gate()?;
            let f = ex::ac_frontier(&p, &lams)?;
            let ec: Vec<f64> = f.iter().map(|q| q.expected_cost).collect();
            let var: Vec<f64> = f.iter().map(|q| q.variance).collect();
            plain(obj([
                ("risk_aversions", lams.into()),
                ("expected_costs", ec.into()),
                ("variances", var.into()),
            ]))
        },
        "exec.impact.sqrt" => {
            let (q, v) = (i.f64("quantity")?, i.f64("daily_volume")?);
            let (s, y) = (i.f64("daily_vol")?, i.f64_or("coefficient", 1.0)?);
            i.gate()?;
            plain(obj([
                ("impact", ex::impact_sqrt(q, v, s, y)?.into()),
                ("model", ex::MODEL.into()),
            ]))
        },
        "exec.impact.ow_optimal" => {
            let (x, t, r) = (i.f64("quantity")?, i.f64("horizon")?, i.f64("resilience")?);
            i.gate()?;
            let (block, rate) = ex::impact_ow_optimal(x, t, r)?;
            plain(obj([
                ("initial_block", block.into()),
                ("rate", rate.into()),
                ("final_block", block.into()),
            ]))
        },
        "exec.tca.shortfall" => {
            let buy = match i.str("side")? {
                "BUY" => true,
                "SELL" => false,
                _ => return i.fail("side", "unknown side"),
            };
            let (pd, p0) = (i.f64("decision_price")?, i.f64("arrival_price")?);
            let (pc, x) = (i.f64("end_price")?, i.f64("order_quantity")?);
            let mut fills = Vec::new();
            for f in items(i, "fills")? {
                fills.push((f.f64("quantity")?, f.f64("price")?));
            }
            let (fees, vwap) = (i.f64_or("fees", 0.0)?, i.opt_f64("benchmark_vwap")?);
            i.gate()?;
            let r = ex::tca_shortfall(&ex::TcaOrder {
                buy,
                decision_price: pd,
                arrival_price: p0,
                end_price: pc,
                order_quantity: x,
                fills,
                fees,
                benchmark_vwap: vwap,
            })?;
            let mut out = obj([
                ("delay", r.delay.into()),
                ("execution", r.execution.into()),
                ("opportunity", r.opportunity.into()),
                ("total", r.total.into()),
                ("total_bps", r.total_bps.into()),
            ]);
            if let (Some(v), Json::Obj(o)) = (r.vwap_slippage, &mut out) {
                o.push(("vwap_slippage".to_string(), v.into()));
            }
            plain(out)
        },
        // Stage H wave 2 execution (HR-59 to HR-67): adaptive-algos.md and tca-pretrade.md.
        "exec.algo.arrival" => {
            let (x, n) = (i.f64("quantity")?, i.int("n_buckets")?);
            let (k, u) = (i.f64("urgency")?, units(i)?);
            i.gate()?;
            plain(obj([("slices", amounts(ae::arrival(x, n, k, u)?))]))
        },
        "exec.algo.close" => {
            let (x, v) = (i.f64("quantity")?, i.f64("close_volume")?);
            let p = i.f64("auction_participation")?;
            let (w, u) = (i.reals("profile")?, units(i)?);
            i.gate()?;
            let (a, s) = ae::close(x, v, p, &w, u)?;
            plain(obj([("auction_quantity", amount(a)), ("slices", amounts(s))]))
        },
        "exec.algo.liquidity_seek" => {
            let (b, x) = (buy(i)?, i.f64("quantity")?);
            let (l, a, bk) = (i.f64("limit_price")?, i.f64("take_fraction")?, books(i)?);
            i.gate()?;
            let r = ae::liquidity_seek(b, x, l, a, &bk)?;
            plain(obj([
                ("slices", r.slices.into()),
                ("avg_prices", Json::Arr(r.avg_prices.into_iter().map(opt_real).collect())),
                ("filled", r.filled.into()),
                ("residual", r.residual.into()),
                ("notional", r.notional.into()),
                ("avg_fill_price", opt_real(r.avg_fill_price)),
            ]))
        },
        "exec.algo.pair" => {
            let a = leg(&object(i, "leg_a")?, true)?;
            let b = leg(&object(i, "leg_b")?, false)?;
            let hedged = match i.str("pair_mode")? {
                "CASH_BALANCED" => false,
                "HEDGED" => true,
                _ => return i.fail("pair_mode", "unknown pair_mode"),
            };
            let (h, n, u) = (i.opt_f64("hedge_ratio")?, i.int("n_buckets")?, units(i)?);
            i.gate()?;
            let r = ae::pair(a, b, hedged, h, n, u)?;
            plain(obj([
                ("slices_a", amounts(r.slices_a)),
                ("slices_b", amounts(r.slices_b)),
                ("quantity_b", amount(r.quantity_b)),
                ("cash_imbalance", r.cash_imbalance.into()),
            ]))
        },
        "exec.algo.basket" => {
            let legs = items(i, "legs")?
                .iter()
                .map(|g| leg(g, true))
                .collect::<Result<Vec<_>>>()?;
            let (n, u) = (i.int("n_buckets")?, units(i)?);
            i.gate()?;
            let r = ae::basket(&legs, n, u)?;
            plain(obj([
                ("slices", Json::Arr(r.slices.into_iter().map(amounts).collect())),
                ("cash_imbalance", r.cash_imbalance.into()),
                ("gross_notional", r.gross_notional.into()),
            ]))
        },
        "exec.tca.pretrade" => {
            let (x, adv, sig) = (i.f64("quantity")?, i.f64("adv")?, i.f64("daily_vol")?);
            let (p, hs) = (i.f64("participation")?, i.f64("half_spread_bps")?);
            let k = object(i, "params")?;
            let k = ae::IstarParams {
                a1: k.f64("a1")?,
                a2: k.f64("a2")?,
                a3: k.f64("a3")?,
                a4: k.f64("a4")?,
                b1: k.f64("b1")?,
            };
            let price = i.opt_f64("price")?;
            i.gate()?;
            let r = ae::pretrade(x, adv, sig, p, hs, k, price)?;
            let mut out = vec![
                ("istar_bps", r.istar_bps),
                ("impact_bps", r.impact_bps),
                ("spread_bps", r.spread_bps),
                ("expected_cost_bps", r.expected_cost_bps),
                ("duration_days", r.duration_days),
                ("timing_risk_bps", r.timing_risk_bps),
            ];
            if let (Some(c), Some(t)) = (r.expected_cost, r.timing_risk) {
                out.extend([("expected_cost", c), ("timing_risk", t)]);
            }
            plain(Json::Obj(out.into_iter().map(|(k, v)| (k.to_string(), v.into())).collect()))
        },
        "exec.tca.attribution" => {
            let b = buy(i)?;
            let (pd, m0) = (i.f64("decision_price")?, i.f64("arrival_mid")?);
            let (pc, x) = (i.f64("end_price")?, i.f64("order_quantity")?);
            let mut fills = Vec::new();
            for f in items(i, "fills")? {
                fills.push(ae::Fill {
                    quantity: f.f64("quantity")?,
                    price: f.f64("price")?,
                    mid: f.f64("mid")?,
                });
            }
            let fees = i.f64_or("fees", 0.0)?;
            i.gate()?;
            let r = ae::attribution(b, pd, m0, pc, x, &fills, fees)?;
            plain(obj([
                ("delay", r.delay.into()),
                ("impact", r.impact.into()),
                ("spread", r.spread.into()),
                ("execution", r.execution.into()),
                ("opportunity", r.opportunity.into()),
                ("fees", r.fees.into()),
                ("total", r.total.into()),
                ("total_bps", r.total_bps.into()),
            ]))
        },
    }
}

pub mod micro {
    use super::{Inputs, Outcome, Result, ex, obj, plain};

    super::super::registry! {
    (op, i)
        "micro.mm.as_quotes" => {
            let (s, q) = (i.f64("mid")?, i.f64("inventory")?);
            let (g, sig) = (i.f64("risk_aversion")?, i.f64("sigma")?);
            let (t, k) = (i.f64("time_left")?, i.f64("k")?);
            i.gate()?;
            let r = ex::as_quotes(s, q, g, sig, t, k)?;
            plain(obj([
                ("reservation", r.reservation.into()),
                ("spread", r.spread.into()),
                ("bid", r.bid.into()),
                ("ask", r.ask.into()),
            ]))
        },
    }
}

/// Use case 5 lives in the `usecase` domain but reuses this module's readers.
pub mod usecase {
    use super::{Inputs, Json, Outcome, Result, ac_params, ex, obj, plain};

    super::super::registry! {
    (op, i)
        "usecase.execution_tca" => {
            let p = ac_params(i)?;
            let risk_aversion = i.f64("risk_aversion")?;
            let buy = match i.str("side")? {
                "BUY" => true,
                "SELL" => false,
                _ => return i.fail("side", "unknown side"),
            };
            let u = ex::ExecutionTca {
                risk_aversion,
                buy,
                decision_price: i.f64("decision_price")?,
                arrival_price: i.f64("arrival_price")?,
                end_price: i.f64("end_price")?,
                fill_prices: i.reals("fill_prices")?,
                completed_steps: i.int("completed_steps")?,
                fee_per_unit: i.f64("fee_per_unit")?,
            };
            i.gate()?;
            let r = ex::execution_tca(&p, &u)?;
            let s = r.shortfall;
            plain(obj([
                ("lots", Json::Arr(r.lots.into_iter().map(Json::Int).collect())),
                ("expected_cost", r.expected_cost.into()),
                ("variance", r.variance.into()),
                ("filled", Json::Int(r.filled)),
                ("fees", r.fees.into()),
                ("delay", s.delay.into()),
                ("execution", s.execution.into()),
                ("opportunity", s.opportunity.into()),
                ("total", s.total.into()),
                ("total_bps", s.total_bps.into()),
            ]))
        },
    }
}

#[cfg(test)]
mod tests {
    use crate::limits::check;
    use crate::ops::operations;
    use quantforge_core::json::parse;

    fn limited(op: &str, text: &str) -> bool {
        check(op, &parse(text).unwrap().0).is_some()
    }

    fn list(key: &str, item: &str, n: usize) -> String {
        format!(r#"{{"{key}":[{}]}}"#, vec![item; n].join(","))
    }

    #[test]
    fn names_are_registered() {
        for n in [
            "exec.ac.frontier",
            "exec.ac.trajectory",
            "exec.impact.ow_optimal",
            "exec.impact.sqrt",
            "exec.schedule.pov",
            "exec.schedule.twap",
            "exec.schedule.vwap",
            "exec.tca.shortfall",
            "micro.mm.as_quotes",
            "exec.algo.arrival",
            "exec.algo.close",
            "exec.algo.liquidity_seek",
            "exec.algo.pair",
            "exec.algo.basket",
            "exec.tca.pretrade",
            "exec.tca.attribution",
        ] {
            assert!(operations().contains(&n), "{n}");
        }
    }

    #[test]
    fn hr_9_limits() {
        assert!(limited("exec.schedule.twap", r#"{"n_buckets":100001}"#));
        assert!(!limited("exec.schedule.twap", r#"{"n_buckets":100000}"#));
        assert!(limited("exec.ac.trajectory", r#"{"n_steps":100001}"#));
        assert!(limited("exec.ac.frontier", r#"{"n_steps":100001}"#));
        assert!(!limited(
            "exec.tca.shortfall",
            &list("fills", "{}", 100_001)
        ));
        assert!(limited(
            "exec.tca.shortfall",
            &list("fills", "{}", 1_000_001)
        ));
        for op in ["exec.algo.arrival", "exec.algo.pair", "exec.algo.basket"] {
            assert!(limited(op, r#"{"n_buckets":100001}"#));
            assert!(!limited(op, r#"{"n_buckets":100000}"#));
        }
        assert!(!limited(
            "exec.tca.attribution",
            &list("fills", "{}", 100_001)
        ));
        assert!(limited(
            "exec.tca.attribution",
            &list("fills", "{}", 1_000_001)
        ));
        assert!(limited(
            "exec.schedule.vwap",
            &list("profile", "1", 100_001)
        ));
    }
}
