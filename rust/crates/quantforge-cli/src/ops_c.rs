//! Stage C operations: read the inputs, call the library, shape the outputs.
use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use crate::ops_b::{curve_input, items, snapshot_id, sub};
use quantforge_core::curve::CurveInput;
use quantforge_core::dates::Date;
use quantforge_core::equity::{self, Outright, ParityQuote};
use quantforge_core::error::{Result, fail};
use quantforge_core::json::{Json, obj};
use quantforge_core::sabr::{self, Sabr};
use quantforge_core::surface::{Check, Position, Surface};
use quantforge_core::svi::{self, Svi};
use quantforge_core::smile;
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

/// `convention` and `scale`, the latter a key that must be present.
fn delta_scale(i: &Inputs) -> Result<(bool, Option<f64>)> {
    present(i, "scale")?;
    let spot = match i.str("convention")? {
        "FORWARD" => false,
        "SPOT" => true,
        _ => return i.fail("convention", "unknown convention"),
    };
    Ok((spot, i.opt_f64("scale")?))
}

fn svi_json(s: &Svi) -> Json {
    obj([
        ("a", s.a.into()),
        ("b", s.b.into()),
        ("rho", s.rho.into()),
        ("m", s.m.into()),
        ("sigma", s.sigma.into()),
    ])
}

fn rows(m: Vec<Vec<f64>>) -> Json {
    Json::Arr(m.into_iter().map(Into::into).collect())
}

fn opt_weights(i: &Inputs) -> Result<Option<Vec<f64>>> {
    no_null(i, "weights")?;
    i.opt("weights").map(|_| i.reals("weights")).transpose()
}

fn check_json(c: &Check) -> Json {
    let at = |j: usize, i: usize| [("expiry_index", (j as i64).into()), ("k_index", (i as i64).into())];
    let cal: Vec<Json> = c.calendar.iter().map(|&(j, i)| obj(at(j, i))).collect();
    let fly: Vec<Json> = c
        .butterfly
        .iter()
        .map(|&(j, i, kind)| {
            let [a, b] = at(j, i);
            obj([a, b, ("kind", kind.into())])
        })
        .collect();
    let free = cal.is_empty() && fly.is_empty();
    obj([
        ("calendar_violations", cal.into()),
        ("butterfly_violations", fly.into()),
        ("arbitrage_free", free.into()),
    ])
}

fn surface_input(i: &Inputs) -> Result<Surface> {
    let s = sub(i, "surface")?;
    Ok(Surface {
        t: s.reals("expiry_years")?,
        k: s.reals("log_moneyness")?,
        vols: s.matrix("vols")?,
    })
}

