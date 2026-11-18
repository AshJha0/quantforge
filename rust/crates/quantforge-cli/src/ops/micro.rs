//! Stage H wave 2 verbs: the MBP book rebuild and the simulated lit matching engine
//! (`specifications/09-microstructure/order-book.md`, `specifications/10-execution/lit-matching.md`).

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
            let session = i.opt("session");
            if session.is_some_and(|s| !matches!(s, quantforge_core::json::Json::Obj(_))) {
                return Err(err("E_SCHEMA", "session: expected an object"));
            }
            i.gate()?;
            plain(lit_matching::run(tick, lot, events, fees, session)?)
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
