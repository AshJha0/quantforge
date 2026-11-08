//! Stage E operations: E6 (`06-risk/correlation.md`), E2 (`heston-family.md`), E4 (`rates-vol-cube.md`), E3 (`fx-smile.md`), E1 (`arb-free-surfaces.md`, `local-and-forward-vol.md`) and E7
//! (`garch.md`, `variance-swaps.md`, `vix-index.md`).

use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use crate::ops_b::{curve_input, items, sub};
use quantforge_core::corr;
use quantforge_core::curve::{Curve, CurveInput};
use quantforge_core::error::{Result, fail};
use quantforge_core::fx_smile::{self, AtmType, DeltaType};
use quantforge_core::garch::{self, Start};
use quantforge_core::heston;
use quantforge_core::json::{Json, obj};
use quantforge_core::rates_e;
use quantforge_core::surface_e::{self, Check, Dynamics, Rule, Side, Slice, WingKind};
use quantforge_core::svi::Svi;
use quantforge_core::varswap::{self, Replication};
use quantforge_core::vix::{self, Quote};

/// `initial_variance`: `"SAMPLE"` or a number; another string is `E_INPUT`, another type
/// `E_SCHEMA`. The string check is returned apart so it can run in its spec order.
fn start(i: &Inputs) -> Result<std::result::Result<Start, ()>> {
    match i.req("initial_variance")? {
        Json::Str(s) if s == "SAMPLE" => Ok(Ok(Start::Sample)),
        Json::Str(_) => Ok(Err(())),
        _ => Ok(Ok(Start::Given(i.f64("initial_variance")?))),
    }
}

fn bad_start<T>() -> Result<T> {
    fail("E_INPUT", "initial_variance must be \"SAMPLE\" or a number")
}