fn sabr_inputs(i: &Inputs) -> Result<Sabr> {
    no_null(i, "shift")?;
    Ok(Sabr {
        t: i.f64("expiry_years")?,
        alpha: i.f64("alpha")?,
        beta: i.f64("beta")?,
        rho: i.f64("rho")?,
        nu: i.f64("nu")?,
        forward: i.f64("forward")?,
        shift: i.f64_or("shift", 0.0)?,
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
        "vol.delta.to_strike" | "vol.delta.from_strike" => {
            let (f, v, t) = (i.f64("forward")?, i.f64("vol")?, i.f64("expiry_years")?);
            let call = option_type(i)?;
            let (spot, scale) = delta_scale(i)?;
            if op == "vol.delta.to_strike" {
                let d = i.f64("delta")?;
                let s = smile::delta_scale(spot, scale)?;
                plain(obj([("strike", smile::to_strike(f, v, t, call, d, s)?.into())]))
            } else {
                let k = i.f64("strike")?;
                let s = smile::delta_scale(spot, scale)?;
                plain(obj([("delta", smile::from_strike(f, v, t, call, k, s)?.into())]))
            }
        }
        "vol.smile.rr_bf" => {
            let (f, t) = (i.f64("forward")?, i.f64("expiry_years")?);
            let (atm, rr, bf) = (i.f64("atm_vol")?, i.f64("rr")?, i.f64("bf")?);
            let neutral = match i.str("atm_convention")? {
                "ATM_FORWARD" => false,
                "DELTA_NEUTRAL" => true,
                _ => return i.fail("atm_convention", "unknown convention"),
            };
            let d = i.f64("delta")?;
            let (spot, scale) = delta_scale(i)?;
            let s = smile::delta_scale(spot, scale)?;
            let r = smile::rr_bf(f, t, atm, neutral, rr, bf, d, s)?;
            plain(obj([
                ("atm_strike", r.atm_strike.into()),
                ("call_vol", r.call_vol.into()),
                ("put_vol", r.put_vol.into()),
                ("call_strike", r.call_strike.into()),
                ("put_strike", r.put_strike.into()),
            ]))
        }
        "vol.svi.evaluate" => {
            let p = sub(i, "svi")?;
            let s = Svi {
                a: p.f64("a")?,
                b: p.f64("b")?,
                rho: p.f64("rho")?,
                m: p.f64("m")?,
                sigma: p.f64("sigma")?,
            };
            let (k, t) = (i.reals("log_moneyness")?, i.f64("expiry_years")?);
            i.gate()?;
            s.check()?;
            if t <= 0.0 {
                return fail("E_DOMAIN", "expiry_years must be above 0");
            }
            let w: Vec<f64> = k.iter().map(|&x| s.w(x)).collect();
            let v: Vec<f64> = w.iter().map(|x| (x / t).sqrt()).collect();
            let g: Vec<f64> = k.iter().map(|&x| s.g(x)).collect();
            let min_g = g.iter().copied().fold(f64::INFINITY, f64::min);
            plain(obj([
                ("total_variance", w.into()),
                ("implied_vol", v.into()),
                ("g", g.into()),
                ("min_g", min_g.into()),
                ("butterfly_free", (min_g >= 0.0).into()),
            ]))
        }
        "vol.svi.calibrate" => {
            let (k, w) = (i.reals("log_moneyness")?, i.reals("total_variance")?);
            let q = opt_weights(i)?;
            i.gate()?;
            let r = svi::calibrate(&k, &w, q.as_deref())?;
            plain(obj([("svi", svi_json(&r.svi)), ("rmse", r.rmse.into())]))
        }
        "vol.ssvi.evaluate" => {
            let (rho, eta, gamma) = (i.f64("rho")?, i.f64("eta")?, i.f64("gamma")?);
            let (t, k) = (i.reals("thetas")?, i.reals("log_moneyness")?);
            i.gate()?;
            let r = svi::ssvi_evaluate(rho, eta, gamma, &t, &k)?;
            plain(obj([
                ("total_variance", rows(r.total_variance)),
                ("butterfly_free", r.butterfly_free.into()),
                ("calendar_free", r.calendar_free.into()),
            ]))
        }
        "vol.ssvi.calibrate" => {
            let (t, k) = (i.reals("thetas")?, i.reals("log_moneyness")?);
            let w = i.matrix("total_variance")?;
            i.gate()?;
            let [rho, eta, gamma, rmse] = svi::ssvi_calibrate(&t, &k, &w)?;
            plain(obj([
                ("rho", rho.into()),
                ("eta", eta.into()),
                ("gamma", gamma.into()),
                ("rmse", rmse.into()),
            ]))
        }
        "vol.surface.query" => {
            let s = surface_input(i)?;
            let mut p = Vec::new();
            for x in items(i, "points")? {
                p.push((x.f64("expiry_years")?, x.f64("log_moneyness")?));
            }
            i.gate()?;
            let r = s.query(&p)?;
            let w: Vec<f64> = r.iter().map(|x| x.0).collect();
            let v: Vec<f64> = r.iter().map(|x| x.1).collect();
            plain(obj([("total_variance", w.into()), ("vols", v.into())]))
        }
        "vol.surface.check" => {
            let s = surface_input(i)?;
            i.gate()?;
            let r = s.check()?;
            plain(check_json(&r))
        }
        "risk.vol.surface_vega" => {
            let s = surface_input(i)?;
            let mut p = Vec::new();
            for x in items(i, "positions")? {
                p.push(Position {
                    call: option_type(&x)?,
                    forward: x.f64("forward")?,
                    strike: x.f64("strike")?,
                    discount: x.f64("discount_factor")?,
                    t: x.f64("expiry_years")?,
                    quantity: x.f64("quantity")?,
                });
            }
            i.gate()?;
            let r = s.vega(&p)?;
            plain(obj([
                ("pv", r.pv.into()),
                ("bucket_vega", rows(r.bucket)),
                ("parallel_vega", r.parallel.into()),
                ("bucket_sum", r.bucket_sum.into()),
            ]))
        }
        "vol.sabr.hagan" => {
            let (s, k) = (sabr_inputs(i)?, i.reals("strikes")?);
            i.gate()?;
            plain(obj([("vols", s.hagan(&k)?.into())]))
        }
        "vol.sabr.density" => {
            let (s, k, h) = (sabr_inputs(i)?, i.reals("strikes")?, i.f64("h_strike")?);
            let reject = match i.str("on_negative")? {
                "REPORT" => false,
                "REJECT" => true,
                _ => return i.fail("on_negative", "unknown choice"),
            };
            i.gate()?;
            let (density, min) = s.density(&k, h)?;
            let negative = min < -1e-9;
            if reject && negative {
                return fail("E_ARBITRAGE", "the Hagan density is negative");
            }
            plain(obj([
                ("density", density.into()),
                ("min_density", min.into()),
                ("negative_density", negative.into()),
            ]))
        }
        "vol.sabr.calibrate" => {
            no_null(i, "shift")?;
            let (f, t, beta) = (i.f64("forward")?, i.f64("expiry_years")?, i.f64("beta")?);
            let (k, v) = (i.reals("strikes")?, i.reals("vols")?);
            let shift = i.f64_or("shift", 0.0)?;
            let q = opt_weights(i)?;
            i.gate()?;
            let [alpha, rho, nu, rmse] = sabr::calibrate(f, t, beta, shift, &k, &v, q.as_deref())?;
            plain(obj([
                ("alpha", alpha.into()),
                ("rho", rho.into()),
                ("nu", nu.into()),
                ("rmse", rmse.into()),
            ]))
        }
        "vol.sabr.arbfree" => {
            let (s, k) = (sabr_inputs(i)?, i.reals("strikes")?);
            let (cells, below) = (i.int("cells")?, i.int("cells_below")?);
            let steps = i.int("steps")?;
            i.gate()?;
            let r = sabr::arbfree(&s, cells, below, steps, &k)?;
            plain(obj([
                ("call_prices", r.call_prices.into()),
                ("vols", r.vols.into()),
                ("mass", r.mass.into()),
                ("mean", r.mean.into()),
                ("absorbed", r.absorbed.into()),
                ("min_density", r.min_density.into()),
            ]))
        }
        // next arm
        _ => fail(
            "E_UNSUPPORTED_OPERATION",
            format!("{op} is not in this build"),
        ),
    }
}
