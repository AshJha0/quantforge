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
            i.gate()?;
            plain(lit_matching::run(tick, lot, events, fees)?)
        }
    }
}
