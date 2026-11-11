//! `rates.lmm.*` operations (stage G wave 3b).
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::{Result, fail};
use quantforge_core::json::obj;
use quantforge_core::lmm::{Abcd, capfloor, swaption_rebonato};
use quantforge_core::shortrate::HwCurve;

fn abcd(i: &Inputs) -> Result<Abcd> {
    let v = super::rates::sub(i, "abcd")?;
    Ok(Abcd {
        a: v.f64("a")?,
        b: v.f64("b")?,
        c: v.f64("c")?,
        d: v.f64("d")?,
    })
}

fn curve(i: &Inputs) -> Result<(Vec<f64>, Vec<f64>)> {
    let c = super::rates::sub(i, "curve")?;
    Ok((c.reals("times")?, c.reals("discount_factors")?))
}

super::registry! {
(op, i)
    "rates.lmm.capfloor" => {
        let (ts, ds) = curve(i)?;
        let v = abcd(i)?;
        let times = i.reals("period_times")?;
        let k = i.f64("strike")?;
        let cf = i.str("cap_floor")?;
        let notional = i.f64("notional")?;
        i.gate()?;
        if times.len() > 10_001 {
            return fail("E_LIMIT", "at most 10,000 periods");
        }
        let c = HwCurve::new(&ts, &ds)?;
        let cap = match cf {
            "CAP" => true,
            "FLOOR" => false,
            _ => return fail("E_INPUT", "cap_floor must be CAP or FLOOR"),
        };
        let r = capfloor(&c, &v, &times, k, cap, notional)?;
        plain(obj([
            ("price", r.price.into()),
            ("caplet_prices", r.caplet_prices.into()),
            ("forward_rates", r.forward_rates.into()),
            ("black_vols", r.black_vols.into()),
        ]))
    },
    "rates.lmm.swaption_rebonato" => {
        let (ts, ds) = curve(i)?;
        let v = abcd(i)?;
        let beta = i.f64("correlation_beta")?;
        let te = i.f64("expiry_years")?;
        let pay = i.reals("payment_times")?;
        let k = i.f64("fixed_rate")?;
        let side = i.str("side")?;
        let notional = i.f64("notional")?;
        i.gate()?;
        if pay.len() > 10_000 {
            return fail("E_LIMIT", "at most 10,000 payment times");
        }
        let c = HwCurve::new(&ts, &ds)?;
        let payer = match side {
            "PAY" => true,
            "RECEIVE" => false,
            _ => return fail("E_INPUT", "side must be PAY or RECEIVE"),
        };
        let r = swaption_rebonato(&c, &v, beta, te, &pay, k, payer, notional)?;
        plain(obj([
            ("price", r.price.into()),
            ("swap_rate", r.swap_rate.into()),
            ("annuity", r.annuity.into()),
            ("black_vol", r.black_vol.into()),
        ]))
    }
}
