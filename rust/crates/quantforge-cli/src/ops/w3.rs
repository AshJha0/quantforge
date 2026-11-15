//! Stage J wave 3 (rulings J-W3-1 to J-W3-14): scenario stress, interpolation backtests and
//! drift detectors. Two registries, one per first name segment (`risk`, `research`).
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::Result;
use quantforge_core::interp::Method;
use quantforge_core::json::{Json, obj};
use quantforge_core::research_w3 as w3;

pub(super) mod risk {
    use super::*;
    crate::ops::registry! {
    (op, i)
            "risk.scenario.historical_shock" => {
                let (d, t, y) = (i.dates("dates")?, i.reals("tenors")?, i.matrix("yields")?);
                let (s, e) = (i.date("start_date")?, i.date("end_date")?);
                i.gate()?;
                let r = w3::historical_shock(&d, &t, &y, s, e)?;
                plain(obj([
                    ("start_yields", r.start_yields.into()),
                    ("end_yields", r.end_yields.into()),
                    ("shift_bp", r.shift_bp.into()),
                    ("level_bp", r.level_bp.into()),
                    ("slope_bp", r.slope_bp.into()),
                ]))
            },
            "risk.scenario.replay" => replay(i),
    }
}

fn replay(i: &Inputs) -> Result<Outcome> {
    let (bt, by) = (i.reals("base_tenors")?, i.reals("base_yields")?);
    let (st, sb) = (i.reals("shock_tenors")?, i.reals("shock_bp")?);
    let scale = i.f64_or("scale", 1.0)?;
    let dv01 = i.opt("dv01").map(|_| i.reals("dv01")).transpose()?;
    i.gate()?;
    let r = w3::replay(&bt, &by, &st, &sb, scale, dv01.as_deref())?;
    let mut fields: Vec<(&str, Json)> =
        vec![("applied_bp", r.applied_bp.into()), ("shocked_yields", r.shocked_yields.into())];
    if let Some(p) = r.pnl {
        fields.push(("pnl", p.into()));
    }
    plain(Json::Obj(fields.into_iter().map(|(k, v)| (k.to_string(), v)).collect()))
}

fn method(i: &Inputs, surface: bool) -> Result<Method> {
    Ok(match i.str("method")? {
        "linear" => Method::Linear,
        "log_linear" if !surface => Method::LogLinear,
        "cubic_natural" => Method::CubicNatural,
        "monotone_pchip" => Method::Pchip,
        _ => return i.fail("method", "unknown method"),
    })
}

fn alarms(a: w3::Alarms, extra: Vec<(&'static str, Json)>) -> Result<Outcome> {
    let mut f: Vec<(&str, Json)> = vec![("alarms", a.alarms.into()), ("directions", a.directions.into())];
    f.extend(extra);
    plain(Json::Obj(f.into_iter().map(|(k, v)| (k.to_string(), v)).collect()))
}

pub(super) mod research {
    use super::*;
    crate::ops::registry! {
    (op, i)
            "research.backtest.interp_loo" => {
                let m = method(i, false)?;
                let (x, y) = (i.reals("x")?, i.reals("y")?);
                i.gate()?;
                let r = w3::interp_loo(m, &x, &y)?;
                plain(obj([
                    ("errors", r.errors.into()),
                    ("max_abs_error", r.max_abs_error.into()),
                    ("rmse", r.rmse.into()),
                ]))
            },
            "research.backtest.surface_holdout" => {
                let m = method(i, true)?;
                let (e, k, v) = (i.reals("expiries")?, i.reals("strikes")?, i.matrix("vols")?);
                let h = super::super::rates::ints(i, "holdout")?;
                i.gate()?;
                let r = w3::surface_holdout(m, &e, &k, &v, &h)?;
                plain(obj([
                    ("errors", r.errors.into()),
                    ("max_abs_error", r.max_abs_error.into()),
                    ("rmse", r.rmse.into()),
                ]))
            },
            "research.drift.cusum" => {
                let x = i.reals("x")?;
                let (k, h) = (i.f64("k")?, i.f64("h")?);
                let (mu0, s) = (i.f64_or("mu0", 0.0)?, i.f64_or("sigma", 1.0)?);
                let reset = i.bool_or("reset", true)?;
                i.gate()?;
                let (a, sp, sm) = w3::cusum(&x, k, h, mu0, s, reset)?;
                alarms(a, vec![("s_plus", sp.into()), ("s_minus", sm.into())])
            },
            "research.drift.page_hinkley" => {
                let x = i.reals("x")?;
                let (d, l) = (i.f64("delta")?, i.f64("lambda")?);
                let dir = match i.opt("direction").map(|_| i.str("direction")).transpose()? {
                    None | Some("both") => w3::Direction::Both,
                    Some("up") => w3::Direction::Up,
                    Some("down") => w3::Direction::Down,
                    Some(_) => return i.fail("direction", "direction must be up, down or both"),
                };
                let reset = i.bool_or("reset", true)?;
                i.gate()?;
                alarms(w3::page_hinkley(&x, d, l, dir, reset)?, vec![])
            },
            "research.drift.psi" => {
                let (r, t) = (i.reals("reference")?, i.reals("test")?);
                let (b, th) = (i.int_or("bins", 10)?, i.f64_or("threshold", 0.25)?);
                i.gate()?;
                let p = w3::psi(&r, &t, b, th)?;
                plain(obj([
                    ("psi", p.psi.into()),
                    ("reference_shares", p.reference_shares.into()),
                    ("test_shares", p.test_shares.into()),
                    ("alarm", p.alarm.into()),
                ]))
            },
            "research.drift.ks" => {
                let (a, b) = (i.reals("a")?, i.reals("b")?);
                let level = i.f64_or("level", 0.05)?;
                i.gate()?;
                let (d, p, rej) = w3::ks(&a, &b, level)?;
                plain(obj([("statistic", d.into()), ("p_value", p.into()), ("reject", rej.into())]))
            },
    }
}
