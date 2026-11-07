//! Stage C operations: read the inputs, call the library, shape the outputs.
use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use crate::ops_b::{curve_input, items};
use quantforge_core::curve::CurveInput;
use quantforge_core::dates::Date;
use quantforge_core::equity::{self, Outright, ParityQuote};
use quantforge_core::error::{Result, fail};
use quantforge_core::json::{Json, obj};

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
        // next arm
        _ => fail(
            "E_UNSUPPORTED_OPERATION",
            format!("{op} is not in this build"),
        ),
    }
}
