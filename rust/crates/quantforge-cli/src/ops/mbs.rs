//! `mbs.*` operations: read the inputs, call the library, shape the outputs.
use super::rates::sub;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::Result;
use quantforge_core::json::obj;
use quantforge_core::stage_d3;
use quantforge_core::stage_d3::Pool;
use quantforge_core::stage_d3::Prepayment;

super::registry! {
(op, i)
        "mbs.cashflows" => {
            let p = mbs_pool(i)?;
            let f = stage_d3::mbs_cashflows(&p)?;
            plain(obj([
                ("balance", f.balance.into()),
                ("interest", f.interest.into()),
                ("scheduled_principal", f.scheduled_principal.into()),
                ("prepayment", f.prepayment.into()),
                ("wal", f.wal.into()),
            ]))
        },
        "mbs.price" => {
            let (p, y, dd) = (mbs_pool(i)?, i.f64("yield")?, i.int("delay_days")?);
            let (pr, dur, wal) = stage_d3::mbs_price(&p, y, dd)?;
            plain(obj([
                ("price", pr.into()),
                ("modified_duration", dur.into()),
                ("wal", wal.into()),
            ]))
        }
}

pub(crate) fn mbs_pool(i: &Inputs) -> Result<Pool> {
    let p = sub(i, "pool")?;
    let pre = sub(&p, "prepayment")?;
    let prepayment = match pre.str("model")? {
        "CPR" => Prepayment::Cpr(pre.f64("rate")?),
        "PSA" => Prepayment::Psa(pre.f64("speed")?),
        _ => return pre.fail("model", "unknown prepayment model"),
    };
    Ok(Pool {
        balance: p.f64("balance")?,
        wac: p.f64("wac")?,
        net_coupon: p.f64("net_coupon")?,
        wam: p.int("wam")?,
        age: p.int("age")?,
        prepayment,
    })
}
