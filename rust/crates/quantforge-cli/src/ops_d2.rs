//! Stage D wave 2 and 3 operations: read the inputs, call the library, shape the outputs.
use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use crate::ops_b::{curve_input, items, sub};
use quantforge_core::bonds::{self, Bond, Frn};
use quantforge_core::curve::Curve;
use quantforge_core::dates::Date;
use quantforge_core::error::{Result, fail};
use quantforge_core::json::{Json, obj};

pub(crate) fn bond_fields(b: &Inputs) -> Result<Bond> {
    let (m, c, f) = (b.date("maturity")?, b.f64("coupon")?, b.int("frequency")?);
    if ![1, 2, 4].contains(&f) {
        return b.fail("frequency", "must be 1, 2 or 4");
    }
    Ok(Bond::new(m, c, f))
}

fn bond(i: &Inputs) -> Result<Bond> {
    bond_fields(&sub(i, "bond")?)
}

/// Required key whose value may be `null`.
pub(crate) fn nullable_f64(i: &Inputs, k: &str) -> Result<Option<f64>> {
    match i.0.get(k) {
        None => i.fail(k, "is required"),
        Some(Json::Null) => Ok(None),
        _ => Ok(Some(i.f64(k)?)),
    }
}

/// Optional, but `null` is `E_SCHEMA` (ruling D10).
pub(crate) fn optional_reals(i: &Inputs, k: &str) -> Result<Option<Vec<f64>>> {
    match i.0.get(k) {
        None => Ok(None),
        Some(Json::Null) => i.fail(k, "must not be null"),
        _ => Ok(Some(i.reals(k)?)),
    }
}

fn month_start(i: &Inputs, k: &str) -> Result<Date> {
    let s = i.str(k)?;
    match Date::parse(&format!("{s}-01")) {
        Some(d) if s.len() == 7 => Ok(d),
        _ => i.fail(k, "expected YYYY-MM"),
    }
}

fn price_json(dirty: f64, accrued: f64) -> Json {
    obj([
        ("dirty", dirty.into()),
        ("accrued", accrued.into()),
        ("clean", (dirty - accrued).into()),
    ])
}

