//! `credit.*` operations: read the inputs, call the library, shape the outputs.
use super::core::kind;
use super::eq::items;
use super::rates::curve_input;
use super::rates::sub;
use super::rates::tenor;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::credit;
use quantforge_core::credit::CdsTrade;
use quantforge_core::credit::Hazard;
use quantforge_core::credit_options;
use quantforge_core::curve::Curve;
use quantforge_core::curve::CurveInput;
use quantforge_core::curve::Interpolation;
use quantforge_core::dates::Date;
use quantforge_core::error::Result;
use quantforge_core::error::fail;
use quantforge_core::json::Json;
use quantforge_core::json::obj;

super::registry! {
(op, i)
        "credit.cds.price" => {
            let (t, d) = (i.date("trade_date")?, curve_input(i, "discount")?);
            let h = hazard_input(i, "hazard")?;
            let r = i.f64("recovery")?;
            let x = sub(i, "trade")?;
            let trade = CdsTrade {
                maturity: x.date("maturity")?,
                coupon: x.f64("coupon")?,
                notional: x.f64("notional")?,
                buy: match x.str("side")? {
                    "BUY_PROTECTION" => true,
                    "SELL_PROTECTION" => false,
                    _ => return x.fail("side", "unknown side"),
                },
            };
            let digital = match i.str("payout")? {
                "STANDARD" => false,
                "DIGITAL" => true,
                _ => return i.fail("payout", "unknown payout"),
            };
            i.gate()?;
            let (c, pil) = credit_discount(&d)?;
            let h = Hazard::new(h.0, &h.1)?;
            let p = credit::price(t, &c, &pil, &h, r, &trade, digital)?;
            plain(obj([
                ("pv", p.pv.into()),
                ("upfront", p.upfront.into()),
                ("accrued", p.accrued.into()),
                ("par_spread", p.par_spread.into()),
                ("protection_leg", p.protection_leg.into()),
                ("rpv01", p.rpv01.into()),
            ]))
        },
        "credit.cds.bootstrap" => {
            let (t, d) = (i.date("trade_date")?, curve_input(i, "discount")?);
            let (r, q) = (i.f64("recovery")?, cds_quotes(i)?);
            i.gate()?;
            let (c, pil) = credit_discount(&d)?;
            let h = credit::bootstrap(t, &c, &pil, r, &q)?;
            plain(obj([("pillars", survival_json(&h))]))
        },
        "credit.index.intrinsic" => {
            let (t, d) = (i.date("trade_date")?, curve_input(i, "discount")?);
            let mut names = Vec::new();
            for n in items(i, "names")? {
                names.push((
                    hazard_input(&n, "hazard")?,
                    n.f64("recovery")?,
                    n.f64("weight")?,
                ));
            }
            let x = sub(i, "trade")?;
            let (m, cpn) = (x.date("maturity")?, x.f64("coupon")?);
            let quoted = i.f64("quoted_upfront")?;
            i.gate()?;
            let (c, pil) = credit_discount(&d)?;
            if names.is_empty() {
                return fail("E_INPUT", "no names");
            }
            let mut built = Vec::new();
            for (h, r, w) in names {
                built.push((Hazard::new(h.0, &h.1)?, r, w));
            }
            let (ups, intrinsic) = credit::index_intrinsic(t, &c, &pil, &built, m, cpn)?;
            plain(obj([
                ("intrinsic_upfront", intrinsic.into()),
                ("basis", (quoted - intrinsic).into()),
                ("name_upfronts", ups.into()),
            ]))
        },
        "credit.curve.composite" => {
            let (t, d) = (i.date("trade_date")?, curve_input(i, "discount")?);
            let r = i.f64("recovery")?;
            let mut cons = Vec::new();
            for c in items(i, "constituents")? {
                cons.push((cds_quotes(&c)?, c.f64("weight")?));
            }
            let scale = i.f64("scale")?;
            i.gate()?;
            let (c, pil) = credit_discount(&d)?;
            let spreads = credit::composite_spreads(&cons, scale)?;
            let h = credit::bootstrap(t, &c, &pil, r, &spreads)?;
            let s: Vec<f64> = spreads.iter().map(|x| x.1).collect();
            plain(obj([("spreads", s.into()), ("pillars", survival_json(&h))]))
        },
        "credit.cdsoption.price" => {
            let (o, v) = (cds_option(i)?, i.f64("vol")?);
            let p = credit_options::cds_option_price(&o, v)?;
            plain(obj([
                ("price", p.price.into()),
                ("forward_spread", p.forward_spread.into()),
                ("risky_annuity", p.risky_annuity.into()),
                ("front_end_protection", p.front_end_protection.into()),
            ]))
        },
        "credit.cdsoption.implied_vol" => {
            let (o, p) = (cds_option(i)?, i.f64("premium")?);
            plain(obj([(
                "vol",
                credit_options::cds_option_implied_vol(&o, p)?.into(),
            )]))
        },
        "credit.copula.joint_default" => {
            let student = match i.str("copula")? {
                "GAUSSIAN" => false,
                "STUDENT_T" => true,
                _ => return i.fail("copula", "must be GAUSSIAN or STUDENT_T"),
            };
            let (p, rho) = (i.reals("default_probabilities")?, i.f64("correlation")?);
            let nu = i.opt_f64("degrees_of_freedom")?;
            i.gate()?;
            if p.len() != 2 {
                return fail("E_INPUT", "default_probabilities must hold two values");
            }
            if student && nu.is_none() {
                return fail("E_INPUT", "STUDENT_T needs degrees_of_freedom");
            }
            let (j, dc) =
                credit_options::joint_default(p[0], p[1], rho, if student { nu } else { None })?;
            plain(obj([
                ("joint_default_probability", j.into()),
                ("default_correlation", dc.into()),
            ]))
        },
        "credit.lhp.tranche_loss" => {
            let (p, a, d) = (lhp_pool(i)?, i.f64("attachment")?, i.f64("detachment")?);
            plain(obj([(
                "expected_loss_fraction",
                credit_options::tranche_loss(&p, a, d)?.into(),
            )]))
        },
        "credit.lhp.loss_cdf" => {
            let (p, x) = (lhp_pool(i)?, i.reals("losses")?);
            i.gate()?;
            if x.is_empty() {
                return fail("E_INPUT", "losses must not be empty");
            }
            plain(obj([("cdf", credit_options::loss_cdf(&p, &x)?.into())]))
        }
}

