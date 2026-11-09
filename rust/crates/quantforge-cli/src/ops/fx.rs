//! `fx.*` operations: read the inputs, call the library, shape the outputs.
use super::eq::items;
use super::rates::curve_input;
use super::rates::pillars_json;
use super::rates::repricing;
use super::rates::snapshot_id;
use super::rates::sub;
use super::rates::tenor;
use super::risk::interpolation;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::conventions;
use quantforge_core::conventions::FxPair;
use quantforge_core::curve::Curve;
use quantforge_core::curve::CurveInput;
use quantforge_core::dates::Date;
use quantforge_core::error::Result;
use quantforge_core::error::fail;
use quantforge_core::fx;
use quantforge_core::fx::FxLeg;
use quantforge_core::fx::FxMarket;
use quantforge_core::fx_smile;
use quantforge_core::fx_smile::AtmType;
use quantforge_core::fx_smile::DeltaType;
use quantforge_core::json::Json;
use quantforge_core::json::obj;
use quantforge_core::xccy;
use quantforge_core::xccy::Ndf;
use quantforge_core::xccy::XccyTrade;

super::registry! {
(op, i)
        "fx.spot_date" => {
            let (p, t) = (pair(i)?, i.date("trade_date")?);
            plain(obj([(
                "spot_date",
                fx::spot_date(&p, t)?.to_string().into(),
            )]))
        },
        "fx.forward.outright" => {
            let m = fx_market_input(i)?;
            let v = i.date("value_date")?;
            let (f, p) = fx_market(i, m)?.outright(v)?;
            plain(obj([("forward", f.into()), ("points", p.into())]))
        },
        "fx.forward.pv" => {
            let m = fx_market_input(i)?;
            let l = fx_leg(&sub(i, "trade")?)?;
            let m = fx_market(i, m)?;
            let (pv, delta) = m.leg(&l)?;
            let v = m.valuation(pv, "FX_FORWARD_DISCOUNTING");
            plain(obj([
                ("valuation", v.to_json()),
                ("fx_delta", delta.into()),
            ]))
        },
        "fx.swap.pv" => {
            let m = fx_market_input(i)?;
            let t = sub(i, "trade")?;
            let (n, far_buy) = (t.f64("notional_base")?, far_side(&t)?);
            let near = FxLeg {
                notional_base: n,
                strike: t.f64("near_rate")?,
                value_date: t.date("near_date")?,
                buy: !far_buy,
            };
            let far = FxLeg {
                notional_base: n,
                strike: t.f64("far_rate")?,
                value_date: t.date("far_date")?,
                buy: far_buy,
            };
            let m = fx_market(i, m)?;
            if near.value_date >= far.value_date {
                return fail("E_DATE_ORDER", "near_date is not before far_date");
            }
            let ((a, b), (c, d)) = (m.leg(&near)?, m.leg(&far)?);
            let v = m.valuation(a + c, "FX_SWAP_DISCOUNTING");
            plain(obj([
                ("valuation", v.to_json()),
                ("fx_delta", (b + d).into()),
            ]))
        },
        "fx.curve.implied" => {
            let m = fx_market_input(i)?;
            let mut points = Vec::new();
            for p in items(i, "points")? {
                let t = tenor(&p, "tenor")?;
                if t.1 != 'M' && t.1 != 'Y' {
                    return p.fail("tenor", "expected months or years");
                }
                points.push((t, p.f64("points")?));
            }
            let rows: Vec<Json> = fx_market(i, m)?
                .implied(&points)?
                .into_iter()
                .map(|(d, r, b)| {
                    obj([
                        ("value_date", d.to_string().into()),
                        ("implied_ratio", r.into()),
                        ("basis_bp", b.into()),
                    ])
                })
                .collect();
            plain(obj([("nodes", rows.into())]))
        },
        "fx.xccy.bootstrap" => {
            let (_, f) = (
                curve_input(i, "domestic")?,
                curve_input(i, "foreign_projection")?,
            );
            let dc = known_convention(i, "domestic_convention", "SOFR")?;
            let fc = known_convention(i, "foreign_convention", "ESTR")?;
            let s = i.date("start")?;
            let mut q = Vec::new();
            for x in items(i, "quotes")? {
                q.push((x.int("months")?, x.f64("spread")?));
            }
            let m = interpolation(i)?;
            i.gate()?;
            dc?;
            fc?;
            let r = xccy::bootstrap(&Curve::new(&f)?, s, &q, m)?;
            Ok(Outcome {
                outputs: pillars_json(&r.dates, &r.logs),
                diagnostics: repricing(r.max_repricing_error),
            })
        },
        "fx.xccy.pv" => {
            let d = curve_input(i, "domestic")?;
            let (fp, fd) = (
                curve_input(i, "foreign_projection")?,
                curve_input(i, "foreign_discount")?,
            );
            let spot = i.f64("spot")?;
            let t = sub(i, "trade")?;
            let trade = XccyTrade {
                start: t.date("start")?,
                months: t.int("months")?,
                foreign_notional: t.f64("foreign_notional")?,
                spread: t.f64("spread")?,
                receive_foreign: match t.str("side")? {
                    "RECEIVE_FOREIGN" => true,
                    "PAY_FOREIGN" => false,
                    _ => return t.fail("side", "unknown side"),
                },
            };
            i.gate()?;
            let (d, fp, fd) = (Curve::new(&d)?, Curve::new(&fp)?, Curve::new(&fd)?);
            let (pv, f, dl) = xccy::pv(&d, &fp, &fd, spot, &trade)?;
            plain(obj([
                ("pv", pv.into()),
                ("foreign_leg", f.into()),
                ("domestic_leg", dl.into()),
            ]))
        },
        "fx.ndf.pv" => {
            let (u, o) = (
                curve_input(i, "usd_curve")?,
                curve_input(i, "offshore_curve")?,
            );
            let spot = i.f64("spot")?;
            let t = sub(i, "trade")?;
            let trade = Ndf {
                fixing_date: t.date("fixing_date")?,
                payment_date: t.date("payment_date")?,
                strike: t.f64("strike")?,
                usd_notional: t.f64("usd_notional")?,
                buy: match t.str("side")? {
                    "BUY" => true,
                    "SELL" => false,
                    _ => return t.fail("side", "unknown side"),
                },
            };
            let fixing = nullable_f64(i, "fixing")?;
            i.gate()?;
            let (pv, f) = xccy::ndf_pv(&Curve::new(&u)?, &Curve::new(&o)?, spot, &trade, fixing)?;
            plain(obj([("pv", pv.into()), ("forward", f.into())]))
        },
        "fx.option.price" => {
            let (m, k, v) = (smile_market(i)?, i.f64("strike")?, i.f64("vol")?);
            let (call, n) = (call_or_put(i)?, i.f64("notional")?);
            let p = fx_smile::price(&m, k, v, call, n)?;
            plain(obj([
                ("price", p.price.into()),
                ("premium_pct_foreign", p.premium_pct_foreign.into()),
                ("forward", p.forward.into()),
                ("delta", p.delta.into()),
                ("gamma", p.gamma.into()),
                ("vega", p.vega.into()),
            ]))
        },
        "fx.delta.from_strike" => {
            let (m, k, v) = (smile_market(i)?, i.f64("strike")?, i.f64("vol")?);
            let d = fx_smile::deltas(&m, k, v, call_or_put(i)?)?;
            let pairs = DeltaType::ALL
                .iter()
                .zip(d)
                .map(|(t, x)| (t.name().to_string(), x.into()))
                .collect();
            plain(obj([("deltas", Json::Obj(pairs))]))
        },
        "fx.delta.to_strike" => {
            let (m, v, call) = (smile_market(i)?, i.f64("vol")?, call_or_put(i)?);
            let (d, t) = (i.f64("delta")?, delta_type(i)?);
            let k = fx_smile::strike_from_delta(&m, v, call, d, t)?;
            plain(obj([("strike", k.into())]))
        },
        "fx.atm.strike" => {
            let (m, v) = (smile_market(i)?, i.f64("vol")?);
            let (a, t) = (atm_type(i)?, delta_type(i)?);
            plain(obj([("strike", fx_smile::atm_strike(&m, v, a, t)?.into())]))
        },
        "fx.smile.from_quotes" => {
            let m = smile_market(i)?;
            let q = fx_smile::Quotes {
                atm_vol: i.f64("atm_vol")?,
                rr: i.f64("rr")?,
                bf: i.f64("bf")?,
                delta: i.f64("delta")?,
            };
            let (t, a) = (delta_type(i)?, atm_type(i)?);
            let s = fx_smile::smile(&m, &q, t, a)?;
            plain(obj([
                ("atm_strike", s.atm_strike.into()),
                ("call_vol", s.call_vol.into()),
                ("put_vol", s.put_vol.into()),
                ("call_strike", s.call_strike.into()),
                ("put_strike", s.put_strike.into()),
            ]))
        }
}

