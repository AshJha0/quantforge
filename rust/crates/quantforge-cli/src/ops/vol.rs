//! `vol.*` operations: read the inputs, call the library, shape the outputs.
use super::eq::forward_inputs;
use super::eq::items;
use super::eq::outright;
use super::fx::call_or_put;
use super::fx::nullable_f64;
use super::rates::present;
use super::rates::snapshot_id;
use super::rates::start;
use super::rates::sub;
use super::risk::option_inputs;
use super::risk::rows;
use super::usecase::equity_valuation;
use super::usecase::trade_side;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::arb_surface;
use quantforge_core::arb_surface::Check as ArbCheck;
use quantforge_core::arb_surface::Dynamics;
use quantforge_core::arb_surface::Rule;
use quantforge_core::arb_surface::Side;
use quantforge_core::arb_surface::Slice;
use quantforge_core::arb_surface::WingKind;
use quantforge_core::black;
use quantforge_core::error::Result;
use quantforge_core::error::fail;
use quantforge_core::garch;
use quantforge_core::heston;
use quantforge_core::json::Json;
use quantforge_core::json::obj;
use quantforge_core::sabr;
use quantforge_core::sabr::Sabr;
use quantforge_core::smile;
use quantforge_core::stats::normal_cdf;
use quantforge_core::stats::normal_pdf;
use quantforge_core::surface::Check as GridCheck;
use quantforge_core::surface::Surface;
use quantforge_core::svi;
use quantforge_core::svi::Svi;
use quantforge_core::varswap;
use quantforge_core::varswap::Replication;
use quantforge_core::vix;
use quantforge_core::vix::Quote as VixQuote;

