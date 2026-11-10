//! `bond.*` operations: read the inputs, call the library, shape the outputs.
use super::calib::optional_reals;
use super::eq::items;
use super::rates::curve_input;
use super::rates::sub;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::bonds;
use quantforge_core::bonds::Bond;
use quantforge_core::bonds::Frn;
use quantforge_core::curve::Curve;
use quantforge_core::dates::Date;
use quantforge_core::error::Result;
use quantforge_core::json::Json;
use quantforge_core::json::obj;

super::registry! {
(op, i)
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
        },
        "bond.yield.from_price" => {
            let (b, s, c) = (bond(i)?, i.date("settlement")?, i.f64("clean_price")?);
            let (y, d, a) = bonds::yield_from_price(&b, s, c)?;
            plain(obj([
                ("yield", y.into()),
                ("dirty", d.into()),
                ("accrued", a.into()),
            ]))
        },
        "bond.price.from_curve" => {
            let (b, s, c) = (bond(i)?, i.date("settlement")?, curve_input(i, "curve")?);
            i.gate()?;
            let (d, a) = bonds::price_from_curve(&b, s, &Curve::new(&c)?)?;
            plain(price_json(d, a))
        },
        "bond.spread.z" => {
            let (b, s, c) = (bond(i)?, i.date("settlement")?, curve_input(i, "curve")?);
            let p = i.f64("clean_price")?;
            i.gate()?;
            let z = bonds::z_spread(&b, s, &Curve::new(&c)?, p)?;
            plain(obj([("z_spread", z.into())]))
        },
        "bond.spread.asset_swap" => {
            let (b, s, c) = (bond(i)?, i.date("settlement")?, curve_input(i, "curve")?);
            let p = i.f64("dirty_price")?;
            i.gate()?;
            let (spread, annuity) = bonds::asset_swap(&b, s, &Curve::new(&c)?, p)?;
            plain(obj([
                ("spread", spread.into()),
                ("annuity", annuity.into()),
            ]))
        },
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
        },
        "bond.futures.conversion_factor" => {
            let (b, d) = (bond(i)?, month_start(i, "delivery_month")?);
            let notional = i.f64("notional_coupon")?;
            let whole_months = match i.opt("contract") {
                None | Some(Json::Null) => false,
                Some(_) => match i.str("contract")? {
                    "TWO_YEAR" | "THREE_YEAR" | "FIVE_YEAR" => true,
                    "TEN_YEAR" | "ULTRA_TEN_YEAR" | "BOND" | "ULTRA_BOND" => false,
                    _ => return i.fail("contract", "unknown contract"),
                },
            };
            let cf = bonds::conversion_factor(&b, d, notional, whole_months)?;
            plain(obj([("conversion_factor", cf.into())]))
        },
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
        },
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
}

pub(crate) fn bond_fields(b: &Inputs) -> Result<Bond> {
    let (m, c, f) = (b.date("maturity")?, b.f64("coupon")?, b.int("frequency")?);
    if ![1, 2, 4].contains(&f) {
        return b.fail("frequency", "must be 1, 2 or 4");
    }
    Ok(Bond::new(m, c, f))
}

pub(crate) fn bond(i: &Inputs) -> Result<Bond> {
    bond_fields(&sub(i, "bond")?)
}

pub(crate) fn month_start(i: &Inputs, k: &str) -> Result<Date> {
    let s = i.str(k)?;
    match Date::parse(&format!("{s}-01")) {
        Some(d) if s.len() == 7 => Ok(d),
        _ => i.fail(k, "expected YYYY-MM"),
    }
}

pub(crate) fn price_json(dirty: f64, accrued: f64) -> Json {
    obj([
        ("dirty", dirty.into()),
        ("accrued", accrued.into()),
        ("clean", (dirty - accrued).into()),
    ])
}
