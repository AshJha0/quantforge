//! `exotic.*` operations: read the inputs, call the library, shape the outputs.
use super::fx::call_or_put;
use super::rates::sub;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::Result;
use quantforge_core::error::fail;
use quantforge_core::exotics;
use quantforge_core::json::obj;

super::registry! {
(op, i)
        "exotic.digital.price" => {
            let x = vanilla(i, true, true)?;
            let cash_kind = pick(
                i,
                "payoff",
                &[("CASH_OR_NOTHING", true), ("ASSET_OR_NOTHING", false)],
            )?;
            price_out(exotics::digital(&x, cash_kind, i.f64("cash")?)?)
        },
        "exotic.barrier.price" => {
            use exotics::BarrierType::{DownIn, DownOut, UpIn, UpOut};
            let x = vanilla(i, true, true)?;
            let (h, r) = (i.f64("barrier")?, i.f64("rebate")?);
            let table = [
                ("DOWN_IN", DownIn),
                ("DOWN_OUT", DownOut),
                ("UP_IN", UpIn),
                ("UP_OUT", UpOut),
            ];
            let kind = pick(i, "barrier_type", &table)?;
            let discrete = match i.opt("monitoring").map(|_| i.str("monitoring")).transpose()? {
                None | Some("CONTINUOUS") => false,
                Some("DISCRETE") => true,
                Some(_) => return fail("E_INPUT", "monitoring must be CONTINUOUS or DISCRETE"),
            };
            let m = i.opt_int("monitoring_per_year")?;
            match (discrete, m) {
                (false, None) => price_out(exotics::barrier(&x, h, r, kind)?),
                (true, Some(m)) => price_out(exotics::barrier_discrete(&x, h, r, kind, m)?),
                (true, None) => fail("E_INPUT", "DISCRETE monitoring needs monitoring_per_year"),
                (false, Some(_)) => fail("E_INPUT", "monitoring_per_year needs DISCRETE monitoring"),
            }
        },
        "exotic.asian.geometric" => {
            let x = vanilla(i, true, true)?;
            let continuous = pick(i, "averaging", &[("CONTINUOUS", true), ("DISCRETE", false)])?;
            let f = i.reals("fixing_years")?;
            i.gate()?;
            x.check()?;
            if continuous && !f.is_empty() {
                return fail("E_INPUT", "CONTINUOUS averaging takes fixing_years []");
            }
            price_out(exotics::asian_geometric(
                &x,
                (!continuous).then_some(&f[..]),
            )?)
        },
        "exotic.lookback.floating" => {
            let x = vanilla(i, false, true)?;
            price_out(exotics::lookback_floating(&x, i.f64("running_extreme")?)?)
        },
        "exotic.quanto.price" => {
            let q = exotics::Quanto {
                spot: i.f64("spot")?,
                strike: i.f64("strike")?,
                expiry_years: i.f64("expiry_years")?,
                domestic_rate: i.f64("domestic_rate")?,
                foreign_rate: i.f64("foreign_rate")?,
                dividend_yield: i.f64("dividend_yield")?,
                vol: i.f64("vol")?,
                fx_vol: i.f64("fx_vol")?,
                correlation: i.f64("correlation")?,
                call: call_or_put(i)?,
            };
            price_out(exotics::quanto(&q)?)
        },
        "exotic.chooser.price" => {
            let x = vanilla(i, true, false)?;
            price_out(exotics::chooser(&x, i.f64("choose_years")?)?)
        },
        "exotic.spread.kirk" => {
            let s = exotics::Spread {
                forward_1: i.f64("forward_1")?,
                forward_2: i.f64("forward_2")?,
                strike: i.f64("strike")?,
                expiry_years: i.f64("expiry_years")?,
                rate: i.f64("rate")?,
                vol_1: i.f64("vol_1")?,
                vol_2: i.f64("vol_2")?,
                correlation: i.f64("correlation")?,
            };
            price_out(exotics::kirk(&s)?)
        },
        "exotic.basket.moment" => {
            let (f, w, v) = (i.reals("forwards")?, i.reals("weights")?, i.reals("vols")?);
            let c = i.matrix("correlation")?;
            let b = exotics::Basket {
                forwards: &f,
                weights: &w,
                vols: &v,
                correlation: &c,
                strike: i.f64("strike")?,
                expiry_years: i.f64("expiry_years")?,
                rate: i.f64("rate")?,
                call: call_or_put(i)?,
            };
            i.gate()?;
            let (p, m1, vb) = exotics::basket(&b)?;
            plain(obj([
                ("price", p.into()),
                ("basket_forward", m1.into()),
                ("basket_vol", vb.into()),
            ]))
        },
        "exotic.american.crr" => {
            let (x, n) = (vanilla(i, true, true)?, i.int("steps")?);
            i.gate()?;
            let t = exotics::crr(&x, n)?;
            plain(obj([
                ("american", t.american.into()),
                ("european", t.european.into()),
                ("early_exercise_premium", (t.american - t.european).into()),
            ]))
        },
        "exotic.american.baw" => price_out(exotics::baw(&vanilla(i, true, true)?)?),
        "exotic.american.fd" => {
            let x = vanilla(i, true, true)?;
            let american = pick(i, "exercise", &[("AMERICAN", true), ("EUROPEAN", false)])?;
            let g = sub(i, "grid")?;
            let grid = exotics::FdGrid {
                nx: g.int("nx")?,
                nt: g.int("nt")?,
                width: g.f64("width")?,
            };
            i.gate()?;
            let r = exotics::american_fd(&x, american, &grid)?;
            plain(obj([
                ("price", r.price.into()),
                ("delta", r.delta.into()),
                ("gamma", r.gamma.into()),
            ]))
        }
}

pub(crate) fn vanilla(i: &Inputs, with_strike: bool, with_type: bool) -> Result<exotics::Vanilla> {
    Ok(exotics::Vanilla {
        spot: i.f64("spot")?,
        strike: if with_strike { i.f64("strike")? } else { 1.0 },
        expiry_years: i.f64("expiry_years")?,
        rate: i.f64("rate")?,
        dividend_yield: i.f64("dividend_yield")?,
        vol: i.f64("vol")?,
        call: if with_type { call_or_put(i)? } else { true },
    })
}

pub(crate) fn pick<T: Copy>(i: &Inputs, k: &str, table: &[(&str, T)]) -> Result<T> {
    let s = i.str(k)?;
    table
        .iter()
        .find(|(name, _)| *name == s)
        .map_or_else(|| i.fail(k, "unknown value"), |(_, v)| Ok(*v))
}

pub(crate) fn price_out(p: f64) -> Result<Outcome> {
    plain(obj([("price", p.into())]))
}