super::registry! {
(op, i)
        "vol.option.price" => {
            let (o, v) = (option_inputs(i)?, i.f64("vol")?);
            plain(obj([
                ("price", o.price(v)?.into()),
                ("forward", o.unshifted_forward().into()),
            ]))
        },
        "vol.option.implied" => {
            let (o, p) = (option_inputs(i)?, i.f64("price")?);
            plain(obj([("vol", o.implied(p)?.into())]))
        },
        "vol.equity.price" => equity_price(i),
        "vol.delta.to_strike" | "vol.delta.from_strike" => {
            let (f, v, t) = (i.f64("forward")?, i.f64("vol")?, i.f64("expiry_years")?);
            let call = option_type(i)?;
            let (spot, scale) = delta_scale(i)?;
            if op == "vol.delta.to_strike" {
                let d = i.f64("delta")?;
                let s = smile::delta_scale(spot, scale)?;
                plain(obj([(
                    "strike",
                    smile::to_strike(f, v, t, call, d, s)?.into(),
                )]))
            } else {
                let k = i.f64("strike")?;
                let s = smile::delta_scale(spot, scale)?;
                plain(obj([(
                    "delta",
                    smile::from_strike(f, v, t, call, k, s)?.into(),
                )]))
            }
        },
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
        },
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
            nonempty(i, &["log_moneyness"])?;
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
        },
        "vol.svi.calibrate" => {
            let (k, w) = (i.reals("log_moneyness")?, i.reals("total_variance")?);
            let q = opt_weights(i)?;
            i.gate()?;
            nonempty(i, &["log_moneyness"])?;
            let r = svi::calibrate(&k, &w, q.as_deref())?;
            plain(obj([("svi", svi_json(&r.svi)), ("rmse", r.rmse.into())]))
        },
        "vol.ssvi.evaluate" => {
            let (rho, eta, gamma) = (i.f64("rho")?, i.f64("eta")?, i.f64("gamma")?);
            let (t, k) = (i.reals("thetas")?, i.reals("log_moneyness")?);
            i.gate()?;
            nonempty(i, &["thetas", "log_moneyness"])?;
            let r = svi::ssvi_evaluate(rho, eta, gamma, &t, &k)?;
            plain(obj([
                ("total_variance", rows(r.total_variance)),
                ("butterfly_free", r.butterfly_free.into()),
                ("calendar_free", r.calendar_free.into()),
            ]))
        },
        "vol.ssvi.calibrate" => {
            let (t, k) = (i.reals("thetas")?, i.reals("log_moneyness")?);
            let w = i.matrix("total_variance")?;
            i.gate()?;
            nonempty(i, &["thetas", "log_moneyness"])?;
            let [rho, eta, gamma, rmse] = svi::ssvi_calibrate(&t, &k, &w)?;
            plain(obj([
                ("rho", rho.into()),
                ("eta", eta.into()),
                ("gamma", gamma.into()),
                ("rmse", rmse.into()),
            ]))
        },
        "vol.surface.query" => {
            let s = surface_input(i)?;
            let mut p = Vec::new();
            for x in items(i, "points")? {
                p.push((x.f64("expiry_years")?, x.f64("log_moneyness")?));
            }
            i.gate()?;
            nonempty(i, &["points"])?;
            let r = s.query(&p)?;
            let w: Vec<f64> = r.iter().map(|x| x.0).collect();
            let v: Vec<f64> = r.iter().map(|x| x.1).collect();
            plain(obj([("total_variance", w.into()), ("vols", v.into())]))
        },
        "vol.surface.check" => {
            let s = surface_input(i)?;
            i.gate()?;
            let r = s.check()?;
            plain(check_json(&r))
        },
        "vol.sabr.hagan" => {
            let (s, k) = (sabr_inputs(i)?, i.reals("strikes")?);
            i.gate()?;
            nonempty(i, &["strikes"])?;
            plain(obj([("vols", s.hagan(&k)?.into())]))
        },
        "vol.sabr.density" => {
            let (s, k, h) = (sabr_inputs(i)?, i.reals("strikes")?, i.f64("h_strike")?);
            let reject = match i.str("on_negative")? {
                "REPORT" => false,
                "REJECT" => true,
                _ => return i.fail("on_negative", "unknown choice"),
            };
            i.gate()?;
            nonempty(i, &["strikes"])?;
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
        },
        "vol.sabr.calibrate" => {
            no_null(i, "shift")?;
            let (f, t, beta) = (i.f64("forward")?, i.f64("expiry_years")?, i.f64("beta")?);
            let (k, v) = (i.reals("strikes")?, i.reals("vols")?);
            let shift = i.f64_or("shift", 0.0)?;
            let q = opt_weights(i)?;
            i.gate()?;
            nonempty(i, &["strikes"])?;
            let [alpha, rho, nu, rmse] = sabr::calibrate(f, t, beta, shift, &k, &v, q.as_deref())?;
            plain(obj([
                ("alpha", alpha.into()),
                ("rho", rho.into()),
                ("nu", nu.into()),
                ("rmse", rmse.into()),
            ]))
        },
        "vol.sabr.arbfree" => {
            let (s, k) = (sabr_inputs(i)?, i.reals("strikes")?);
            let (cells, below) = (i.int("cells")?, i.int("cells_below")?);
            let steps = i.int("steps")?;
            i.gate()?;
            nonempty(i, &["strikes"])?;
            let r = sabr::arbfree(&s, cells, below, steps, &k)?;
            plain(obj([
                ("call_prices", r.call_prices.into()),
                ("vols", r.vols.into()),
                ("mass", r.mass.into()),
                ("mean", r.mean.into()),
                ("absorbed", r.absorbed.into()),
                ("min_density", r.min_density.into()),
            ]))
        },
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
        },
        "vol.heston.cf" => {
            let (t, h, u) = (i.f64("expiry_years")?, heston_of(i)?, i.reals("u")?);
            i.gate()?;
            let (re, im) = heston::heston_cf(t, &h, &u)?;
            plain(obj([("re", re.into()), ("im", im.into())]))
        },
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
        },
        "vol.svi.surface_check" => {
            let s = slices(i)?;
            let (k, reject) = (i.reals("log_moneyness")?, i.bool("reject")?);
            i.gate()?;
            arb_surface::check_slices(&s)?;
            let c = arb_surface::surface_check(&s, &k)?;
            plain(fields(check_fields(&c, reject)?))
        },
        "vol.ssvi.to_svi" => {
            let (rho, eta) = (i.f64("rho")?, i.f64("eta")?);
            let (gamma, theta) = (i.f64("gamma")?, i.f64("theta")?);
            let s = arb_surface::ssvi_to_svi(rho, eta, gamma, theta)?;
            plain(obj([("svi", svi_json(&s))]))
        },
        "vol.svi.fit_surface" => {
            let (t, k) = (i.reals("expiry_years")?, i.reals("log_moneyness")?);
            let (w, reject) = (i.matrix("total_variance")?, i.bool("reject")?);
            i.gate()?;
            let f = arb_surface::fit_surface(&t, &k, &w)?;
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
        },
        "vol.local.dupire" => {
            let s = slices(i)?;
            let p = items(i, "points")?
                .iter()
                .map(|p| Ok((p.f64("expiry_years")?, p.f64("log_moneyness")?)))
                .collect::<Result<Vec<_>>>()?;
            i.gate()?;
            let r = arb_surface::dupire(&s, &p)?;
            plain(obj([
                ("total_variance", r.total_variance.into()),
                ("implied_vol", r.implied_vol.into()),
                ("local_vol", r.local_vol.into()),
            ]))
        },
        "vol.forward.vol" => {
            let (t, v) = (i.reals("expiry_years")?, i.reals("vols")?);
            i.gate()?;
            let f = arb_surface::forward_vols(&t, &v)?;
            plain(obj([("forward_vols", f.into())]))
        },
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
            let o = arb_surface::smile_dynamics(&x)?;
            plain(obj([
                ("vols_base", o.vols_base.into()),
                ("vols_shifted", o.vols_shifted.into()),
                ("prices_base", o.prices_base.into()),
                ("prices_shifted", o.prices_shifted.into()),
                ("deltas", o.deltas.into()),
            ]))
        },
        "vol.volofvol.measure" => {
            let (v, a) = (i.reals("vols")?, i.f64("periods_per_year")?);
            let log = match i.str("method")? {
                "LOG" => true,
                "ABSOLUTE" => false,
                _ => return i.fail("method", "must be LOG or ABSOLUTE"),
            };
            i.gate()?;
            let (vv, m) = arb_surface::vol_of_vol(&v, a, log)?;
            plain(obj([("vol_of_vol", vv.into()), ("mean_change", m.into())]))
        },
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
        },
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
        },
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
        },
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
        },
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
        },
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
        },
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
}

