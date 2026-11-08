//! Stage E operations: E7 (`garch.md`, `variance-swaps.md`, `vix-index.md`).

use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use crate::ops_b::{items, sub};
use quantforge_core::error::{Result, fail};
use quantforge_core::garch::{self, Start};
use quantforge_core::json::{Json, obj};
use quantforge_core::varswap::{self, Replication};
use quantforge_core::vix::{self, Quote};

/// `initial_variance`: `"SAMPLE"` or a number; another string is `E_INPUT`, another type
/// `E_SCHEMA`. The string check is returned apart so it can run in its spec order.
fn start(i: &Inputs) -> Result<std::result::Result<Start, ()>> {
    match i.req("initial_variance")? {
        Json::Str(s) if s == "SAMPLE" => Ok(Ok(Start::Sample)),
        Json::Str(_) => Ok(Err(())),
        _ => Ok(Ok(Start::Given(i.f64("initial_variance")?))),
    }
}

fn bad_start<T>() -> Result<T> {
    fail("E_INPUT", "initial_variance must be \"SAMPLE\" or a number")
}

fn strip(i: &Inputs) -> Result<(i64, f64, Vec<Quote>)> {
    let n = i.int("minutes_to_expiry")?;
    let r = i.f64("rate")?;
    let s = items(i, "strip")?
        .iter()
        .map(|q| {
            Ok(Quote {
                strike: q.f64("strike")?,
                call_bid: q.f64("call_bid")?,
                call_ask: q.f64("call_ask")?,
                put_bid: q.f64("put_bid")?,
                put_ask: q.f64("put_ask")?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    Ok((n, r, s))
}

pub fn dispatch(op: &str, i: &Inputs) -> Result<Outcome> {
    match op {
        "vol.garch.loglik" => {
            let r = i.reals("returns")?;
            let (o, a, b) = (i.f64("omega")?, i.f64("alpha")?, i.f64("beta")?);
            let s = start(i)?;
            i.gate()?;
            if r.len() < 2 {
                return fail("E_INPUT", "at least 2 returns are required");
            }
            let Ok(s) = s else { return bad_start() };
            let l = garch::loglik(&r, o, a, b, s)?;
            plain(obj([
                ("loglik", l.loglik.into()),
                ("variances", l.variances.into()),
                ("next_variance", l.next_variance.into()),
            ]))
        }
        "vol.garch.forecast" => {
            let (o, a, b) = (i.f64("omega")?, i.f64("alpha")?, i.f64("beta")?);
            let (v, h, p) = (
                i.f64("next_variance")?,
                i.int("horizon")?,
                i.f64("periods_per_year")?,
            );
            i.gate()?;
            let f = garch::forecast(o, a, b, v, h, p)?;
            plain(obj([
                ("variances", f.variances.into()),
                ("total_variance", f.total_variance.into()),
                ("annualized_vol", f.annualized_vol.into()),
                ("long_run_variance", f.long_run_variance.into()),
            ]))
        }
        "vol.garch.fit" => {
            let r = i.reals("returns")?;
            let s = start(i)?;
            i.gate()?;
            if r.len() < 30 {
                return fail("E_INPUT", "at least 30 returns are required");
            }
            let Ok(s) = s else { return bad_start() };
            let f = garch::fit(&r, s)?;
            plain(obj([("loglik", f.loglik.into())]))
        }
        "vol.varswap.fair_strike" => {
            let vols = items(i, "vols")?
                .iter()
                .map(|v| Ok((v.f64("strike")?, v.f64("vol")?)))
                .collect::<Result<Vec<_>>>()?;
            let (puts, calls) = (i.reals("put_strikes")?, i.reals("call_strikes")?);
            let x = Replication {
                as_of: i.date("as_of")?,
                maturity: i.date("maturity")?,
                spot: i.f64("spot")?,
                rate: i.f64("rate")?,
                dividend_yield: i.f64("dividend_yield")?,
                put_strikes: &puts,
                call_strikes: &calls,
                vols: &vols,
                extension_step: i.f64("extension_step")?,
                variance_strike: i.f64("variance_strike")?,
                variance_notional: i.f64("variance_notional")?,
            };
            i.gate()?;
            let f = varswap::fair_strike(&x)?;
            plain(obj([
                ("fair_variance", f.fair_variance.into()),
                ("fair_vol", f.fair_vol.into()),
                ("pv", f.pv.into()),
            ]))
        }
        "vol.varswap.realized" => {
            let p = i.reals("prices")?;
            let a = i.f64("periods_per_year")?;
            let (k, n) = (i.f64("variance_strike")?, i.f64("variance_notional")?);
            i.gate()?;
            let r = varswap::realized(&p, a, k, n)?;
            plain(obj([
                ("realized_variance", r.realized_variance.into()),
                ("realized_vol", r.realized_vol.into()),
                ("payoff", r.payoff.into()),
            ]))
        }
        "vol.vix.term_variance" => {
            let (n, r, s) = strip(i)?;
            i.gate()?;
            let t = vix::term_variance(n, r, &s)?;
            plain(obj([
                ("forward", t.forward.into()),
                ("k0", t.k0.into()),
                ("variance", t.variance.into()),
                ("strikes_used", t.strikes_used.into()),
            ]))
        }
        "vol.vix.index" => {
            let near = strip(&sub(i, "near")?)?;
            let next = strip(&sub(i, "next")?)?;
            i.gate()?;
            let x = vix::index((near.0, near.1, &near.2), (next.0, next.1, &next.2))?;
            plain(obj([
                ("index", x.index.into()),
                ("near_variance", x.near_variance.into()),
                ("next_variance", x.next_variance.into()),
            ]))
        }
        _ => fail(
            "E_UNSUPPORTED_OPERATION",
            format!("{op} is not in this build"),
        ),
    }
}
