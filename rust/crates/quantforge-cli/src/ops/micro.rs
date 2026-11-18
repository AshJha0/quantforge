//! Stage H wave 2 verbs: the MBP book rebuild, the simulated lit matching engine, the microstructure
//! estimators and venue analytics (`specifications/09-microstructure/order-book.md`,
//! `micro-estimators.md`, `specifications/10-execution/lit-matching.md`, `venue-analytics.md`).

pub mod rebuild {
    use crate::input::Inputs;
    use crate::ops::{Outcome, plain};
    use quantforge_core::error::Result;
    use quantforge_core::json::Json;
    use quantforge_core::order_book;

    crate::ops::registry! {
    (op, i)
        "micro.book.rebuild" => {
            let messages = i.array("messages")?;
            let (depth, pd, qd) = (i.int("depth")?, i.int("price_decimals")?, i.int("qty_decimals")?);
            let checkpoints = match i.opt("checkpoints") {
                Some(_) => Some(i.array("checkpoints")?),
                None => None,
            };
            let emit = i.bool_or("emit_checksum_string", false)?;
            i.gate()?;
            let out: Json = order_book::rebuild(messages, depth, pd, qd, checkpoints, emit)?;
            plain(out)
        }
    }
}

pub mod lit {
    use crate::input::Inputs;
    use crate::ops::{Outcome, plain};
    use quantforge_core::error::Result;
    use quantforge_core::error::err;
    use quantforge_core::lit_matching;

    crate::ops::registry! {
    (op, i)
        "exec.sim.lit.run" => {
            let (tick, lot) = (i.str("tick_size")?, i.str("lot_size")?);
            let events = i.array("events")?;
            let fees = i.req("fee_schedule")?;
            if !matches!(fees, quantforge_core::json::Json::Obj(_)) {
                return Err(err("E_SCHEMA", "fee_schedule: expected an object"));
            }
            i.gate()?;
            plain(lit_matching::run(tick, lot, events, fees)?)
        }
    }
}

pub mod dark {
    use crate::input::Inputs;
    use crate::ops::{Outcome, plain};
    use quantforge_core::dark_pool;
    use quantforge_core::error::{Result, err};
    use quantforge_core::json::Json;
    use quantforge_core::sor;

    crate::ops::registry! {
    (op, i)
        "exec.sim.dark.run" => {
            if i.opt("scenarios").is_some() {
                let runs = i.array("scenarios")?;
                i.gate()?;
                let empty = Json::Obj(Vec::new());
                let mut out = Vec::with_capacity(runs.len());
                for (k, s) in runs.iter().enumerate() {
                    if !matches!(s, Json::Obj(_)) {
                        return Err(err("E_SCHEMA", format!("scenarios/{k}: not an object")));
                    }
                    let cfg = s.get("config").filter(|c| !matches!(c, Json::Null)).unwrap_or(&empty);
                    let events = s.get("events").and_then(Json::as_array).unwrap_or(&[]);
                    out.push(dark_pool::run(cfg, events)?);
                }
                return plain(Json::Obj(vec![("scenarios".into(), Json::Arr(out))]));
            }
            let cfg = i.req("config")?;
            if !matches!(cfg, Json::Obj(_)) {
                return Err(err("E_SCHEMA", "config: expected an object"));
            }
            let events = i.array("events")?;
            i.gate()?;
            plain(dark_pool::run(cfg, events)?)
        },
        "exec.sim.dark.markouts" => {
            let fills = i.array("fills")?;
            i.gate()?;
            plain(dark_pool::markouts(fills)?)
        },
        "exec.sor.allocate" => {
            i.gate()?;
            plain(sor::allocate(i.0)?)
        }
    }
}

/// Stage H H-4b microstructure estimators (`09-microstructure/micro-estimators.md`). Every input is
/// read before the gate, so `E_SCHEMA` and a non-finite input (F-2) come before any rule check
/// (HR-75 as amended (HR-66)).
pub mod est {
    use crate::input::Inputs;
    use crate::ops::{Outcome, plain};
    use quantforge_core::error::Result;
    use quantforge_core::json::{Json, obj};
    use quantforge_core::micro_est::{self as me, Estimate};

    fn est(e: Estimate, name: &str) -> Json {
        obj([(name, e.value.into()), ("se", e.se.into())])
    }