/// Ruling C9: an optional key may be absent, but `null` is `E_SCHEMA`.
pub(crate) fn no_null(i: &Inputs, k: &str) -> Result<()> {
    match i.0.get(k) {
        Some(Json::Null) => i.fail(k, "null is not allowed here"),
        _ => Ok(()),
    }
}

pub(crate) fn option_type(i: &Inputs) -> Result<bool> {
    match i.str("option_type")? {
        "CALL" => Ok(true),
        "PUT" => Ok(false),
        _ => i.fail("option_type", "unknown option type"),
    }
}

pub(crate) fn equity_price(i: &Inputs) -> Result<Outcome> {
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
        return fail(
            "E_DOMAIN",
            "expiry, vol, strike or quantity is out of domain",
        );
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
        (
            "gamma",
            (sign * q * d * normal_pdf(d1) / (fw * v * root * c * c)).into(),
        ),
        ("vega", (sign * q * d * fw * normal_pdf(d1) * root).into()),
    ]))
}

/// `convention` and `scale`, the latter a key that must be present.
pub(crate) fn delta_scale(i: &Inputs) -> Result<(bool, Option<f64>)> {
    present(i, "scale")?;
    let spot = match i.str("convention")? {
        "FORWARD" => false,
        "SPOT" => true,
        _ => return i.fail("convention", "unknown convention"),
    };
    Ok((spot, i.opt_f64("scale")?))
}

pub(crate) fn svi_json(s: &Svi) -> Json {
    obj([
        ("a", s.a.into()),
        ("b", s.b.into()),
        ("rho", s.rho.into()),
        ("m", s.m.into()),
        ("sigma", s.sigma.into()),
    ])
}

pub(crate) fn opt_weights(i: &Inputs) -> Result<Option<Vec<f64>>> {
    no_null(i, "weights")?;
    i.opt("weights").map(|_| i.reals("weights")).transpose()
}

