//! Stage C operations: read the inputs, call the library, shape the outputs.
use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use crate::ops_b::{curve_input, items};
use quantforge_core::curve::CurveInput;
use quantforge_core::dates::Date;
use quantforge_core::equity::{self, Outright, ParityQuote};
use quantforge_core::error::{Result, fail};
use quantforge_core::json::{Json, obj};
use quantforge_core::black::{Model, Option_};

/// Ruling C9: the key must be present, and `null` carries meaning.
fn present(i: &Inputs, k: &str) -> Result<()> {
    match i.0.get(k) {
        None => i.fail(k, "is required"),
        _ => Ok(()),
    }
}

struct ForwardInputs {
    spot: f64,
    as_of: Date,
    expiry: Date,
    funding: CurveInput,
    borrow: Option<CurveInput>,
    dividends: Vec<(Date, f64)>,
}

fn forward_inputs(i: &Inputs) -> Result<ForwardInputs> {
    present(i, "borrow_curve")?;
    let mut dividends = Vec::new();
    for d in items(i, "dividends")? {
        dividends.push((d.date("ex_date")?, d.f64("amount")?));
    }
    Ok(ForwardInputs {
        spot: i.f64("spot")?,
        as_of: i.date("as_of")?,
        expiry: i.date("expiry")?,
        funding: curve_input(i, "funding_curve")?,
        borrow: i
            .opt("borrow_curve")
            .map(|_| curve_input(i, "borrow_curve"))
            .transpose()?,
        dividends,
    })
}

fn outright(f: &ForwardInputs) -> Result<Outright> {
    equity::outright(
        f.spot,
        f.as_of,
        f.expiry,
        &f.funding,
        f.borrow.as_ref(),
        &f.dividends,
    )
}

fn parity_quotes(i: &Inputs) -> Result<Vec<ParityQuote>> {
    items(i, "quotes")?
        .iter()
        .map(|q| {
            Ok(ParityQuote {
                strike: q.f64("strike")?,
                call_bid: q.f64("call_bid")?,
                call_ask: q.f64("call_ask")?,
                put_bid: q.f64("put_bid")?,
                put_ask: q.f64("put_ask")?,
            })
        })
        .collect()
}

/// Ruling C9: an optional key may be absent, but `null` is `E_SCHEMA`.
fn no_null(i: &Inputs, k: &str) -> Result<()> {
    match i.0.get(k) {
        Some(Json::Null) => i.fail(k, "null is not allowed here"),
        _ => Ok(()),
    }
}

fn option_type(i: &Inputs) -> Result<bool> {
    match i.str("option_type")? {
        "CALL" => Ok(true),
        "PUT" => Ok(false),
        _ => i.fail("option_type", "unknown option type"),
    }
}

/// Keys of other models are `E_SCHEMA`, whatever their value.
fn only(i: &Inputs, keys: &[&str]) -> Result<()> {
    for k in ["spot", "rate", "yield", "forward", "discount_factor", "shift"] {
        if !keys.contains(&k) && i.0.get(k).is_some() {
            return i.fail(k, "not an input of this model");
        }
    }
    Ok(())
}

fn option_inputs(i: &Inputs) -> Result<Option_> {
    let model = match i.str("model")? {
        "BLACK_SCHOLES" => {
            only(i, &["spot", "rate", "yield"])?;
            Model::BlackScholes {
                spot: i.f64("spot")?,
                rate: i.f64("rate")?,
                dividend: i.f64("yield")?,
            }
        }
        "BLACK_76" => {
            only(i, &["forward", "discount_factor", "shift"])?;
            no_null(i, "shift")?;
            Model::Black76 {
                forward: i.f64("forward")?,
                discount: i.f64("discount_factor")?,
                shift: i.f64_or("shift", 0.0)?,
            }
        }
        "BACHELIER" => {
            only(i, &["forward", "discount_factor"])?;
            Model::Bachelier {
                forward: i.f64("forward")?,
                discount: i.f64("discount_factor")?,
            }
        }
        _ => return i.fail("model", "unknown model"),
    };
    Ok(Option_ {
        model,
        call: option_type(i)?,
        strike: i.f64("strike")?,
        t: i.f64("expiry_years")?,
    })
}

pub fn dispatch(op: &str, i: &Inputs) -> Result<Outcome> {
    match op {
        "eq.forward.outright" => {
            let f = forward_inputs(i)?;
            i.gate()?;
            let r = outright(&f)?;
            plain(obj([
                ("forward", r.forward.into()),
                ("discount_factor", r.discount_factor.into()),
                ("carry_factor", r.carry_factor.into()),
                ("pv_dividends", r.pv_dividends.into()),
            ]))
        }
        "eq.forward.flat" => {
            let mut d = Vec::new();
            for v in items(i, "dividends")? {
                d.push((v.f64("time_years")?, v.f64("amount")?));
            }
            let (s, r, b, t) = (
                i.f64("spot")?,
                i.f64("rate")?,
                i.f64("borrow")?,
                i.f64("expiry_years")?,
            );
            i.gate()?;
            plain(obj([("forward", equity::flat(s, r, b, t, &d)?.into())]))
        }
        "eq.forward.parity" => {
            present(i, "discount_factor")?;
            let q = parity_quotes(i)?;
            let d = i.opt_f64("discount_factor")?;
            i.gate()?;
            let r = equity::parity(&q, d)?;
            plain(obj([
                ("forward", r.forward.into()),
                ("discount_factor", r.discount_factor.into()),
                ("max_residual", r.max_residual.into()),
                ("outside_spread", r.outside_spread.into()),
            ]))
        }
        "vol.option.price" => {
            let (o, v) = (option_inputs(i)?, i.f64("vol")?);
            plain(obj([
                ("price", o.price(v)?.into()),
                ("forward", o.unshifted_forward().into()),
            ]))
        }
        "vol.option.implied" => {
            let (o, p) = (option_inputs(i)?, i.f64("price")?);
            plain(obj([("vol", o.implied(p)?.into())]))
        }
        // next arm
        _ => fail(
            "E_UNSUPPORTED_OPERATION",
            format!("{op} is not in this build"),
        ),
    }
}