    /// Each element of the array `k` as an object reader.
    pub(crate) fn rows<'a>(i: &Inputs<'a>, k: &str) -> Result<Vec<Inputs<'a>>> {
        i.array(k)?
            .iter()
            .map(|v| match v {
                Json::Obj(_) => Ok(Inputs::new(v)),
                _ => i.fail(k, "expected an array of objects"),
            })
            .collect()
    }

    crate::ops::registry! {
    (op, i)
        "micro.est.arrival_rate" => {
            let count = i.int("count")?;
            let window = i.f64("window")?;
            i.gate()?;
            plain(est(me::arrival_rate(count, window)?, "lambda"))
        },
        "micro.est.cancel_rate" => {
            let mut orders = Vec::new();
            for o in rows(i, "orders")? {
                let life = o.f64("lifetime")?;
                let cancelled = match o.str("outcome")? {
                    "CANCEL" => true,
                    "FILL" => false,
                    _ => return o.fail("outcome", "expected CANCEL or FILL"),
                };
                orders.push((life, cancelled));
            }
            i.gate()?;
            plain(est(me::cancel_rate(&orders)?, "theta"))
        },
        "micro.est.resilience" => {
            let s_inf = i.f64("s_inf")?;
            let mut pts = Vec::new();
            for p in rows(i, "points")? {
                pts.push((p.f64("t")?, p.f64("s")?));
            }
            i.gate()?;
            plain(est(me::resilience(s_inf, &pts)?, "kappa"))
        },
        "micro.est.liquidity_decay" => {
            let mut lv = Vec::new();
            for p in rows(i, "levels")? {
                lv.push((p.f64("k")?, p.f64("depth")?));
            }
            i.gate()?;
            plain(est(me::liquidity_decay(&lv)?, "alpha"))
        },
        "micro.est.adverse_selection" => {
            let (x, y) = (i.reals("x")?, i.reals("y")?);
            i.gate()?;
            plain(est(me::adverse_selection(&x, &y)?, "lambda_as"))
        },
        "micro.est.regime_impact" => {
            let Json::Obj(reg) = i.req("regimes")? else {
                return i.fail("regimes", "expected an object");
            };
            let mut labels: Vec<&(String, Json)> = reg.iter().collect();
            labels.sort_by(|a, b| a.0.cmp(&b.0));
            let mut samples = Vec::new();
            for (label, v) in labels {
                if !matches!(v, Json::Obj(_)) {
                    return i.fail(label, "expected an object");
                }
                let r = Inputs::new(v);
                samples.push((label.clone(), me::Sample { x: r.reals("x")?, y: r.reals("y")? }));
            }
            i.gate()?;
            let (regimes, ratio) = me::regime_impact(&samples)?;
            let out = regimes.into_iter().map(|(k, e)| (k, est(e, "lambda_as"))).collect();
            plain(obj([("regimes", Json::Obj(out)), ("ratio", ratio.into())]))
        },
        "micro.est.passive_vs_aggressive" => {
            let (p, a) = (i.reals("passive")?, i.reals("aggressive")?);
            i.gate()?;
            plain(est(me::passive_vs_aggressive(&p, &a)?, "delta"))
        },
    }
}

/// Stage H H-16 venue analytics (`10-execution/venue-analytics.md`).
pub mod venue {
    use super::est::rows;
    use crate::input::Inputs;
    use crate::ops::{Outcome, plain};
    use quantforge_core::error::Result;
    use quantforge_core::json::{Json, obj};
    use quantforge_core::venue_analytics::{self as va, Fill, Order};

    fn run(i: &Inputs) -> Result<Outcome> {
        let mut mids = Vec::new();
        for m in rows(i, "mids")? {
            mids.push((m.f64("t")?, m.f64("mid")?));
        }
        let mut fills = Vec::new();
        for f in rows(i, "fills")? {
            let venue = f.str("venue")?.to_string();
            let buy = match f.str("side")? {
                "BUY" => true,
                "SELL" => false,
                _ => return f.fail("side", "expected BUY or SELL"),
            };
            fills.push(Fill {
                venue,
                buy,
                quantity: f.f64("quantity")?,
                price: f.f64("price")?,
                t: f.f64("t")?,
            });
        }
        let mut orders = Vec::new();
        for o in rows(i, "orders")? {
            orders.push(Order {
                venue: o.str("venue")?.to_string(),
                sent: o.f64("sent")?,
                filled: o.f64("filled")?,
            });
        }
        let horizons = i.reals("horizons")?;
        i.gate()?;
        let r = va::analytics(&mids, &fills, &orders, &horizons)?;
        let rates = r
            .fill_rates
            .into_iter()
            .map(|(k, v)| (k, v.into()))
            .collect();
        let rows = r
            .markouts
            .into_iter()
            .map(|m| {
                obj([
                    ("venue", Json::Str(m.venue)),
                    ("h", m.h.into()),
                    ("markout", m.markout.into()),
                    ("markout_bps", m.markout_bps.into()),
                    ("toxicity", m.toxicity.into()),
                ])
            })
            .collect();
        plain(obj([
            ("fill_rates", Json::Obj(rates)),
            ("markouts", Json::Arr(rows)),
        ]))
    }

    crate::ops::registry! {
    (op, i)
        "exec.venue.analytics" => run(i),
    }
}
