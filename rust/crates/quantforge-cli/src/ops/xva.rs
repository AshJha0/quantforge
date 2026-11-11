//! `xva.*` operations (stage G wave 4a: closed-form swap exposure under Hull-White).
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::{Result, fail};
use quantforge_core::json::{Json, obj};
use quantforge_core::shortrate::{self as sr, HwCurve};

super::registry! {
(op, i)
    "xva.exposure.swap_ee_hw" => {
        let (a, sigma) = (i.f64("mean_reversion")?, i.f64("sigma")?);
        if i.opt("short_rate").is_some() {
            return fail("E_INPUT", "HULL_WHITE takes no short_rate");
        }
        let c = super::rates::sub(i, "curve")?;
        let (ts, ds) = (c.reals("times")?, c.reals("discount_factors")?);
        let start = i.f64("start_years")?;
        let pay = i.reals("payment_times")?;
        let k = i.f64("fixed_rate")?;
        let side = i.str("side")?;
        let notional = i.f64("notional")?;
        let ex = i.reals("exposure_times")?;
        let credit = (i.opt_f64("hazard_rate")?, i.opt_f64("recovery")?);
        i.gate()?;
        if ts.len() > 10_000 {
            return fail("E_LIMIT", "at most 10,000 curve pillars");
        }
        let curve = HwCurve::new(&ts, &ds)?;
        let payer = match side {
            "PAY" => true,
            "RECEIVE" => false,
            _ => return fail("E_INPUT", "side must be PAY or RECEIVE"),
        };
        let swap = sr::SwapLeg { start, pay: &pay, fixed_rate: k, payer, notional };
        let (ee, cva) = sr::swap_ee_hw(&curve, a, sigma, &swap, &ex, credit)?;
        plain(match cva {
            Some(c) => obj([("discounted_ee", Json::from(ee)), ("cva", c.into())]),
            None => obj([("discounted_ee", Json::from(ee))]),
        })
    }
}