pub(crate) fn pair(i: &Inputs) -> Result<FxPair> {
    match conventions::fx_pair(i.str("pair")?) {
        Some(p) => Ok(p),
        None => i.fail("pair", "unknown pair"),
    }
}

pub(crate) fn side(i: &Inputs, yes: &str, no: &str) -> Result<bool> {
    let s = i.str("side")?;
    if s == yes {
        Ok(true)
    } else if s == no {
        Ok(false)
    } else {
        i.fail("side", "unknown side")
    }
}

pub(crate) fn fx_market_input(i: &Inputs) -> Result<FxInput> {
    Ok((
        pair(i)?,
        i.f64("spot")?,
        i.date("as_of")?,
        curve_input(i, "base_curve")?,
        curve_input(i, "quote_curve")?,
        snapshot_id(i)?,
    ))
}

pub(crate) type FxInput = (FxPair, f64, Date, CurveInput, CurveInput, Option<String>);

pub(crate) fn fx_market(i: &Inputs, m: FxInput) -> Result<FxMarket> {
    i.gate()?;
    if m.1 <= 0.0 {
        return fail("E_DOMAIN", "spot must be positive");
    }
    let (base, quote) = (Curve::new(&m.3)?, Curve::new(&m.4)?);
    if base.as_of != m.2 || quote.as_of != m.2 {
        return fail("E_INPUT", "a curve's as_of differs");
    }
    Ok(FxMarket {
        pair: m.0,
        spot: m.1,
        as_of: m.2,
        base,
        quote,
        data_version: m.5,
    })
}

