//! `usecase.*` operations: read the inputs, call the library, shape the outputs.
use super::eq::items;
use super::eq::parity_quotes;
use super::fx::fx_leg;
use super::fx::fx_market;
use super::fx::fx_market_input;
use super::rates::curve_input;
use super::rates::ois_trade;
use super::rates::sub;
use super::risk::interpolation;
use super::risk::ois_quotes;
use super::vol::nonempty;
use super::vol::option_type;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::black;
use quantforge_core::black::Model;
use quantforge_core::black::Option_;
use quantforge_core::calendar::parse_tenor;
use quantforge_core::curve::Curve;
use quantforge_core::dates::Date;
use quantforge_core::equity;
use quantforge_core::error::Result;
use quantforge_core::error::fail;
use quantforge_core::fx;
use quantforge_core::json::Json;
use quantforge_core::json::obj;
use quantforge_core::ois::Valuation;
use quantforge_core::risk;
use quantforge_core::stats::normal_cdf;
use quantforge_core::stats::normal_pdf;
use quantforge_core::surface::Surface;
use quantforge_core::svi;
use quantforge_core::svi::Svi;

super::registry! {
(op, i)
        "usecase.option_hedge_lots" => super::hedge::option_hedge_lots(i),
        "usecase.fx_hedge" => {
            let m = fx_market_input(i)?;
            let mut book = Vec::new();
            for t in items(i, "book")? {
                book.push(fx_leg(&t)?);
            }
            let s = i.f64("half_spread")?;
            let [pv, delta, hedge, residual, cost] = fx::hedge_book(&fx_market(i, m)?, &book, s)?;
            plain(obj([
                ("pv", pv.into()),
                ("fx_delta", delta.into()),
                ("hedge_spot_base", hedge.into()),
                ("residual_delta", residual.into()),
                ("hedge_cost", cost.into()),
            ]))
        },
        "usecase.rates_hedge" => {
            let (t, q, m) = (i.date("as_of")?, ois_quotes(i)?, interpolation(i)?);
            let trade = ois_trade(i)?;
            let mut tenors = Vec::new();
            for v in i.array("hedge_tenors")? {
                match v.as_str() {
                    Some(s) => tenors.push(tenor_text(i, "hedge_tenors", s)?),
                    None => return i.fail("hedge_tenors", "expected strings"),
                }
            }
            let (u, h) = (i.f64("hedge_unit_notional")?, i.f64("half_spread_bp")?);
            i.gate()?;
            let r = risk::rates_hedge(t, &q, m, &trade, &tenors, u, h)?;
            plain(obj([
                ("pv", r.pv.into()),
                ("dv01", r.dv01.into()),
                ("key_rate", r.key_rate.into()),
                ("hedge_units", r.hedge_units.into()),
                ("residual_key_rate", r.residual_key_rate.into()),
                ("hedge_cost", r.hedge_cost.into()),
            ]))
        },
        "usecase.vol_surface" => vol_surface(i),
        "usecase.factor_attribution" => {
            let y = i.reals("portfolio_returns")?;
            let f = i.matrix("factor_returns")?;
            let names: Vec<String> = i
                .array("factor_names")?
                .iter()
                .map(|v| match v {
                    Json::Str(s) => Ok(s.clone()),
                    _ => i.fail("factor_names", "expected strings"),
                })
                .collect::<Result<_>>()?;
            i.gate()?;
            let r = quantforge_core::attribution::factor_attribution(&y, &f, names.len())?;
            plain(obj([
                ("alpha", r.alpha.into()),
                ("betas", r.betas.into()),
                ("r_squared", r.r_squared.into()),
                ("contributions", r.contributions.into()),
                ("mean_return", r.mean_return.into()),
                ("residual_vol", r.residual_vol.into()),
                ("beta_se", r.beta_se.into()),
            ]))
        }
}

pub(crate) fn tenor_text(i: &Inputs, k: &str, s: &str) -> Result<(i64, char)> {
    match parse_tenor(s) {
        Some(t) => Ok(t),
        None => i.fail(k, "malformed tenor"),
    }
}

/// True for `BUY`.
pub(crate) fn trade_side(i: &Inputs) -> Result<f64> {
    match i.str("side")? {
        "BUY" => Ok(1.0),
        "SELL" => Ok(-1.0),
        _ => i.fail("side", "unknown side"),
    }
}