pub(crate) type HazardInput = (Date, Vec<(Date, f64)>);

pub(crate) fn hazard_input(i: &Inputs, k: &str) -> Result<HazardInput> {
    let h = sub(i, k)?;
    let mut p = Vec::new();
    for x in items(&h, "pillars")? {
        p.push((x.date("date")?, x.f64("survival")?));
    }
    Ok((h.date("as_of")?, p))
}

pub(crate) fn cds_quotes(i: &Inputs) -> Result<Vec<((i64, char), f64)>> {
    items(i, "quotes")?
        .iter()
        .map(|q| Ok((tenor(q, "tenor")?, q.f64("spread")?)))
        .collect()
}

/// Every `credit.*` operation: a discount curve other than `LOG_LINEAR_DF` is `E_INPUT`, before
/// any other rule check (ruling R1-4).
pub(crate) fn credit_discount(c: &CurveInput) -> Result<(Curve, Vec<Date>)> {
    if c.interpolation != Interpolation::LogLinearDf {
        return fail("E_INPUT", "credit discount curves are LOG_LINEAR_DF");
    }
    Ok((Curve::new(c)?, c.pillars.iter().map(|p| p.0).collect()))
}

pub(crate) fn survival_json(h: &Hazard) -> Json {
    let rows: Vec<Json> = h
        .pillars()
        .iter()
        .map(|(d, s)| obj([("date", d.to_string().into()), ("survival", (*s).into())]))
        .collect();
    rows.into()
}

pub(crate) fn cds_option(i: &Inputs) -> Result<credit_options::CdsOption> {
    Ok(credit_options::CdsOption {
        as_of: i.date("as_of")?,
        expiry: i.date("expiry")?,
        maturity: i.date("maturity")?,
        rate: i.f64("rate")?,
        hazard_rate: i.f64("hazard_rate")?,
        recovery: i.f64("recovery")?,
        payer: kind(i, "PAYER", "RECEIVER")?,
        strike: i.f64("strike")?,
        notional: i.f64("notional")?,
        knock_out: i.bool("knock_out")?,
    })
}

pub(crate) fn lhp_pool(i: &Inputs) -> Result<credit_options::Pool> {
    Ok(credit_options::Pool {
        default_probability: i.f64("default_probability")?,
        correlation: i.f64("correlation")?,
        recovery: i.f64("recovery")?,
    })
}