pub(crate) fn fx_leg(t: &Inputs) -> Result<FxLeg> {
    Ok(FxLeg {
        notional_base: t.f64("notional_base")?,
        strike: t.f64("strike")?,
        value_date: t.date("value_date")?,
        buy: side(t, "BUY", "SELL")?,
    })
}

pub(crate) fn far_side(t: &Inputs) -> Result<bool> {
    match t.str("far_side")? {
        "BUY" => Ok(true),
        "SELL" => Ok(false),
        _ => t.fail("far_side", "unknown side"),
    }
}

/// A convention id that must be `want`: another known id is `E_INPUT`, an unknown one `E_SCHEMA`.
pub(crate) fn known_convention(i: &Inputs, k: &str, want: &str) -> Result<Result<()>> {
    let id = i.str(k)?;
    if id == want {
        Ok(Ok(()))
    } else if conventions::lookup(id).is_some() {
        Ok(fail("E_INPUT", format!("{k} must be {want}")))
    } else {
        i.fail(k, "unknown convention")
    }
}

/// Required key whose value may be `null`.
pub(crate) fn nullable_f64(i: &Inputs, k: &str) -> Result<Option<f64>> {
    match i.0.get(k) {
        None => i.fail(k, "is required"),
        Some(Json::Null) => Ok(None),
        _ => Ok(Some(i.f64(k)?)),
    }
}

pub(crate) fn smile_market(i: &Inputs) -> Result<fx_smile::Market> {
    Ok(fx_smile::Market {
        spot: i.f64("spot")?,
        expiry_years: i.f64("expiry_years")?,
        domestic_rate: i.f64("domestic_rate")?,
        foreign_rate: i.f64("foreign_rate")?,
    })
}

pub(crate) fn call_or_put(i: &Inputs) -> Result<bool> {
    match i.str("option_type")? {
        "CALL" => Ok(true),
        "PUT" => Ok(false),
        _ => i.fail("option_type", "must be CALL or PUT"),
    }
}

pub(crate) fn delta_type(i: &Inputs) -> Result<DeltaType> {
    let s = i.str("delta_type")?;
    DeltaType::parse(s).map_or_else(|| i.fail("delta_type", "unknown delta type"), Ok)
}

pub(crate) fn atm_type(i: &Inputs) -> Result<AtmType> {
    match i.str("atm_type")? {
        "SPOT" => Ok(AtmType::Spot),
        "FORWARD" => Ok(AtmType::Forward),
        "DNS" => Ok(AtmType::Dns),
        _ => i.fail("atm_type", "unknown ATM type"),
    }
}
