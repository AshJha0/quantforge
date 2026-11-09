//! `infl.*` operations: read the inputs, call the library, shape the outputs.
use super::bond::bond;
use super::core::kind;
use super::eq::items;
use super::rates::curve_input;
use super::rates::sub;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::curve::Curve;
use quantforge_core::dates::Date;
use quantforge_core::error::Result;
use quantforge_core::inflation;
use quantforge_core::inflation::CpiCurve;
use quantforge_core::inflation::Zcis;
use quantforge_core::inflation::month_index;
use quantforge_core::json::Json;
use quantforge_core::json::obj;
use quantforge_core::rates_vol;

super::registry! {
(op, i)
        "infl.curve.cpi" => {
            let c = cpi_input(i)?;
            let mut months = Vec::new();
            for v in i.array("months")? {
                match v.as_str().and_then(month_of) {
                    Some(m) => months.push(m),
                    None => return i.fail("months", "expected YYYY-MM"),
                }
            }
            i.gate()?;
            let c = c.build()?;
            let v = months
                .iter()
                .map(|m| c.cpi(*m))
                .collect::<Result<Vec<_>>>()?;
            plain(obj([("cpi", v.into())]))
        },
        "infl.zcis.pv" => {
            let (c, d) = (cpi_input(&sub(i, "curve")?)?, curve_input(i, "discount")?);
            let t = sub(i, "trade")?;
            let trade = Zcis {
                years: t.int("years")?,
                fixed_rate: t.f64("fixed_rate")?,
                notional: t.f64("notional")?,
                receive_inflation: match t.str("side")? {
                    "RECEIVE_INFLATION" => true,
                    "PAY_INFLATION" => false,
                    _ => return t.fail("side", "unknown side"),
                },
                payment_date: t.date("payment_date")?,
            };
            i.gate()?;
            let (pv, r) = inflation::zcis_pv(&c.build()?, &Curve::new(&d)?, &trade)?;
            plain(obj([("pv", pv.into()), ("index_ratio", r.into())]))
        },
        "infl.linker.price" => {
            let (b, s) = (bond(i)?, i.date("settlement")?);
            let (y, base) = (i.f64("real_yield")?, i.f64("base_ref_cpi")?);
            let mut fx = Vec::new();
            for f in items(i, "cpi_fixings")? {
                let Some(m) = month_of(f.str("month")?) else {
                    return f.fail("month", "expected YYYY-MM");
                };
                fx.push((m, f.f64("value")?));
            }
            i.gate()?;
            let p = inflation::linker_price(&b, s, y, base, &fx)?;
            plain(obj([
                ("ref_cpi", p.ref_cpi.into()),
                ("index_ratio", p.index_ratio.into()),
                ("real_clean", p.real_clean.into()),
                ("real_accrued", p.real_accrued.into()),
                ("nominal_clean", p.nominal_clean.into()),
                ("nominal_accrued", p.nominal_accrued.into()),
            ]))
        },
        "infl.linker.price_curve" => {
            let (b, s, base) = (bond(i)?, i.date("settlement")?, i.f64("base_ref_cpi")?);
            let (c, d) = (cpi_input(&sub(i, "curve")?)?, curve_input(i, "discount")?);
            i.gate()?;
            let v = inflation::linker_price_curve(&b, s, base, &c.build()?, &Curve::new(&d)?)?;
            plain(obj([("nominal_dirty", v.into())]))
        },
        "infl.cap.yoy_price" => {
            let (normal, cap) = (model(i)?, kind(i, "CAP", "FLOOR")?);
            let (k, n) = (i.f64("strike")?, i.f64("notional")?);
            let periods = items(i, "periods")?
                .iter()
                .map(|p| {
                    Ok(rates_vol::YoyPeriod {
                        accrual: p.f64("accrual")?,
                        discount_factor: p.f64("discount_factor")?,
                        yoy_forward: p.f64("yoy_forward")?,
                        expiry_years: p.f64("expiry_years")?,
                        vol: p.f64("vol")?,
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            i.gate()?;
            let c = rates_vol::yoy_caplets(normal, cap, k, n, &periods)?;
            let total: f64 = c.iter().sum();
            plain(obj([("caplets", c.into()), ("price", total.into())]))
        },
        "infl.cap.zc_price" => {
            let z = rates_vol::ZeroCoupon {
                normal: model(i)?,
                cap: kind(i, "CAP", "FLOOR")?,
                forward_index_ratio: i.f64("forward_index_ratio")?,
                years: i.f64("years")?,
                strike: i.f64("strike")?,
                discount_factor: i.f64("discount_factor")?,
                vol: i.f64("vol")?,
                notional: i.f64("notional")?,
            };
            let (p, r) = rates_vol::zc_cap(&z)?;
            plain(obj([("price", p.into()), ("strike_ratio", r.into())]))
        }
}

pub(crate) fn month_of(s: &str) -> Option<i64> {
    let d = Date::parse(&format!("{s}-01"))?;
    (s.len() == 7).then(|| month_index(d.y, d.m))
}

pub(crate) struct CpiInput {
    base: i64,
    base_cpi: f64,
    quotes: Vec<(i64, f64)>,
    seasonality: Option<Vec<f64>>,
}

impl CpiInput {
    pub(crate) fn build(&self) -> Result<CpiCurve> {
        CpiCurve::new(
            self.base,
            self.base_cpi,
            &self.quotes,
            self.seasonality.as_deref(),
        )
    }
}

/// The curve fields; `seasonality` is a required key that may be `null`.
pub(crate) fn cpi_input(i: &Inputs) -> Result<CpiInput> {
    let Some(base) = month_of(i.str("base_month")?) else {
        return i.fail("base_month", "expected YYYY-MM");
    };
    let base_cpi = i.f64("base_cpi")?;
    let mut quotes = Vec::new();
    for q in items(i, "quotes")? {
        quotes.push((q.int("years")?, q.f64("rate")?));
    }
    let seasonality = match i.0.get("seasonality") {
        None => return i.fail("seasonality", "is required"),
        Some(Json::Null) => None,
        _ => Some(i.reals("seasonality")?),
    };
    Ok(CpiInput {
        base,
        base_cpi,
        quotes,
        seasonality,
    })
}

pub(crate) fn model(i: &Inputs) -> Result<bool> {
    match i.str("model")? {
        "BLACK_76" => Ok(false),
        "BACHELIER" => Ok(true),
        _ => i.fail("model", "must be BLACK_76 or BACHELIER"),
    }
}
