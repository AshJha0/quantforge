//! Stage C operations: read the inputs, call the library, shape the outputs.
use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use crate::ops_b::{curve_input, items, snapshot_id};
use quantforge_core::curve::CurveInput;
use quantforge_core::dates::Date;
use quantforge_core::equity::{self, Outright, ParityQuote};
use quantforge_core::error::{Result, fail};
use quantforge_core::json::{Json, obj};
use quantforge_core::black;
use quantforge_core::greeks;
use quantforge_core::ois::Valuation;
use quantforge_core::stats::{normal_cdf, normal_pdf};
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

/// True for `BUY`.
fn trade_side(i: &Inputs) -> Result<f64> {
    match i.str("side")? {
        "BUY" => Ok(1.0),
        "SELL" => Ok(-1.0),
        _ => i.fail("side", "unknown side"),
    }
}

fn equity_valuation(pv: f64, currency: &str, id: Option<String>, as_of: Date) -> Json {
    Valuation {
        pv,
        currency: currency.to_string(),
        model: "BLACK_76_EQUITY",
        data_version: id,
        conventions: "EQUITY_FORWARD".to_string(),
        as_of,
    }
    .to_json()
}

fn equity_price(i: &Inputs) -> Result<Outcome> {
    let f = forward_inputs(i)?;
    let call = option_type(i)?;
    let (k, v, q) = (i.f64("strike")?, i.f64("vol")?, i.f64("quantity")?);
    let sign = trade_side(i)?;
    let currency = i.str("currency")?;
    no_null(i, "snapshot_id")?;
    let id = snapshot_id(i)?;
    i.gate()?;
    let r = outright(&f)?;
    let t = (f.expiry.serial() - f.as_of.serial()) as f64 / 365.0;
    if t == 0.0 || v <= 0.0 || k <= 0.0 || q <= 0.0 {
        return fail("E_DOMAIN", "expiry, vol, strike or quantity is out of domain");
    }
    let (fw, d, c) = (r.forward, r.discount_factor, r.carry_factor);
    let p = black::phi(call);
    let d1 = black::d1_d2(fw, k, v, t).0;
    let root = t.sqrt();
    let pv = sign * q * black::black(call, fw, k, v, t, d);
    plain(obj([
        ("valuation", equity_valuation(pv, currency, id, f.as_of)),
        ("forward", fw.into()),
        ("delta", (sign * q * d * p * normal_cdf(p * d1) / c).into()),
        ("gamma", (sign * q * d * normal_pdf(d1) / (fw * v * root * c * c)).into()),
        ("vega", (sign * q * d * fw * normal_pdf(d1) * root).into()),
    ]))
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
        "vol.equity.price" => equity_price(i),
        "risk.vol.greeks" => {
            let (o, v) = (option_inputs(i)?, i.f64("vol")?);
            let g = greeks::analytic(&o, v)?;
            plain(obj([
                ("price", g.price.into()),
                ("delta", g.delta.into()),
                ("gamma", g.gamma.into()),
                ("vega", g.vega.into()),
                ("theta", g.theta.into()),
                ("rho", g.rho.into()),
                ("vanna", g.vanna.into()),
                ("volga", g.volga.into()),
            ]))
        }
        "risk.vol.bump_greeks" => {
            let (o, v) = (option_inputs(i)?, i.f64("vol")?);
            let [delta, gamma, vega, volga, vanna] = greeks::bumped(&o, v)?;
            plain(obj([
                ("delta", delta.into()),
                ("gamma", gamma.into()),
                ("vega", vega.into()),
                ("volga", volga.into()),
                ("vanna", vanna.into()),
            ]))
        }
        // next arm
        _ => fail(
            "E_UNSUPPORTED_OPERATION",
            format!("{op} is not in this build"),
        ),
    }
}