pub(crate) fn equity_valuation(pv: f64, currency: &str, id: Option<String>, as_of: Date) -> Json {
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

/// Use case 3 (`use-cases.md`): quotes to forwards, SVI slices, a checked surface, one price.
pub(crate) fn vol_surface(i: &Inputs) -> Result<Outcome> {
    let as_of = i.date("as_of")?;
    let funding = curve_input(i, "funding_curve")?;
    let mut slices = Vec::new();
    for s in items(i, "slices")? {
        slices.push((s.date("expiry")?, parity_quotes(&s)?));
    }
    let k_grid = i.reals("k_grid")?;
    let target = sub(i, "target")?;
    let (call, strike) = (option_type(&target)?, target.f64("strike")?);
    let (expiry, q) = (target.date("expiry")?, target.f64("quantity")?);
    let sign = trade_side(&target)?;
    let currency = i.str("currency")?;
    i.gate()?;
    nonempty(i, &["slices", "k_grid"])?;
    if slices.iter().any(|x| x.1.is_empty()) {
        return fail("E_INPUT", "a slice has no quotes");
    }
    let curve = Curve::new(&funding)?;
    if funding.as_of != as_of {
        return fail("E_INPUT", "the curve as_of differs");
    }
    if slices.is_empty() || slices.windows(2).any(|w| w[1].0 <= w[0].0) {
        return fail("E_INPUT", "slices must be in expiry order");
    }
    if slices[0].0 <= as_of {
        return fail("E_DOMAIN", "a slice expiry is not after as_of");
    }
    let Some(index) = slices.iter().position(|s| s.0 == expiry) else {
        return fail("E_INPUT", "target expiry is not a slice");
    };
    if strike <= 0.0 || q <= 0.0 {
        return fail("E_DOMAIN", "target strike or quantity is out of domain");
    }
    let (mut times, mut discounts, mut forwards) = (Vec::new(), Vec::new(), Vec::new());
    let (mut fits, mut rmse): (Vec<Svi>, Vec<f64>) = (Vec::new(), Vec::new());
    for (date, quotes) in &slices {
        let t = (date.serial() - as_of.serial()) as f64 / 365.0;
        let d = curve.discount(*date)?;
        let f = equity::parity(quotes, Some(d))?.forward;
        let (mut ks, mut ws) = (Vec::new(), Vec::new());
        for x in quotes {
            let call = x.strike >= f;
            let mid = if call {
                (x.call_bid + x.call_ask) / 2.0
            } else {
                (x.put_bid + x.put_ask) / 2.0
            };
            let o = Option_ {
                model: Model::Black76 {
                    forward: f,
                    discount: d,
                    shift: 0.0,
                },
                call,
                strike: x.strike,
                t,
            };
            let v = o.implied(mid)?;
            ks.push((x.strike / f).ln());
            ws.push(v * v * t);
        }
        let r = svi::calibrate(&ks, &ws, None)?;
        fits.push(r.svi);
        rmse.push(r.rmse);
        times.push(t);
        discounts.push(d);
        forwards.push(f);
    }
    let vols = fits
        .iter()
        .zip(&times)
        .map(|(s, t)| k_grid.iter().map(|&k| (s.w(k) / t).sqrt()).collect())
        .collect();
    let surface = Surface {
        t: times.clone(),
        k: k_grid,
        vols,
    };
    let check = surface.check()?;
    let (f, d, t) = (forwards[index], discounts[index], times[index]);
    let v = (fits[index].w((strike / f).ln()) / t).sqrt();
    let p = black::phi(call);
    let d1 = black::d1_d2(f, strike, v, t).0;
    let pv = sign * q * black::black(call, f, strike, v, t, d);
    plain(obj([
        ("forwards", forwards.into()),
        ("svi_rmse", rmse.into()),
        (
            "arbitrage_free",
            (check.calendar.is_empty() && check.butterfly.is_empty()).into(),
        ),
        ("vol", v.into()),
        ("valuation", equity_valuation(pv, currency, None, as_of)),
        ("delta", (sign * q * d * p * normal_cdf(p * d1)).into()),
        (
            "vega",
            (sign * q * d * f * normal_pdf(d1) * t.sqrt()).into(),
        ),
    ]))
}
