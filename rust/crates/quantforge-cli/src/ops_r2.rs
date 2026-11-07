//! Phase R2 operations (contract 1.7.0): `06-risk/par-and-key-rate.md`.

use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use crate::ops_b::{
    curve_input, interpolation, ois_quotes, ois_quotes_at, ois_trade, overnight, sub,
};
use crate::ops_d2::bond_fields;
use quantforge_core::error::{Result, fail};
use quantforge_core::json::{Json, obj};
use quantforge_core::risk_curve::{self, Bump, KeyMode, Product, Scheme};

fn product(i: &Inputs) -> Result<Product> {
    let p = sub(i, "product")?;
    match p.str("kind")? {
        "OIS" => Ok(Product::Ois(ois_trade(&p)?)),
        "BOND" => Ok(Product::Bond {
            bond: bond_fields(&sub(&p, "bond")?)?,
            settlement: p.date("settlement")?,
            notional: p.f64("notional")?,
        }),
        _ => p.fail("kind", "unknown product kind"),
    }
}

/// `bump_bp` (default 1) and `scheme` (default `CENTRAL`), read without the `E_DOMAIN` check.
fn bump_inputs(i: &Inputs) -> Result<(f64, Scheme)> {
    let bp = i.f64_or("bump_bp", 1.0)?;
    let scheme = match i.opt("scheme").map(|_| i.str("scheme")).transpose()? {
        None | Some("CENTRAL") => Scheme::Central,
        Some("FORWARD") => Scheme::Forward,
        Some(_) => return i.fail("scheme", "unknown scheme"),
    };
    Ok((bp, scheme))
}

/// `key_dates`: `null` or absent is `None`; anything else must be an array of dates.
fn key_dates(i: &Inputs) -> Result<Option<Vec<quantforge_core::dates::Date>>> {
    match i.opt("key_dates") {
        None | Some(Json::Null) => Ok(None),
        Some(_) => Ok(Some(i.dates("key_dates")?)),
    }
}

pub fn dispatch(op: &str, i: &Inputs) -> Result<Outcome> {
    match op {
        "risk.curve.par" => {
            let c = overnight(i, "convention")?;
            let (t, q, m) = (i.date("as_of")?, ois_quotes(i)?, interpolation(i)?);
            let (p, (bp, scheme)) = (product(i)?, bump_inputs(i)?);
            i.gate()?;
            let r = risk_curve::par(&c, t, &q, m, &p, Bump::new(bp, scheme)?)?;
            plain(obj([
                ("value", r.value.into()),
                ("par_dv01", r.par_dv01.into()),
                ("par_buckets", r.par_buckets.into()),
            ]))
        }
        "risk.curve.key_rate" => {
            let curve = curve_input(i, "curve")?;
            let mode = i.str("mode")?;
            if !["TRIANGULAR", "PILLAR"].contains(&mode) {
                return i.fail("mode", "unknown mode");
            }
            let keys = key_dates(i)?;
            let (p, (bp, scheme)) = (product(i)?, bump_inputs(i)?);
            i.gate()?;
            let bump = Bump::new(bp, scheme)?;
            let mode = match (mode, keys) {
                ("TRIANGULAR", Some(k)) => KeyMode::Triangular(k),
                ("PILLAR", None) => KeyMode::Pillar,
                (_, k) => {
                    // After bump_bp and notional: E_DOMAIN outranks E_INPUT.
                    risk_curve::check_notional(&p)?;
                    return fail(
                        "E_INPUT",
                        if k.is_some() {
                            "key_dates must be null in PILLAR mode"
                        } else {
                            "TRIANGULAR needs key_dates"
                        },
                    );
                }
            };
            let r = risk_curve::key_rate(&curve, &mode, &p, bump)?;
            plain(obj([
                ("value", r.value.into()),
                ("key_rates", r.key_rates.into()),
                ("zero_dv01", r.zero_dv01.into()),
            ]))
        }
        "risk.curve.jacobian" => {
            let c = overnight(i, "convention")?;
            let (t, q, m) = (i.date("as_of")?, ois_quotes(i)?, interpolation(i)?);
            let bp = i.f64_or("bump_bp", 1.0)?;
            i.gate()?;
            let r = risk_curve::jacobian(&c, t, &q, m, bp)?;
            let dates: Vec<String> = r.pillar_dates.iter().map(ToString::to_string).collect();
            let rows: Vec<Json> = r.jacobian.into_iter().map(Json::from).collect();
            plain(obj([
                ("pillar_dates", dates.into()),
                ("zero_rates", r.zero_rates.into()),
                ("jacobian", rows.into()),
            ]))
        }
        "risk.pnl.explain" => {
            let c = overnight(i, "convention")?;
            let (t, m) = (i.date("as_of")?, interpolation(i)?);
            let (s, e) = (
                ois_quotes_at(i, "quotes_start")?,
                ois_quotes_at(i, "quotes_end")?,
            );
            let (p, bp) = (product(i)?, i.f64_or("bump_bp", 1.0)?);
            i.gate()?;
            let r = risk_curve::pnl_explain(&c, t, m, &s, &e, &p, bp)?;
            plain(obj([
                ("value_start", r.value_start.into()),
                ("value_end", r.value_end.into()),
                ("full_pnl", r.full_pnl.into()),
                ("par_buckets", r.par_buckets.into()),
                ("risk_pnl", r.risk_pnl.into()),
                ("gross_risk_pnl", r.gross_risk_pnl.into()),
                ("unexplained", r.unexplained.into()),
                ("threshold", r.threshold.into()),
                ("explained", r.explained.into()),
            ]))
        }
        _ => fail(
            "E_UNSUPPORTED_OPERATION",
            format!("{op} is not in this build"),
        ),
    }
}