pub fn dispatch(op: &str, i: &Inputs) -> Result<Outcome> {
    match op {
        "bond.price.from_yield" => {
            let (b, s, y) = (bond(i)?, i.date("settlement")?, i.f64("yield")?);
            let p = bonds::price_from_yield(&b, s, y)?;
            plain(obj([
                ("dirty", p.dirty.into()),
                ("accrued", p.accrued.into()),
                ("clean", p.clean.into()),
                ("modified_duration", p.modified_duration.into()),
                ("macaulay_duration", p.macaulay_duration.into()),
                ("convexity", p.convexity.into()),
            ]))
        }
        "bond.yield.from_price" => {
            let (b, s, c) = (bond(i)?, i.date("settlement")?, i.f64("clean_price")?);
            let (y, d, a) = bonds::yield_from_price(&b, s, c)?;
            plain(obj([
                ("yield", y.into()),
                ("dirty", d.into()),
                ("accrued", a.into()),
            ]))
        }
        "bond.price.from_curve" => {
            let (b, s, c) = (bond(i)?, i.date("settlement")?, curve_input(i, "curve")?);
            i.gate()?;
            let (d, a) = bonds::price_from_curve(&b, s, &Curve::new(&c)?)?;
            plain(price_json(d, a))
        }
        "bond.spread.z" => {
            let (b, s, c) = (bond(i)?, i.date("settlement")?, curve_input(i, "curve")?);
            let p = i.f64("clean_price")?;
            i.gate()?;
            let z = bonds::z_spread(&b, s, &Curve::new(&c)?, p)?;
            plain(obj([("z_spread", z.into())]))
        }
        "bond.spread.asset_swap" => {
            let (b, s, c) = (bond(i)?, i.date("settlement")?, curve_input(i, "curve")?);
            let p = i.f64("dirty_price")?;
            i.gate()?;
            let (spread, annuity) = bonds::asset_swap(&b, s, &Curve::new(&c)?, p)?;
            plain(obj([
                ("spread", spread.into()),
                ("annuity", annuity.into()),
            ]))
        }
        "bond.frn.price" => {
            let f = i.int("frequency")?;
            if ![1, 2, 4].contains(&f) {
                return i.fail("frequency", "must be 1, 2 or 4");
            }
            let n = Frn {
                settlement: i.date("settlement")?,
                maturity: i.date("maturity")?,
                frequency: f,
                current_rate: i.f64("current_rate")?,
                margin: i.f64("margin")?,
                discount_margin: i.f64("discount_margin")?,
            };
            let (d, p) = (curve_input(i, "discount")?, curve_input(i, "projection")?);
            i.gate()?;
            let (dirty, a) = bonds::frn_price(&n, &Curve::new(&d)?, &Curve::new(&p)?)?;
            plain(price_json(dirty, a))
        }
        "repo.forward" => {
            let (b, s, e) = (bond(i)?, i.date("start")?, i.date("end")?);
            let (c, r) = (i.f64("clean_price")?, i.f64("repo_rate")?);
            let g = nullable_f64(i, "gc_rate")?;
            let f = bonds::repo_forward(&b, s, e, c, r, g)?;
            plain(obj([
                ("dirty", f.dirty.into()),
                ("forward_dirty", f.forward_dirty.into()),
                ("forward_clean", f.forward_clean.into()),
                ("interest", f.interest.into()),
                ("special_spread", f.special_spread.into()),
                ("specialness_value", f.specialness_value.into()),
            ]))
        }
        "repo.implied_rate" => {
            let (b, s, e) = (bond(i)?, i.date("start")?, i.date("end")?);
            let (c, f) = (i.f64("clean_price")?, i.f64("forward_clean")?);
            let r = bonds::repo_implied_rate(&b, s, e, c, f)?;
            plain(obj([("repo_rate", r.into())]))
        }
        "bond.futures.conversion_factor" => {
            let (b, d) = (bond(i)?, month_start(i, "delivery_month")?);
            let cf = bonds::conversion_factor(&b, d, i.f64("notional_coupon")?)?;
            plain(obj([("conversion_factor", cf.into())]))
        }
        "bond.futures.basis" => {
            let (f, s, d, r) = (
                i.f64("futures_price")?,
                i.date("settlement")?,
                i.date("delivery")?,
                i.f64("repo_rate")?,
            );
            let mut list = Vec::new();
            for b in items(i, "bonds")? {
                let x = bond_fields(&b)?;
                list.push((x, b.f64("clean_price")?, b.f64("conversion_factor")?));
            }
            i.gate()?;
            let (out, ctd) = bonds::futures_basis(f, s, d, r, &list)?;
            let rows: Vec<Json> = out
                .iter()
                .map(|x| {
                    obj([
                        ("invoice", x.invoice.into()),
                        ("gross_basis", x.gross_basis.into()),
                        ("net_basis", x.net_basis.into()),
                        ("implied_repo", x.implied_repo.into()),
                    ])
                })
                .collect();
            plain(obj([("bonds", rows.into()), ("ctd", (ctd as i64).into())]))
        }
        "bond.fit.nelson_siegel" => {
            let (s, tau) = (i.date("settlement")?, i.f64("tau")?);
            let mut list = Vec::new();
            for b in items(i, "bonds")? {
                list.push((bond_fields(&b)?, b.f64("dirty_price")?));
            }
            let w = optional_reals(i, "weights")?;
            i.gate()?;
            let (beta, res) = bonds::fit_nelson_siegel(s, tau, &list, w.as_deref())?;
            plain(obj([
                ("betas", beta.to_vec().into()),
                ("residuals", res.into()),
            ]))
        }
        _ => fail(
            "E_UNSUPPORTED_OPERATION",
            format!("{op} is not in this build"),
        ),
    }
}