pub(crate) fn check_json(c: &GridCheck) -> Json {
    let at = |j: usize, i: usize| {
        [
            ("expiry_index", (j as i64).into()),
            ("k_index", (i as i64).into()),
        ]
    };
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

pub(crate) fn surface_input(i: &Inputs) -> Result<Surface> {
    let s = sub(i, "surface")?;
    Ok(Surface {
        t: s.reals("expiry_years")?,
        k: s.reals("log_moneyness")?,
        vols: s.matrix("vols")?,
    })
}

pub(crate) fn sabr_inputs(i: &Inputs) -> Result<Sabr> {
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

/// Ruling C17: an empty list is `E_INPUT`, the first rule check.
pub(crate) fn nonempty(i: &Inputs, keys: &[&str]) -> Result<()> {
    for k in keys {
        if i.array(k)?.is_empty() {
            return fail("E_INPUT", format!("{k} is empty"));
        }
    }
    Ok(())
}

pub(crate) fn bad_start<T>() -> Result<T> {
    fail("E_INPUT", "initial_variance must be \"SAMPLE\" or a number")
}

pub(crate) fn strip(i: &Inputs) -> Result<(i64, f64, Vec<VixQuote>)> {
    let n = i.int("minutes_to_expiry")?;
    let r = i.f64("rate")?;
    let s = items(i, "strip")?
        .iter()
        .map(|q| {
            Ok(VixQuote {
                strike: q.f64("strike")?,
                call_bid: nullable_f64(&q, "call_bid")?,
                call_ask: nullable_f64(&q, "call_ask")?,
                put_bid: nullable_f64(&q, "put_bid")?,
                put_ask: nullable_f64(&q, "put_ask")?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    Ok((n, r, s))
}

pub(crate) fn svi_of(p: &Inputs) -> Result<Svi> {
    Ok(Svi {
        a: p.f64("a")?,
        b: p.f64("b")?,
        rho: p.f64("rho")?,
        m: p.f64("m")?,
        sigma: p.f64("sigma")?,
    })
}

pub(crate) fn slices(i: &Inputs) -> Result<Vec<Slice>> {
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

pub(crate) fn fields(v: Vec<(&str, Json)>) -> Json {
    Json::Obj(v.into_iter().map(|(k, x)| (k.to_string(), x)).collect())
}

pub(crate) fn index_json(j: usize) -> Json {
    i64::try_from(j).unwrap_or(i64::MAX).into()
}

/// The four check outputs, or `E_ARBITRAGE` when `reject` is set and the surface is not clean.
pub(crate) fn check_fields(c: &ArbCheck, reject: bool) -> Result<Vec<(&'static str, Json)>> {
    if reject && !c.arbitrage_free() {
        return fail("E_ARBITRAGE", "the surface has arbitrage");
    }
    let at = |v: &[(usize, usize)]| -> Json {
        Json::Arr(
            v.iter()
                .map(|&(j, k)| obj([("expiry_index", index_json(j)), ("k_index", index_json(k))]))
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
                ("expiry_index", index_json(j)),
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

pub(crate) fn heston_of(i: &Inputs) -> Result<heston::Heston> {
    let h = sub(i, "heston")?;
    Ok(heston::Heston {
        v0: h.f64("v0")?,
        kappa: h.f64("kappa")?,
        theta: h.f64("theta")?,
        xi: h.f64("xi")?,
        rho: h.f64("rho")?,
    })
}

pub(crate) fn jumps_of(i: &Inputs) -> Result<heston::Jumps> {
    let j = sub(i, "jumps")?;
    Ok(heston::Jumps {
        intensity: j.f64("intensity")?,
        mean_log_jump: j.f64("mean_log_jump")?,
        log_jump_vol: j.f64("log_jump_vol")?,
    })
}

pub(crate) fn heston_market(i: &Inputs, with_type: bool) -> Result<heston::Market> {
    Ok(heston::Market {
        spot: i.f64("spot")?,
        expiry_years: i.f64("expiry_years")?,
        rate: i.f64("rate")?,
        dividend_yield: i.f64("dividend_yield")?,
        call: if with_type { call_or_put(i)? } else { true },
    })
}