fn strip(i: &Inputs) -> Result<(i64, f64, Vec<Quote>)> {
    let n = i.int("minutes_to_expiry")?;
    let r = i.f64("rate")?;
    let s = items(i, "strip")?
        .iter()
        .map(|q| {
            Ok(Quote {
                strike: q.f64("strike")?,
                call_bid: q.f64("call_bid")?,
                call_ask: q.f64("call_ask")?,
                put_bid: q.f64("put_bid")?,
                put_ask: q.f64("put_ask")?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    Ok((n, r, s))
}

fn svi_of(p: &Inputs) -> Result<Svi> {
    Ok(Svi {
        a: p.f64("a")?,
        b: p.f64("b")?,
        rho: p.f64("rho")?,
        m: p.f64("m")?,
        sigma: p.f64("sigma")?,
    })
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

fn slices(i: &Inputs) -> Result<Vec<Slice>> {
    items(i, "slices")?
        .iter()
        .map(|s| {
            Ok(Slice {
                expiry_years: s.f64("expiry_years")?,
                svi: svi_of(&sub(s, "svi")?)?,
            })
        })
        .collect()
}

fn fields(v: Vec<(&str, Json)>) -> Json {
    Json::Obj(v.into_iter().map(|(k, x)| (k.to_string(), x)).collect())
}

fn index(j: usize) -> Json {
    i64::try_from(j).unwrap_or(i64::MAX).into()
}

/// The four check outputs, or `E_ARBITRAGE` when `reject` is set and the surface is not clean.
fn check_fields(c: &Check, reject: bool) -> Result<Vec<(&'static str, Json)>> {
    if reject && !c.arbitrage_free() {
        return fail("E_ARBITRAGE", "the surface has arbitrage");
    }
    let at = |v: &[(usize, usize)]| -> Json {
        Json::Arr(
            v.iter()
                .map(|&(j, k)| obj([("expiry_index", index(j)), ("k_index", index(k))]))
                .collect(),
        )
    };
    let wings = c
        .wings
        .iter()
        .map(|&(j, side, kind)| {
            let side = if side == Side::Left { "LEFT" } else { "RIGHT" };
            let kind = if kind == WingKind::Lee {
                "LEE"
            } else {
                "CALENDAR"
            };
            obj([
                ("expiry_index", index(j)),
                ("side", side.into()),
                ("kind", kind.into()),
            ])
        })
        .collect();
    Ok(vec![
        ("butterfly_violations", at(&c.butterfly)),
        ("calendar_violations", at(&c.calendar)),
        ("wing_violations", Json::Arr(wings)),
        ("arbitrage_free", c.arbitrage_free().into()),
    ])
}

fn fx_market(i: &Inputs) -> Result<fx_smile::Market> {
    Ok(fx_smile::Market {
        spot: i.f64("spot")?,
        expiry_years: i.f64("expiry_years")?,
        domestic_rate: i.f64("domestic_rate")?,
        foreign_rate: i.f64("foreign_rate")?,
    })
}

fn option_type(i: &Inputs) -> Result<bool> {
    match i.str("option_type")? {
        "CALL" => Ok(true),
        "PUT" => Ok(false),
        _ => i.fail("option_type", "must be CALL or PUT"),
    }
}

fn delta_type(i: &Inputs) -> Result<DeltaType> {
    let s = i.str("delta_type")?;
    DeltaType::parse(s).map_or_else(|| i.fail("delta_type", "unknown delta type"), Ok)
}

fn atm_type(i: &Inputs) -> Result<AtmType> {
    match i.str("atm_type")? {
        "SPOT" => Ok(AtmType::Spot),
        "FORWARD" => Ok(AtmType::Forward),
        "DNS" => Ok(AtmType::Dns),
        _ => i.fail("atm_type", "unknown ATM type"),
    }
}

fn model(i: &Inputs) -> Result<bool> {
    match i.str("model")? {
        "BLACK_76" => Ok(false),
        "BACHELIER" => Ok(true),
        _ => i.fail("model", "must be BLACK_76 or BACHELIER"),
    }
}

fn kind(i: &Inputs, yes: &str, no: &str) -> Result<bool> {
    let s = i.str("type")?;
    if s == yes {
        Ok(true)
    } else if s == no {
        Ok(false)
    } else {
        i.fail("type", "unknown type")
    }
}

fn ints(i: &Inputs, k: &str) -> Result<Vec<i64>> {
    i.array(k)?
        .iter()
        .map(|v| {
            v.as_int()
                .map_or_else(|| i.fail(k, "expected integers"), Ok)
        })
        .collect()
}

fn curves(i: &Inputs) -> Result<(CurveInput, CurveInput)> {
    Ok((curve_input(i, "discount")?, curve_input(i, "projection")?))
}

fn futures_option(i: &Inputs) -> Result<rates_e::FuturesOption> {
    Ok(rates_e::FuturesOption {
        call: kind(i, "CALL", "PUT")?,
        futures_price: i.f64("futures_price")?,
        strike: i.f64("strike")?,
        expiry_years: i.f64("expiry_years")?,
        discount_factor: i.f64("discount_factor")?,
    })
}

fn heston_of(i: &Inputs) -> Result<heston::Heston> {
    let h = sub(i, "heston")?;
    Ok(heston::Heston {
        v0: h.f64("v0")?,
        kappa: h.f64("kappa")?,
        theta: h.f64("theta")?,
        xi: h.f64("xi")?,
        rho: h.f64("rho")?,
    })
}

fn jumps_of(i: &Inputs) -> Result<heston::Jumps> {
    let j = sub(i, "jumps")?;
    Ok(heston::Jumps {
        intensity: j.f64("intensity")?,
        mean_log_jump: j.f64("mean_log_jump")?,
        log_jump_vol: j.f64("log_jump_vol")?,
    })
}

fn heston_market(i: &Inputs, with_type: bool) -> Result<heston::Market> {
    Ok(heston::Market {
        spot: i.f64("spot")?,
        expiry_years: i.f64("expiry_years")?,
        rate: i.f64("rate")?,
        dividend_yield: i.f64("dividend_yield")?,
        call: if with_type { option_type(i)? } else { true },
    })
}

pub fn dispatch(op: &str, i: &Inputs) -> Result<Outcome> {
    match op {
        "risk.corr.validate" => {
            let m = i.matrix("matrix")?;
            i.gate()?;
            let v = corr::validate(&m)?;
            plain(obj([
                ("symmetric", v.symmetric.into()),
                ("unit_diagonal", v.unit_diagonal.into()),
                ("in_range", v.in_range.into()),
                ("min_eigenvalue", v.min_eigenvalue.into()),
                ("psd", v.psd.into()),
                ("valid", v.valid().into()),
            ]))
        }
        "risk.corr.nearest" => {
            let m = i.matrix("matrix")?;
            i.gate()?;
            let (x, d) = corr::nearest(&m)?;
            let rows = Json::Arr(x.into_iter().map(Into::into).collect());
            plain(obj([("matrix", rows), ("frobenius_distance", d.into())]))
        }
        "risk.corr.implied" => {
            let (w, v, s) = (i.reals("weights")?, i.reals("vols")?, i.f64("index_vol")?);
            i.gate()?;
            plain(obj([("correlation", corr::implied(&w, &v, s)?.into())]))
        }
        "risk.corr.dispersion" => {
            let (w, k) = (i.reals("weights")?, i.reals("vol_strikes")?);
            let s = i.reals("realized_vols")?;
            let x = corr::Dispersion {
                weights: &w,
                vol_strikes: &k,
                index_vol_strike: i.f64("index_vol_strike")?,
                realized_vols: &s,
                index_realized_vol: i.f64("index_realized_vol")?,
                vega_notional: i.f64("vega_notional")?,
            };
            i.gate()?;
            let o = corr::dispersion(&x)?;
            plain(obj([
                ("pnl", o.pnl.into()),
                ("implied_correlation", o.implied_correlation.into()),
                ("realized_correlation", o.realized_correlation.into()),
                (
                    "constituent_variance_notionals",
                    o.constituent_variance_notionals.into(),
                ),
                ("index_variance_notional", o.index_variance_notional.into()),
            ]))
        }
        "vol.heston.price" | "vol.bates.price" | "vol.merton.price" => {
            let (m, k) = (heston_market(i, true)?, i.reals("strikes")?);
            let p = match op {
                "vol.heston.price" => {
                    let h = heston_of(i)?;
                    i.gate()?;
                    heston::heston_price(&m, &k, &h)?
                }
                "vol.bates.price" => {
                    let (h, j) = (heston_of(i)?, jumps_of(i)?);
                    i.gate()?;
                    heston::bates_price(&m, &k, &h, &j)?
                }
                _ => {
                    let (v, j) = (i.f64("vol")?, jumps_of(i)?);
                    i.gate()?;
                    heston::merton_price(&m, &k, v, &j)?
                }
            };
            plain(obj([("prices", p.into())]))
        }
        "vol.heston.cf" => {
            let (t, h, u) = (i.f64("expiry_years")?, heston_of(i)?, i.reals("u")?);
            i.gate()?;
            let (re, im) = heston::heston_cf(t, &h, &u)?;
            plain(obj([("re", re.into()), ("im", im.into())]))
        }
        "vol.slv.leverage" => {
            let (m, h, s) = (heston_market(i, false)?, heston_of(i)?, slices(i)?);
            let g = sub(i, "grid")?;
            let grid = heston::Grid {
                nx: g.int("nx")?,
                nv: g.int("nv")?,
                nt: g.int("nt")?,
                x_min: g.f64("x_min")?,
                x_max: g.f64("x_max")?,
                v_max: g.f64("v_max")?,
            };
            i.gate()?;
            let r = heston::slv_leverage(&m, &h, &s, &grid)?;
            plain(obj([
                ("x", r.x.into()),
                ("leverage", r.leverage.into()),
                ("mass", r.mass.into()),
            ]))
        }
        "rates.swaption.price_cube" => {
            let (d, p) = curves(i)?;
            let c = sub(i, "cube")?;
            let cube = rates_e::Cube {
                expiries_months: ints(&c, "expiries_months")?,
                tenors_months: ints(&c, "tenors_months")?,
                alpha: c.matrix("alpha")?,
                beta: c.matrix("beta")?,
                rho: c.matrix("rho")?,
                nu: c.matrix("nu")?,
            };
            let t = sub(i, "trade")?;
            let trade = rates_e::CubeTrade {
                payer: kind(&t, "PAYER", "RECEIVER")?,
                expiry_months: t.int("expiry_months")?,
                tenor_months: t.int("tenor_months")?,
                strike: t.f64("strike")?,
                notional: t.f64("notional")?,
            };
            i.gate()?;
            let r = rates_e::price_cube(&Curve::new(&d)?, &Curve::new(&p)?, &cube, &trade)?;
            plain(obj([
                ("price", r.price.into()),
                ("forward_rate", r.forward_rate.into()),
                ("annuity", r.annuity.into()),
                ("vol", r.vol.into()),
                (
                    "sabr",
                    obj([
                        ("alpha", r.sabr.alpha.into()),
                        ("beta", r.sabr.beta.into()),
                        ("rho", r.sabr.rho.into()),
                        ("nu", r.sabr.nu.into()),
                    ]),
                ),
            ]))
        }
        "rates.cap.strip" => {
            let (d, p) = curves(i)?;
            let (tenors, vols) = (ints(i, "cap_tenors_months")?, i.reals("flat_vols")?);
            let x = rates_e::Strip {
                normal: model(i)?,
                start_months: i.int("start_months")?,
                strike: i.f64("strike")?,
                cap_tenors_months: &tenors,
                flat_vols: &vols,
                notional: i.f64("notional")?,
            };
            i.gate()?;
            let (cv, prices) = rates_e::strip_caplets(&Curve::new(&d)?, &Curve::new(&p)?, &x)?;
            plain(obj([
                ("caplet_vols", cv.into()),
                ("cap_prices", prices.into()),
            ]))
        }
        "rates.bondfut.option_price" => {
            let o = futures_option(i)?;
            let (v, n) = (i.f64("vol")?, i.f64("contract_size")?);
            let (p, cv) = rates_e::futures_option_price(&o, v, n)?;
            plain(obj([("price", p.into()), ("contract_value", cv.into())]))
        }
        "rates.bondfut.implied_vol" => {
            let o = futures_option(i)?;
            let (pr, y) = (i.f64("premium")?, i.f64("ctd_yield")?);
            let dm = i.f64("ctd_modified_duration")?;
            let (pv, yv) = rates_e::futures_implied_vol(&o, pr, y, dm)?;
            plain(obj([("price_vol", pv.into()), ("yield_vol", yv.into())]))
        }
        "infl.cap.yoy_price" => {
            let (normal, cap) = (model(i)?, kind(i, "CAP", "FLOOR")?);
            let (k, n) = (i.f64("strike")?, i.f64("notional")?);
            let periods = items(i, "periods")?
                .iter()
                .map(|p| {
                    Ok(rates_e::YoyPeriod {
                        accrual: p.f64("accrual")?,
                        discount_factor: p.f64("discount_factor")?,
                        yoy_forward: p.f64("yoy_forward")?,
                        expiry_years: p.f64("expiry_years")?,
                        vol: p.f64("vol")?,
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            i.gate()?;
            let c = rates_e::yoy_caplets(normal, cap, k, n, &periods)?;
            let total: f64 = c.iter().sum();
            plain(obj([("caplets", c.into()), ("price", total.into())]))
        }
        "infl.cap.zc_price" => {
            let z = rates_e::ZeroCoupon {
                normal: model(i)?,
                cap: kind(i, "CAP", "FLOOR")?,
                forward_index_ratio: i.f64("forward_index_ratio")?,
                years: i.f64("years")?,
                strike: i.f64("strike")?,
                discount_factor: i.f64("discount_factor")?,
                vol: i.f64("vol")?,
                notional: i.f64("notional")?,
            };
            let (p, r) = rates_e::zc_cap(&z)?;
            plain(obj([("price", p.into()), ("strike_ratio", r.into())]))
        }
        "fx.option.price" => {
            let (m, k, v) = (fx_market(i)?, i.f64("strike")?, i.f64("vol")?);
            let (call, n) = (option_type(i)?, i.f64("notional")?);
            let p = fx_smile::price(&m, k, v, call, n)?;
            plain(obj([
                ("price", p.price.into()),
                ("premium_pct_foreign", p.premium_pct_foreign.into()),
                ("forward", p.forward.into()),
                ("delta", p.delta.into()),
                ("gamma", p.gamma.into()),
                ("vega", p.vega.into()),
            ]))
        }
        "fx.delta.from_strike" => {
            let (m, k, v) = (fx_market(i)?, i.f64("strike")?, i.f64("vol")?);
            let d = fx_smile::deltas(&m, k, v, option_type(i)?)?;
            let pairs = DeltaType::ALL
                .iter()
                .zip(d)
                .map(|(t, x)| (t.name().to_string(), x.into()))
                .collect();
            plain(obj([("deltas", Json::Obj(pairs))]))
        }
        "fx.delta.to_strike" => {
            let (m, v, call) = (fx_market(i)?, i.f64("vol")?, option_type(i)?);
            let (d, t) = (i.f64("delta")?, delta_type(i)?);
            let k = fx_smile::strike_from_delta(&m, v, call, d, t)?;
            plain(obj([("strike", k.into())]))
        }
        "fx.atm.strike" => {
            let (m, v) = (fx_market(i)?, i.f64("vol")?);
            let (a, t) = (atm_type(i)?, delta_type(i)?);
            plain(obj([("strike", fx_smile::atm_strike(&m, v, a, t)?.into())]))
        }
        "fx.smile.from_quotes" => {
            let m = fx_market(i)?;
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
        "vol.svi.surface_check" => {
            let s = slices(i)?;
            let (k, reject) = (i.reals("log_moneyness")?, i.bool("reject")?);
            i.gate()?;
            surface_e::check_slices(&s)?;
            let c = surface_e::surface_check(&s, &k)?;
            plain(fields(check_fields(&c, reject)?))
        }
        "vol.ssvi.to_svi" => {
            let (rho, eta) = (i.f64("rho")?, i.f64("eta")?);
            let (gamma, theta) = (i.f64("gamma")?, i.f64("theta")?);
            let s = surface_e::ssvi_to_svi(rho, eta, gamma, theta)?;
            plain(obj([("svi", svi_json(&s))]))
        }
        "vol.svi.fit_surface" => {
            let (t, k) = (i.reals("expiry_years")?, i.reals("log_moneyness")?);
            let (w, reject) = (i.matrix("total_variance")?, i.bool("reject")?);
            i.gate()?;
            let f = surface_e::fit_surface(&t, &k, &w)?;
            let fitted = f
                .slices
                .iter()
                .map(|s| {
                    obj([
                        ("expiry_years", s.expiry_years.into()),
                        ("svi", svi_json(&s.svi)),
                    ])
                })
                .collect();
            let mut out = vec![("slices", Json::Arr(fitted)), ("rmse", f.rmse.into())];
            out.extend(check_fields(&f.check, reject)?);
            plain(fields(out))
        }
        "vol.local.dupire" => {
            let s = slices(i)?;
            let p = items(i, "points")?
                .iter()
                .map(|p| Ok((p.f64("expiry_years")?, p.f64("log_moneyness")?)))
                .collect::<Result<Vec<_>>>()?;
            i.gate()?;
            let r = surface_e::dupire(&s, &p)?;
            plain(obj([
                ("total_variance", r.total_variance.into()),
                ("implied_vol", r.implied_vol.into()),
                ("local_vol", r.local_vol.into()),
            ]))
        }
        "vol.forward.vol" => {
            let (t, v) = (i.reals("expiry_years")?, i.reals("vols")?);
            i.gate()?;
            let f = surface_e::forward_vols(&t, &v)?;
            plain(obj([("forward_vols", f.into())]))
        }
        "vol.smile.dynamics" => {
            let svi = svi_of(&sub(i, "svi")?)?;
            let k = i.reals("strikes")?;
            let rule = match i.str("rule")? {
                "STICKY_STRIKE" => Rule::StickyStrike,
                "STICKY_DELTA" => Rule::StickyDelta,
                _ => return i.fail("rule", "must be STICKY_STRIKE or STICKY_DELTA"),
            };
            let x = Dynamics {
                svi,
                expiry_years: i.f64("expiry_years")?,
                spot: i.f64("spot")?,
                spot_shifted: i.f64("spot_shifted")?,
                rate: i.f64("rate")?,
                dividend_yield: i.f64("dividend_yield")?,
                strikes: &k,
                rule,
                call: match i.str("option_type")? {
                    "CALL" => true,
                    "PUT" => false,
                    _ => return i.fail("option_type", "must be CALL or PUT"),
                },
            };
            i.gate()?;
            let o = surface_e::smile_dynamics(&x)?;
            plain(obj([
                ("vols_base", o.vols_base.into()),
                ("vols_shifted", o.vols_shifted.into()),
                ("prices_base", o.prices_base.into()),
                ("prices_shifted", o.prices_shifted.into()),
                ("deltas", o.deltas.into()),
            ]))
        }
        "vol.volofvol.measure" => {
            let (v, a) = (i.reals("vols")?, i.f64("periods_per_year")?);
            let log = match i.str("method")? {
                "LOG" => true,
                "ABSOLUTE" => false,
                _ => return i.fail("method", "must be LOG or ABSOLUTE"),
            };
            i.gate()?;
            let (vv, m) = surface_e::vol_of_vol(&v, a, log)?;
            plain(obj([("vol_of_vol", vv.into()), ("mean_change", m.into())]))
        }
        "vol.garch.loglik" => {
            let r = i.reals("returns")?;
            let (o, a, b) = (i.f64("omega")?, i.f64("alpha")?, i.f64("beta")?);
            let s = start(i)?;
            i.gate()?;
            if r.len() < 2 {
                return fail("E_INPUT", "at least 2 returns are required");
            }
            let Ok(s) = s else { return bad_start() };
            let l = garch::loglik(&r, o, a, b, s)?;
            plain(obj([
                ("loglik", l.loglik.into()),
                ("variances", l.variances.into()),
                ("next_variance", l.next_variance.into()),
            ]))
        }
        "vol.garch.forecast" => {
            let (o, a, b) = (i.f64("omega")?, i.f64("alpha")?, i.f64("beta")?);
            let (v, h, p) = (
                i.f64("next_variance")?,
                i.int("horizon")?,
                i.f64("periods_per_year")?,
            );
            i.gate()?;
            let f = garch::forecast(o, a, b, v, h, p)?;
            plain(obj([
                ("variances", f.variances.into()),
                ("total_variance", f.total_variance.into()),
                ("annualized_vol", f.annualized_vol.into()),
                ("long_run_variance", f.long_run_variance.into()),
            ]))
        }
        "vol.garch.fit" => {
            let r = i.reals("returns")?;
            let s = start(i)?;
            i.gate()?;
            if r.len() < 30 {
                return fail("E_INPUT", "at least 30 returns are required");
            }
            let Ok(s) = s else { return bad_start() };
            let f = garch::fit(&r, s)?;
            plain(obj([("loglik", f.loglik.into())]))
        }
        "vol.varswap.fair_strike" => {
            let vols = items(i, "vols")?
                .iter()
                .map(|v| Ok((v.f64("strike")?, v.f64("vol")?)))
                .collect::<Result<Vec<_>>>()?;
            let (puts, calls) = (i.reals("put_strikes")?, i.reals("call_strikes")?);
            let x = Replication {
                as_of: i.date("as_of")?,
                maturity: i.date("maturity")?,
                spot: i.f64("spot")?,
                rate: i.f64("rate")?,
                dividend_yield: i.f64("dividend_yield")?,
                put_strikes: &puts,
                call_strikes: &calls,
                vols: &vols,
                extension_step: i.f64("extension_step")?,
                variance_strike: i.f64("variance_strike")?,
                variance_notional: i.f64("variance_notional")?,
            };
            i.gate()?;
            let f = varswap::fair_strike(&x)?;
            plain(obj([
                ("fair_variance", f.fair_variance.into()),
                ("fair_vol", f.fair_vol.into()),
                ("pv", f.pv.into()),
            ]))
        }
        "vol.varswap.realized" => {
            let p = i.reals("prices")?;
            let a = i.f64("periods_per_year")?;
            let (k, n) = (i.f64("variance_strike")?, i.f64("variance_notional")?);
            i.gate()?;
            let r = varswap::realized(&p, a, k, n)?;
            plain(obj([
                ("realized_variance", r.realized_variance.into()),
                ("realized_vol", r.realized_vol.into()),
                ("payoff", r.payoff.into()),
            ]))
        }
        "vol.vix.term_variance" => {
            let (n, r, s) = strip(i)?;
            i.gate()?;
            let t = vix::term_variance(n, r, &s)?;
            plain(obj([
                ("forward", t.forward.into()),
                ("k0", t.k0.into()),
                ("variance", t.variance.into()),
                ("strikes_used", t.strikes_used.into()),
            ]))
        }
        "vol.vix.index" => {
            let near = strip(&sub(i, "near")?)?;
            let next = strip(&sub(i, "next")?)?;
            i.gate()?;
            let x = vix::index((near.0, near.1, &near.2), (next.0, next.1, &next.2))?;
            plain(obj([
                ("index", x.index.into()),
                ("near_variance", x.near_variance.into()),
                ("next_variance", x.next_variance.into()),
            ]))
        }
        _ => fail(
            "E_UNSUPPORTED_OPERATION",
            format!("{op} is not in this build"),
        ),
    }
}
