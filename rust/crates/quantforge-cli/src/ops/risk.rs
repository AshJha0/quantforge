//! `risk.*` operations: read the inputs, call the library, shape the outputs.
use super::bond::bond_fields;
use super::eq::items;
use super::rates::curve_input;
use super::rates::ois_trade;
use super::rates::overnight;
use super::rates::sub;
use super::rates::tenor;
use super::vol::no_null;
use super::vol::nonempty;
use super::vol::option_type;
use super::vol::surface_input;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::black::Model;
use quantforge_core::black::Option_;
use quantforge_core::book_risk;
use quantforge_core::corr;
use quantforge_core::curve::Interpolation;
use quantforge_core::error::Result;
use quantforge_core::error::fail;
use quantforge_core::frtb;
use quantforge_core::greeks;
use quantforge_core::json::Json;
use quantforge_core::json::obj;
use quantforge_core::ois::OisQuote;
use quantforge_core::risk;
use quantforge_core::risk_curve;
use quantforge_core::risk_curve::Bump;
use quantforge_core::risk_curve::KeyMode;
use quantforge_core::risk_curve::Product;
use quantforge_core::risk_curve::Scheme;
use quantforge_core::risk_tools;
use quantforge_core::surface::Position;
use quantforge_core::var;

super::registry! {
(op, i)
        "risk.ois.dv01" => {
            let (t, q, m) = (i.date("as_of")?, ois_quotes(i)?, interpolation(i)?);
            let trade = ois_trade(i)?;
            i.gate()?;
            let (d, k) = risk::ois_dv01(t, &q, m, &trade)?;
            plain(obj([("dv01", d.into()), ("key_rate", k.into())]))
        },
        "risk.cashflows" => {
            let mut flows = Vec::new();
            for c in items(i, "cashflows")? {
                flows.push((c.f64("t")?, c.f64("amount")?));
            }
            let y = i.f64("yield")?;
            i.gate()?;
            let (p, d, c) = risk::cashflows(&flows, y)?;
            plain(obj([
                ("pv", p.into()),
                ("duration", d.into()),
                ("convexity", c.into()),
            ]))
        },
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
        },
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
        },
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
            nonempty(i, &["positions"])?;
            let r = s.vega(&p)?;
            plain(obj([
                ("pv", r.pv.into()),
                ("bucket_vega", rows(r.bucket)),
                ("parallel_vega", r.parallel.into()),
                ("bucket_sum", r.bucket_sum.into()),
            ]))
        },
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
        },
        "risk.corr.nearest" => {
            let m = i.matrix("matrix")?;
            i.gate()?;
            let (x, d) = corr::nearest(&m)?;
            let rows = Json::Arr(x.into_iter().map(Into::into).collect());
            plain(obj([("matrix", rows), ("frobenius_distance", d.into())]))
        },
        "risk.corr.implied" => {
            let (w, v, s) = (i.reals("weights")?, i.reals("vols")?, i.f64("index_vol")?);
            i.gate()?;
            plain(obj([("correlation", corr::implied(&w, &v, s)?.into())]))
        },
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
        },
        "risk.book.ois_sensitivity" => {
            let c = overnight(i, "convention")?;
            let (t, m) = (i.date("as_of")?, interpolation(i)?);
            let raw = items(i, "quotes")?;
            let q = ois_quotes(i)?;
            let labels: Vec<String> = raw
                .iter()
                .map(|r| r.str("tenor").map(str::to_string))
                .collect::<Result<_>>()?;
            let swaps = items(i, "swaps")?
                .iter()
                .map(|s| {
                    let payer = match s.str("side")? {
                        "PAY" => true,
                        "RECEIVE" => false,
                        _ => return s.fail("side", "PAY or RECEIVE"),
                    };
                    Ok(book_risk::BookSwap {
                        id: s.str("id")?.to_string(),
                        tenor_years: s.int("tenor_years")?,
                        fixed_rate: s.f64("fixed_rate")?,
                        payer,
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            i.gate()?;
            let r = book_risk::ois_sensitivity(&c, t, &q, m, &swaps)?;
            let strs = |v: Vec<String>| Json::Arr(v.into_iter().map(Json::from).collect());
            let rows = |m: Vec<Vec<f64>>| Json::Arr(m.into_iter().map(Json::from).collect());
            let ids: Vec<String> = swaps.iter().map(|s| s.id.clone()).collect();
            let pillars: Vec<String> = r.pillars.iter().map(ToString::to_string).collect();
            plain(obj([
                ("pv", r.pv.into()),
                ("book_pv", r.book_pv.into()),
                (
                    "quote_sensitivity",
                    obj([
                        ("swaps", strs(ids)),
                        ("quotes", strs(labels.clone())),
                        ("matrix", rows(r.quote_sensitivity)),
                    ]),
                ),
                ("book_sensitivity", r.book_sensitivity.into()),
                (
                    "zero_jacobian",
                    obj([
                        ("pillars", strs(pillars)),
                        ("quotes", strs(labels)),
                        ("matrix", rows(r.zero_jacobian)),
                    ]),
                ),
            ]))
        },
        "risk.curve.pca" => {
            let x = i.matrix("changes")?;
            let k = i.int("components")?;
            i.gate()?;
            let r = risk_tools::pca(&x, k)?;
            let rows: Vec<Json> = r.loadings.into_iter().map(Json::from).collect();
            plain(obj([
                ("eigenvalues", r.eigenvalues.into()),
                ("loadings", Json::Arr(rows)),
                ("explained_ratio", r.explained_ratio.into()),
            ]))
        },
        "risk.curve.cross_gamma" => {
            let curve = curve_input(i, "curve")?;
            let p = product(i)?;
            let bp = i.f64("bump_bp")?;
            i.gate()?;
            let (v, g) = risk_curve::cross_gamma(&curve, &p, bp)?;
            let rows: Vec<Json> = g.into_iter().map(Json::from).collect();
            plain(obj([("value", v.into()), ("cross_gamma", Json::Arr(rows))]))
        },
        "risk.credit.jtd" => {
            let ps = items(i, "positions")?
                .iter()
                .map(|p| {
                    let kind = match p.str("kind")? {
                        "BOND" => risk_tools::JtdKind::Bond,
                        "CDS_PROTECTION_BUYER" => risk_tools::JtdKind::ProtectionBuyer,
                        "CDS_PROTECTION_SELLER" => risk_tools::JtdKind::ProtectionSeller,
                        _ => return p.fail("kind", "unknown kind"),
                    };
                    p.str("id")?;
                    Ok(risk_tools::JtdPosition {
                        kind,
                        notional: p.f64("notional")?,
                        recovery: p.f64("recovery")?,
                        market_value: p.f64("market_value")?,
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            i.gate()?;
            let (v, t) = risk_tools::jtd(&ps)?;
            plain(obj([("jtd", v.into()), ("total", t.into())]))
        },
        "risk.var.historical" => {
            let (x, c) = (i.reals("pnl")?, i.f64("confidence")?);
            i.gate()?;
            let r = var::historical(&x, c)?;
            plain(var_json(r, true))
        },
        "risk.var.filtered_historical" => {
            let x = i.reals("returns")?;
            let (p, l, c) = (i.f64("position_value")?, i.f64("lambda")?, i.f64("confidence")?);
            i.gate()?;
            let (r, next) = var::filtered_historical(&x, p, l, c)?;
            let mut o = var_json(r, true);
            if let Json::Obj(m) = &mut o {
                m.push(("sigma_next".into(), next.into()));
            }
            plain(o)
        },
        "risk.var.parametric" => {
            let (m, s, c) = (i.f64("mean")?, i.f64("std")?, i.f64("confidence")?);
            i.gate()?;
            plain(var_json(var::parametric(m, s, c)?, false))
        },
        "risk.var.monte_carlo" => {
            let (m, cov, w) = (i.reals("mean")?, i.matrix("covariance")?, i.reals("weights")?);
            let (paths, seed, c) = (i.int("paths")?, i.seed()?, i.f64("confidence")?);
            i.gate()?;
            plain(var_json(var::monte_carlo(&m, &cov, &w, paths, seed, c)?, true))
        },
        "risk.backtest.kupiec" => {
            let (n, x, c) = (i.int("observations")?, i.int("exceptions")?, i.f64("confidence")?);
            i.gate()?;
            let (lr, p) = var::kupiec(n, x, c)?;
            plain(obj([("lr_uc", lr.into()), ("p_value", p.into())]))
        },
        "risk.backtest.christoffersen" => {
            let e = i
                .array("exceptions")?
                .iter()
                .map(|v| match v {
                    Json::Bool(b) => Ok(*b),
                    _ => i.fail("exceptions", "expected booleans"),
                })
                .collect::<Result<Vec<_>>>()?;
            let c = i.f64("confidence")?;
            i.gate()?;
            let r = var::christoffersen(&e, c)?;
            let [n00, n01, n10, n11] = r.transitions;
            plain(obj([
                ("lr_uc", r.lr_uc.into()),
                ("lr_ind", r.lr_ind.into()),
                ("lr_cc", r.lr_cc.into()),
                ("p_uc", r.p_uc.into()),
                ("p_ind", r.p_ind.into()),
                ("p_cc", r.p_cc.into()),
                (
                    "transitions",
                    obj([
                        ("n00", n00.into()),
                        ("n01", n01.into()),
                        ("n10", n10.into()),
                        ("n11", n11.into()),
                    ]),
                ),
            ]))
        },
        "risk.backtest.traffic_light" => {
            let (n, x, c) = (i.int("observations")?, i.int("exceptions")?, i.f64("confidence")?);
            i.gate()?;
            let (p, zone, plus) = var::traffic_light(n, x, c)?;
            plain(obj([
                ("cumulative_probability", p.into()),
                ("zone", zone.into()),
                ("plus_factor", plus.into()),
            ]))
        },
        "risk.frtb.girr_delta" => {
            let sens = items(i, "sensitivities")?
                .iter()
                .map(|s| {
                    let f = s.str("risk_factor")?;
                    let Some(factor) = frtb::Factor::parse(f) else {
                        return s.fail("risk_factor", "unknown risk factor");
                    };
                    Ok(frtb::Sensitivity {
                        currency: s.str("currency")?.to_string(),
                        curve: s.str("curve")?.to_string(),
                        factor,
                        sensitivity: s.f64("sensitivity")?,
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            let red = i.bool_or("specified_currency_reduction", false)?;
            let rep = match i.opt("reporting_currency") {
                None | Some(Json::Null) => None,
                Some(_) => Some(i.str("reporting_currency")?),
            };
            i.gate()?;
            let r = frtb::girr_delta(&sens, red, rep)?;
            let scen: Vec<(String, Json)> = r
                .scenarios
                .iter()
                .map(|s| {
                    let b: Vec<Json> = s
                        .buckets
                        .iter()
                        .map(|b| {
                            obj([
                                ("currency", b.currency.as_str().into()),
                                ("k", b.k.into()),
                                ("s", b.s.into()),
                                ("s_used", b.s_used.into()),
                            ])
                        })
                        .collect();
                    (
                        s.name.to_string(),
                        obj([
                            ("buckets", Json::Arr(b)),
                            ("delta", s.delta.into()),
                            ("alternative_used", Json::Bool(s.alternative_used)),
                        ]),
                    )
                })
                .collect();
            plain(obj([
                ("scenarios", Json::Obj(scen)),
                ("capital", r.capital.into()),
                ("binding_scenario", r.binding_scenario.into()),
            ]))
        },
        "risk.curve.par" => {
            let c = overnight(i, "convention")?;
            let (t, q, m) = (i.date("as_of")?, ois_quotes(i)?, interpolation(i)?);
            let (p, (bp, scheme)) = (product(i)?, bump_inputs(i)?);
            i.gate()?;
            let r = risk_curve::par(&c, t, &q, m, &p, Bump::new(bp, scheme)?)?;
            plain(obj([
                ("value", r.value.into()),
                ("par_dv01", r.par_dv01.into()),
                ("par_buckets", r.par_buckets.into()),
            ]))
        },
        "risk.curve.key_rate" => {
            let curve = curve_input(i, "curve")?;
            let mode = i.str("mode")?;
            if !["TRIANGULAR", "PILLAR"].contains(&mode) {
                return i.fail("mode", "unknown mode");
            }
            let keys = key_dates(i)?;
            let (p, (bp, scheme)) = (product(i)?, bump_inputs(i)?);
            i.gate()?;
            let bump = Bump::new(bp, scheme)?;
            let mode = match (mode, keys) {
                ("TRIANGULAR", Some(k)) => KeyMode::Triangular(k),
                ("PILLAR", None) => KeyMode::Pillar,
                (_, k) => {
                    // After bump_bp and notional: E_DOMAIN outranks E_INPUT.
                    risk_curve::check_notional(&p)?;
                    return fail(
                        "E_INPUT",
                        if k.is_some() {
                            "key_dates must be null in PILLAR mode"
                        } else {
                            "TRIANGULAR needs key_dates"
                        },
                    );
                }
            };
            let r = risk_curve::key_rate(&curve, &mode, &p, bump)?;
            plain(obj([
                ("value", r.value.into()),
                ("key_rates", r.key_rates.into()),
                ("zero_dv01", r.zero_dv01.into()),
            ]))
        },
        "risk.curve.jacobian" => {
            let c = overnight(i, "convention")?;
            let (t, q, m) = (i.date("as_of")?, ois_quotes(i)?, interpolation(i)?);
            let bp = i.f64_or("bump_bp", 1.0)?;
            i.gate()?;
            let r = risk_curve::jacobian(&c, t, &q, m, bp)?;
            let dates: Vec<String> = r.pillar_dates.iter().map(ToString::to_string).collect();
            let rows: Vec<Json> = r.jacobian.into_iter().map(Json::from).collect();
            plain(obj([
                ("pillar_dates", dates.into()),
                ("zero_rates", r.zero_rates.into()),
                ("jacobian", rows.into()),
            ]))
        },
        "risk.pnl.explain" => {
            let c = overnight(i, "convention")?;
            let (t, m) = (i.date("as_of")?, interpolation(i)?);
            let (s, e) = (
                ois_quotes_at(i, "quotes_start")?,
                ois_quotes_at(i, "quotes_end")?,
            );
            let (p, bp) = (product(i)?, i.f64_or("bump_bp", 1.0)?);
            i.gate()?;
            let r = risk_curve::pnl_explain(&c, t, m, &s, &e, &p, bp)?;
            plain(obj([
                ("value_start", r.value_start.into()),
                ("value_end", r.value_end.into()),
                ("full_pnl", r.full_pnl.into()),
                ("par_buckets", r.par_buckets.into()),
                ("risk_pnl", r.risk_pnl.into()),
                ("gross_risk_pnl", r.gross_risk_pnl.into()),
                ("unexplained", r.unexplained.into()),
                ("threshold", r.threshold.into()),
                ("explained", r.explained.into()),
            ]))
        }
}

pub(crate) fn interpolation(i: &Inputs) -> Result<Interpolation> {
    match i.str("interpolation")? {
        "TENSION_SPLINE" => match i.opt_f64("tension")? {
            None => quantforge_core::error::fail("E_INPUT", "TENSION_SPLINE needs tension"),
            Some(s) if !(s > 0.0 && s <= 1000.0) => {
                quantforge_core::error::fail("E_DOMAIN", "tension must be in (0, 1000]")
            }
            Some(s) => Ok(Interpolation::TensionSpline(s)),
        },
        "HYBRID" => match i.0.get("step_end") {
            None => quantforge_core::error::fail("E_INPUT", "HYBRID needs step_end"),
            Some(_) => Ok(Interpolation::Hybrid(i.date("step_end")?)),
        },
        s => match Interpolation::parse(s) {
            Some(v) => Ok(v),
            None => i.fail("interpolation", "unknown interpolation"),
        },
    }
}

pub(crate) fn ois_quotes(i: &Inputs) -> Result<Vec<OisQuote>> {
    ois_quotes_at(i, "quotes")
}

pub(crate) fn ois_quotes_at(i: &Inputs, k: &str) -> Result<Vec<OisQuote>> {
    items(i, k)?
        .iter()
        .map(|q| {
            let t = tenor(q, "tenor")?;
            let (bid, ask) = match q.opt_f64("rate")? {
                Some(r) => (r, r),
                None => (q.f64("bid")?, q.f64("ask")?),
            };
            Ok(OisQuote { tenor: t, bid, ask })
        })
        .collect()
}

/// Keys of other models are `E_SCHEMA`, whatever their value.
pub(crate) fn only(i: &Inputs, keys: &[&str]) -> Result<()> {
    for k in [
        "spot",
        "rate",
        "yield",
        "forward",
        "discount_factor",
        "shift",
    ] {
        if !keys.contains(&k) && i.0.get(k).is_some() {
            return i.fail(k, "not an input of this model");
        }
    }
    Ok(())
}

pub(crate) fn option_inputs(i: &Inputs) -> Result<Option_> {
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

pub(crate) fn rows(m: Vec<Vec<f64>>) -> Json {
    Json::Arr(m.into_iter().map(Into::into).collect())
}

pub(crate) fn product(i: &Inputs) -> Result<Product> {
    let p = sub(i, "product")?;
    match p.str("kind")? {
        "OIS" => Ok(Product::Ois(ois_trade(&p)?)),
        "BOND" => Ok(Product::Bond {
            bond: bond_fields(&sub(&p, "bond")?)?,
            settlement: p.date("settlement")?,
            notional: p.f64("notional")?,
        }),
        _ => p.fail("kind", "unknown product kind"),
    }
}

/// `bump_bp` (default 1) and `scheme` (default `CENTRAL`), read without the `E_DOMAIN` check.
pub(crate) fn bump_inputs(i: &Inputs) -> Result<(f64, Scheme)> {
    let bp = i.f64_or("bump_bp", 1.0)?;
    let scheme = match i.opt("scheme").map(|_| i.str("scheme")).transpose()? {
        None | Some("CENTRAL") => Scheme::Central,
        Some("FORWARD") => Scheme::Forward,
        Some(_) => return i.fail("scheme", "unknown scheme"),
    };
    Ok((bp, scheme))
}

/// `key_dates`: `null` or absent is `None`; anything else must be an array of dates.
pub(crate) fn key_dates(i: &Inputs) -> Result<Option<Vec<quantforge_core::dates::Date>>> {
    match i.opt("key_dates") {
        None | Some(Json::Null) => Ok(None),
        Some(_) => Ok(Some(i.dates("key_dates")?)),
    }
}

fn var_json(r: var::VarEs, tail: bool) -> Json {
    let mut v: Vec<(String, Json)> = vec![("var".into(), r.var.into()), ("es".into(), r.es.into())];
    if tail {
        v.push(("tail_count".into(), r.tail_count.into()));
    }
    Json::Obj(v)
}
