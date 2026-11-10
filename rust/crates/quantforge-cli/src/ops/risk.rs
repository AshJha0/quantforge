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
use quantforge_core::corr;
use quantforge_core::curve::Interpolation;
use quantforge_core::error::Result;
use quantforge_core::error::fail;
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
use quantforge_core::surface::Position;

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
    match Interpolation::parse(i.str("interpolation")?) {
        Some(v) => Ok(v),
        None => i.fail("interpolation", "unknown interpolation"),
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
