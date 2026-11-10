//! `rates.*` operations: read the inputs, call the library, shape the outputs.
use super::core::kind;
use super::eq::items;
use super::fx::side;
use super::infl::model;
use super::risk::interpolation;
use super::risk::ois_quotes;
use super::risk::ois_quotes_at;
use super::usecase::tenor_text;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::caps;
use quantforge_core::caps::CapTrade;
use quantforge_core::caps::SwaptionTrade;
use quantforge_core::conventions;
use quantforge_core::conventions::Overnight;
use quantforge_core::conventions::TERM_INDEX;
use quantforge_core::curve::Curve;
use quantforge_core::curve::CurveInput;
use quantforge_core::curve::Discount;
use quantforge_core::curve::SolveMethod;
use quantforge_core::dates::Date;
use quantforge_core::error::Result;
use quantforge_core::error::fail;
use quantforge_core::garch::Start;
use quantforge_core::joint;
use quantforge_core::json::Json;
use quantforge_core::json::obj;
use quantforge_core::ois;
use quantforge_core::ois::OisCurveProblem;
use quantforge_core::ois::OisTrade;
use quantforge_core::projection;
use quantforge_core::projection::ProjectionQuote;
use quantforge_core::rates_overnight;
use quantforge_core::rates_overnight::CsaFx;
use quantforge_core::rates_overnight::Shift;
use quantforge_core::rates_overnight::StepCurve;
use quantforge_core::rates_vol;
use quantforge_core::schedule;

super::registry! {
(op, i)
        "rates.schedule.generate" => {
            let (s, e) = (i.date("start")?, i.date("end")?);
            let f = i.int("frequency_months")?;
            if ![1, 2, 3, 4, 6, 12].contains(&f) {
                return i.fail("frequency_months", "not listed");
            }
            let c = i.calendar("calendar")?;
            let eom = match i.req("end_of_month")? {
                Json::Bool(b) => *b,
                _ => return i.fail("end_of_month", "expected a boolean"),
            };
            let lag = i.int("payment_lag")?;
            let rows: Vec<Json> = schedule::generate(s, e, f, &c, eom, lag)?
                .iter()
                .map(|p| {
                    obj([
                        ("start", p.start.to_string().into()),
                        ("end", p.end.to_string().into()),
                        ("payment", p.payment.to_string().into()),
                    ])
                })
                .collect();
            plain(obj([("periods", rows.into())]))
        },
        "rates.curve.discount" => {
            let c = curve_input(i, "curve")?;
            let dates = i.dates("dates")?;
            i.gate()?;
            let c = Curve::new(&c)?;
            let d = dates.iter().map(|d| c.discount(*d));
            let d = d.collect::<Result<Vec<_>>>()?;
            let z = dates.iter().map(|d| c.zero_rate(*d));
            let z = z.collect::<Result<Vec<_>>>()?;
            plain(obj([
                ("discount_factors", d.into()),
                ("zero_rates", z.into()),
            ]))
        },
        "rates.funding.curve" => {
            let c = curve_input(i, "discount")?;
            let quotes = items(i, "quotes")?
                .iter()
                .map(|q| Ok((q.date("end")?, q.f64("rate")?)))
                .collect::<Result<Vec<_>>>()?;
            let dates = match i.0.get("dates") {
                None => Vec::new(),
                Some(_) => i.dates("dates")?,
            };
            i.gate()?;
            let f = quantforge_core::funding::funding_curve(&Curve::new(&c)?, &quotes, &dates)?;
            let pillars: Vec<Json> = f
                .pillars
                .iter()
                .map(|(d, v)| obj([("date", d.to_string().into()), ("discount_factor", (*v).into())]))
                .collect();
            plain(obj([
                ("spreads", f.spreads.into()),
                ("pillars", Json::Arr(pillars)),
                ("discount_factors", f.discount_factors.into()),
            ]))
        },
        "rates.curve.joint_solve" => {
            let as_of = i.date("as_of")?;
            let curves = items(i, "curves")?
                .iter()
                .map(joint_curve)
                .collect::<Result<Vec<_>>>()?;
            let insts = items(i, "instruments")?
                .iter()
                .map(joint_instrument)
                .collect::<Result<Vec<_>>>()?;
            i.gate()?;
            let r = joint::joint_solve(as_of, &curves, &insts)?;
            let curves: Vec<Json> = r
                .curves
                .iter()
                .map(|c| match c {
                    joint::CurveOut::Pillars { name, pillars } => obj([
                        ("name", name.as_str().into()),
                        (
                            "pillars",
                            Json::Arr(
                                pillars
                                    .iter()
                                    .map(|(d, v)| {
                                        obj([
                                            ("date", d.to_string().into()),
                                            ("discount_factor", (*v).into()),
                                        ])
                                    })
                                    .collect(),
                            ),
                        ),
                    ]),
                    joint::CurveOut::Steps { name, base_rate, step_rates } => obj([
                        ("name", name.as_str().into()),
                        ("base_rate", (*base_rate).into()),
                        ("step_rates", step_rates.clone().into()),
                    ]),
                })
                .collect();
            let turns: Vec<Json> = r
                .turn_factors
                .iter()
                .map(|(c, d, f)| {
                    obj([
                        ("curve", c.as_str().into()),
                        ("date", d.to_string().into()),
                        ("factor", (*f).into()),
                    ])
                })
                .collect();
            let strs = |v: &[String]| Json::Arr(v.iter().map(|s| s.as_str().into()).collect());
            let rows = |m: &[Vec<f64>]| Json::Arr(m.iter().map(|r| r.clone().into()).collect());
            Ok(Outcome {
                outputs: obj([
                    ("curves", Json::Arr(curves)),
                    ("turn_factors", Json::Arr(turns)),
                    (
                        "jacobian",
                        obj([
                            ("unknowns", strs(&r.unknowns)),
                            ("quotes", strs(&r.quotes)),
                            ("matrix", rows(&r.jacobian)),
                        ]),
                    ),
                    ("turn_sensitivity", rows(&r.turn_sensitivity)),
                ]),
                diagnostics: repricing(r.max_repricing_error),
            })
        },
        "rates.curve.inspect" => {
            let c = curve_input(i, "curve")?;
            let dates = i.dates("dates")?;
            i.gate()?;
            let c = Curve::new(&c)?;
            let d = dates.iter().map(|d| c.discount(*d));
            let d = d.collect::<Result<Vec<_>>>()?;
            let z = dates.iter().map(|d| c.zero_rate(*d));
            let z = z.collect::<Result<Vec<_>>>()?;
            let f = dates.iter().map(|d| c.instantaneous_forward(*d));
            let f = f.collect::<Result<Vec<_>>>()?;
            plain(obj([
                ("discount_factors", d.into()),
                ("zero_rates", z.into()),
                ("instantaneous_forwards", f.into()),
            ]))
        },
        "rates.curve.forward" => {
            let c = curve_input(i, "curve")?;
            let (s, e, dc) = (i.date("start")?, i.date("end")?, i.str("day_count")?);
            i.gate()?;
            let f = Curve::new(&c)?.forward(s, e, dc)?;
            plain(obj([("forward", f.into())]))
        },
        "rates.ois.bootstrap" => {
            let c = overnight(i, "convention")?;
            let (t, q, m) = (i.date("as_of")?, ois_quotes(i)?, interpolation(i)?);
            let method = solve_method(i)?;
            let j = jumps(i, false)?;
            i.gate()?;
            let p = OisCurveProblem::with_jumps(&c, t, &q, m, &j)?;
            let s = p.solve(&p.mids, method)?;
            Ok(Outcome {
                outputs: pillars_json(&s.dates, &s.logs),
                diagnostics: repricing(s.max_repricing_error),
            })
        },
        "rates.ois.compound" => {
            let r = i.reals("rates")?;
            let mut days = Vec::new();
            for v in i.array("days")? {
                match v.as_int() {
                    Some(n) => days.push(n),
                    None => return i.fail("days", "expected integers"),
                }
            }
            let b = i.int("denominator")?;
            if b != 360 && b != 365 {
                return i.fail("denominator", "not listed");
            }
            i.gate()?;
            plain(obj([(
                "compounded_rate",
                ois::compound(&r, &days, b)?.into(),
            )]))
        },
        "rates.ois.pv" => {
            let (c, t, id) = (curve_input(i, "curve")?, ois_trade(i)?, snapshot_id(i)?);
            i.gate()?;
            let (v, par, a) = ois::pv(&Curve::new(&c)?, &t, id)?;
            plain(obj([
                ("valuation", v.to_json()),
                ("par_rate", par.into()),
                ("annuity", a.into()),
            ]))
        },
        "rates.projection.bootstrap" => {
            let d = curve_input(i, "discount")?;
            term_index(i)?;
            let (t, q, m) = (i.date("as_of")?, projection_quotes(i)?, interpolation(i)?);
            i.gate()?;
            let s = projection::bootstrap(&Curve::new(&d)?, t, &q, m)?;
            Ok(Outcome {
                outputs: pillars_json(&s.dates, &s.logs),
                diagnostics: repricing(s.max_repricing_error),
            })
        },
        "rates.swap.pv" => {
            let (d, p) = (curve_input(i, "discount")?, curve_input(i, "projection")?);
            let t = sub(i, "trade")?;
            term_index(&t)?;
            let (m, k, n) = (
                t.int("tenor_months")?,
                t.f64("fixed_rate")?,
                t.f64("notional")?,
            );
            let (pay, id) = (side(&t, "PAY", "RECEIVE")?, snapshot_id(i)?);
            i.gate()?;
            let (d, p) = (Curve::new(&d)?, Curve::new(&p)?);
            let (v, par) = projection::swap_pv(&d, &p, m, k, n, pay, id)?;
            plain(obj([("valuation", v.to_json()), ("par_rate", par.into())]))
        },
        "rates.fra.pv" => {
            let (d, p) = (curve_input(i, "discount")?, curve_input(i, "projection")?);
            let t = sub(i, "trade")?;
            term_index(&t)?;
            let (s, k, n) = (t.date("start")?, t.f64("fixed_rate")?, t.f64("notional")?);
            let (pay, id) = (side(&t, "PAY", "RECEIVE")?, snapshot_id(i)?);
            i.gate()?;
            let (d, p) = (Curve::new(&d)?, Curve::new(&p)?);
            let (v, f) = projection::fra_pv(&d, &p, s, k, n, pay, id)?;
            plain(obj([
                ("valuation", v.to_json()),
                ("forward_rate", f.into()),
            ]))
        },
        "rates.basis.spread" => {
            let (d, p) = (curve_input(i, "discount")?, curve_input(i, "projection")?);
            term_index(i)?;
            let m = i.int("tenor_months")?;
            i.gate()?;
            let s = projection::basis_spread(&Curve::new(&d)?, &Curve::new(&p)?, m)?;
            plain(obj([("spread", s.into())]))
        },
        "rates.ois.compound_dated" => {
            let c = overnight_record(i);
            let (s, e) = (i.date("start")?, i.date("end")?);
            let Some(m) = Shift::parse(i.str("method")?) else {
                return i.fail("method", "unknown method");
            };
            let (k, f) = (i.int("shift_days")?, fixings(i)?);
            i.gate()?;
            let r = rates_overnight::compound_dated(&c?, s, e, m, k, &f)?;
            plain(compounded(r))
        },
        "rates.fallback.rate" => {
            let Some((index, spread)) = rates_overnight::fallback_spread(i.str("ibor")?) else {
                return i.fail("ibor", "not a listed IBOR");
            };
            let (s, e, f) = (i.date("start")?, i.date("end")?, fixings(i)?);
            i.gate()?;
            let c = conventions::overnight(index).expect("listed index");
            let r = rates_overnight::compound_dated(&c, s, e, Shift::ObservationShift, 2, &f)?;
            plain(obj([
                ("compounded_rate", r.compounded_rate.into()),
                ("spread_adjustment", spread.into()),
                ("fallback_rate", (r.compounded_rate + spread).into()),
            ]))
        },
        "rates.ois.step_curve" => {
            let (t, base) = (i.date("as_of")?, i.f64("base_rate")?);
            let (steps, j) = (dated(i, "steps", "rate")?, jumps(i, true)?);
            let dates = i.dates("dates")?;
            i.gate()?;
            nonempty_dates(&dates)?;
            let c = StepCurve::new(t, base, steps, j)?;
            let d = dates.iter().map(|d| c.discount(*d));
            let d = d.collect::<Result<Vec<_>>>()?;
            let f = dates.iter().map(|d| c.forward(*d));
            let f = f.collect::<Result<Vec<_>>>()?;
            plain(obj([
                ("discount_factors", d.into()),
                ("overnight_forwards", f.into()),
            ]))
        },
        "rates.ois.fit_steps" => {
            let c = overnight(i, "convention")?;
            let (t, steps) = (i.date("as_of")?, i.dates("step_dates")?);
            let mut quotes = Vec::new();
            for q in items(i, "quotes")? {
                quotes.push((tenor(&q, "tenor")?, q.f64("rate")?));
            }
            let j = jumps(i, true)?;
            i.gate()?;
            let fit = rates_overnight::fit_steps(&c, t, &steps, &quotes, &j)?;
            Ok(Outcome {
                outputs: obj([
                    ("base_rate", fit.base_rate.into()),
                    ("step_rates", fit.step_rates.into()),
                ]),
                diagnostics: repricing(fit.max_repricing_error),
            })
        },
        "rates.futures.convexity" => {
            let (p, s, e) = (i.f64("price")?, i.f64("start_years")?, i.f64("end_years")?);
            let (v, a) = (i.f64("sigma")?, i.f64("mean_reversion")?);
            let r = rates_overnight::convexity(p, s, e, v, a)?;
            plain(obj([
                ("futures_rate", r.futures_rate.into()),
                ("convexity", r.convexity.into()),
                ("forward_rate", r.forward_rate.into()),
            ]))
        },
        "rates.csa.discount" => {
            let (c, s) = (curve_input(i, "curve")?, i.f64("collateral_spread")?);
            present(i, "fx")?;
            let fx = if i.opt("fx").is_none() {
                None
            } else {
                let f = sub(i, "fx")?;
                Some(CsaFx {
                    spot: f.f64("spot")?,
                    forwards: dated(&f, "forwards", "forward")?,
                })
            };
            let dates = i.dates("dates")?;
            i.gate()?;
            let d = rates_overnight::csa_discount(&Curve::new(&c)?, s, fx.as_ref(), &dates)?;
            plain(obj([("discount_factors", d.into())]))
        },
        "rates.basis.ois_spread" => {
            let (c, t) = (overnight(i, "convention")?, tenor(i, "tenor")?);
            let d = curve_input(i, "discount")?;
            let (a, b) = (
                curve_input(i, "projection_a")?,
                curve_input(i, "projection_b")?,
            );
            i.gate()?;
            let (d, a, b) = (Curve::new(&d)?, Curve::new(&a)?, Curve::new(&b)?);
            let s = ois::ois_spread(&c, t, &d, &a, &b)?;
            plain(obj([("spread", s.into())]))
        },
        "rates.curve.joint_bootstrap" => {
            let c = overnight(i, "convention")?;
            term_index(i)?;
            let (t, q) = (i.date("as_of")?, ois_quotes_at(i, "ois_quotes")?);
            let p = projection_quotes_at(i, "term_quotes")?;
            let (m, method) = (interpolation(i)?, solve_method(i)?);
            i.gate()?;
            let (d, p) = rates_overnight::joint_bootstrap(&c, t, &q, &p, m, method)?;
            let field = |j: Json| match j {
                Json::Obj(mut v) => v.remove(0).1,
                other => other,
            };
            Ok(Outcome {
                outputs: obj([
                    ("discount_pillars", field(pillars_json(&d.dates, &d.logs))),
                    ("projection_pillars", field(pillars_json(&p.dates, &p.logs))),
                ]),
                diagnostics: repricing(d.max_repricing_error.max(p.max_repricing_error)),
            })
        },
        "rates.cap.price" => {
            let (d, p) = (curve_input(i, "discount")?, curve_input(i, "projection")?);
            let normal = vol_model(i)?;
            let vols = match i.req("vol")? {
                Json::Arr(_) => i.reals("vol")?,
                _ => vec![i.f64("vol")?],
            };
            let t = sub(i, "trade")?;
            let trade = CapTrade {
                cap: match t.str("type")? {
                    "CAP" => true,
                    "FLOOR" => false,
                    _ => return t.fail("type", "unknown type"),
                },
                start_months: t.int("start_months")?,
                tenor_months: t.int("tenor_months")?,
                strike: t.f64("strike")?,
                notional: t.f64("notional")?,
            };
            i.gate()?;
            let c = caps::cap_price(&Curve::new(&d)?, &Curve::new(&p)?, normal, &vols, &trade)?;
            let total: f64 = c.iter().sum();
            plain(obj([("price", total.into()), ("caplets", c.into())]))
        },
        "rates.swaption.price" => {
            let (d, p) = (curve_input(i, "discount")?, curve_input(i, "projection")?);
            let (normal, vol) = (vol_model(i)?, i.f64("vol")?);
            let t = sub(i, "trade")?;
            let trade = SwaptionTrade {
                payer: match t.str("type")? {
                    "PAYER" => true,
                    "RECEIVER" => false,
                    _ => return t.fail("type", "unknown type"),
                },
                expiry_months: t.int("expiry_months")?,
                tenor_months: t.int("tenor_months")?,
                strike: t.f64("strike")?,
                notional: t.f64("notional")?,
            };
            i.gate()?;
            let (pr, f, a) =
                caps::swaption_price(&Curve::new(&d)?, &Curve::new(&p)?, normal, vol, &trade)?;
            plain(obj([
                ("price", pr.into()),
                ("forward_rate", f.into()),
                ("annuity", a.into()),
            ]))
        },
        "rates.swaption.price_cube" => {
            let (d, p) = curves(i)?;
            let c = sub(i, "cube")?;
            let cube = rates_vol::Cube {
                expiries_months: ints(&c, "expiries_months")?,
                tenors_months: ints(&c, "tenors_months")?,
                alpha: c.matrix("alpha")?,
                beta: c.matrix("beta")?,
                rho: c.matrix("rho")?,
                nu: c.matrix("nu")?,
            };
            let t = sub(i, "trade")?;
            let trade = rates_vol::CubeTrade {
                payer: kind(&t, "PAYER", "RECEIVER")?,
                expiry_months: t.int("expiry_months")?,
                tenor_months: t.int("tenor_months")?,
                strike: t.f64("strike")?,
                notional: t.f64("notional")?,
            };
            i.gate()?;
            let r = rates_vol::price_cube(&Curve::new(&d)?, &Curve::new(&p)?, &cube, &trade)?;
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
        },
        "rates.cap.strip" => {
            let (d, p) = curves(i)?;
            let (tenors, vols) = (ints(i, "cap_tenors_months")?, i.reals("flat_vols")?);
            let x = rates_vol::Strip {
                normal: model(i)?,
                start_months: i.int("start_months")?,
                strike: i.f64("strike")?,
                cap_tenors_months: &tenors,
                flat_vols: &vols,
                notional: i.f64("notional")?,
            };
            i.gate()?;
            let (cv, prices) = rates_vol::strip_caplets(&Curve::new(&d)?, &Curve::new(&p)?, &x)?;
            plain(obj([
                ("caplet_vols", cv.into()),
                ("cap_prices", prices.into()),
            ]))
        },
        "rates.bondfut.option_price" => {
            let o = futures_option(i)?;
            let (v, n) = (i.f64("vol")?, i.f64("contract_size")?);
            let (p, cv) = rates_vol::futures_option_price(&o, v, n)?;
            plain(obj([("price", p.into()), ("contract_value", cv.into())]))
        },
        "rates.bondfut.implied_vol" => {
            let o = futures_option(i)?;
            let (pr, y) = (i.f64("premium")?, i.f64("ctd_yield")?);
            let dm = i.f64("ctd_modified_duration")?;
            let (pv, yv) = rates_vol::futures_implied_vol(&o, pr, y, dm)?;
            plain(obj([("price_vol", pv.into()), ("yield_vol", yv.into())]))
        }
}

pub(crate) fn sub<'a>(i: &Inputs<'a>, k: &str) -> Result<Inputs<'a>> {
    let v = i.req(k)?;
    if !matches!(v, Json::Obj(_)) {
        return i.fail(k, "expected an object");
    }
    Ok(Inputs::new(v))
}

pub(crate) fn curve_input(i: &Inputs, k: &str) -> Result<CurveInput> {
    let c = sub(i, k)?;
    let mut pillars = Vec::new();
    for p in items(&c, "pillars")? {
        pillars.push((p.date("date")?, p.f64("discount_factor")?));
    }
    Ok(CurveInput {
        as_of: c.date("as_of")?,
        interpolation: interpolation(&c)?,
        pillars,
        jumps: jumps(&c, false)?,
    })
}

/// Stage D `jumps`: may be absent unless `required`; `null` is `E_SCHEMA` (ruling D10).
pub(crate) fn jumps(i: &Inputs, required: bool) -> Result<Vec<(Date, f64)>> {
    match i.0.get("jumps") {
        None if !required => return Ok(Vec::new()),
        None | Some(Json::Null) => return i.fail("jumps", "is required and not null"),
        _ => {}
    }
    items(i, "jumps")?
        .iter()
        .map(|j| Ok((j.date("date")?, j.f64("factor")?)))
        .collect()
}

pub(crate) fn tenor(i: &Inputs, k: &str) -> Result<(i64, char)> {
    tenor_text(i, k, i.str(k)?)
}

pub(crate) fn overnight(i: &Inputs, k: &str) -> Result<Overnight> {
    match conventions::overnight(i.str(k)?) {
        Some(c) => Ok(c),
        None => i.fail(k, "unknown convention"),
    }
}

pub(crate) fn term_index(i: &Inputs) -> Result<()> {
    if i.str("index")? != TERM_INDEX {
        return i.fail("index", "unknown index");
    }
    Ok(())
}

pub(crate) fn solve_method(i: &Inputs) -> Result<SolveMethod> {
    match i.str("method")? {
        "SEQUENTIAL" => Ok(SolveMethod::Sequential),
        "GLOBAL" => Ok(SolveMethod::Global),
        _ => i.fail("method", "unknown method"),
    }
}

pub(crate) fn ois_trade(i: &Inputs) -> Result<OisTrade> {
    let t = sub(i, "trade")?;
    Ok(OisTrade {
        convention: overnight(&t, "convention")?,
        tenor: tenor(&t, "tenor")?,
        fixed_rate: t.f64("fixed_rate")?,
        notional: t.f64("notional")?,
        pay: side(&t, "PAY", "RECEIVE")?,
    })
}

pub(crate) fn snapshot_id(i: &Inputs) -> Result<Option<String>> {
    let id = i.opt("snapshot_id").map(|_| i.str("snapshot_id"));
    Ok(id.transpose()?.map(str::to_string))
}

pub(crate) fn pillars_json(dates: &[Date], logs: &[f64]) -> Json {
    let rows: Vec<Json> = dates
        .iter()
        .zip(logs)
        .map(|(d, l)| {
            obj([
                ("date", d.to_string().into()),
                ("discount_factor", l.exp().into()),
            ])
        })
        .collect();
    obj([("pillars", rows.into())])
}

pub(crate) fn repricing(e: f64) -> Json {
    obj([("max_repricing_error", e.into())])
}

pub(crate) fn projection_quotes(i: &Inputs) -> Result<Vec<ProjectionQuote>> {
    projection_quotes_at(i, "quotes")
}

pub(crate) fn projection_quotes_at(i: &Inputs, k: &str) -> Result<Vec<ProjectionQuote>> {
    items(i, k)?
        .iter()
        .map(|q| {
            let rate = q.f64("rate")?;
            Ok(match q.str("type")? {
                "DEPOSIT" => ProjectionQuote::Deposit {
                    months: q.int("months")?,
                    rate,
                },
                "FRA" => ProjectionQuote::Fra {
                    start_months: q.int("start_months")?,
                    rate,
                },
                "SWAP" => ProjectionQuote::Swap {
                    months: q.int("months")?,
                    rate,
                },
                _ => return q.fail("type", "unknown quote type"),
            })
        })
        .collect()
}

/// Ruling C9: the key must be present, and `null` carries meaning.
pub(crate) fn present(i: &Inputs, k: &str) -> Result<()> {
    match i.0.get(k) {
        None => i.fail(k, "is required"),
        _ => Ok(()),
    }
}

pub(crate) fn fixings(i: &Inputs) -> Result<Vec<(Date, f64)>> {
    items(i, "fixings")?
        .iter()
        .map(|f| Ok((f.date("date")?, f.f64("rate")?)))
        .collect()
}

pub(crate) fn dated(i: &Inputs, k: &str, v: &str) -> Result<Vec<(Date, f64)>> {
    items(i, k)?
        .iter()
        .map(|f| Ok((f.date("date")?, f.f64(v)?)))
        .collect()
}

/// An `OVERNIGHT` record: a known non-overnight id is `E_INPUT`, an unknown one `E_SCHEMA`.
pub(crate) fn overnight_record(i: &Inputs) -> Result<Overnight> {
    let id = i.str("convention")?;
    match (conventions::overnight(id), conventions::lookup(id)) {
        (Some(c), _) => Ok(c),
        (None, Some(_)) => fail("E_INPUT", "convention is not OVERNIGHT"),
        (None, None) => i.fail("convention", "unknown convention"),
    }
}

pub(crate) fn compounded(r: rates_overnight::Compounded) -> Json {
    obj([
        ("compounded_rate", r.compounded_rate.into()),
        ("accrual", r.accrual.into()),
        ("interest", r.interest.into()),
    ])
}

pub(crate) fn nonempty_dates(dates: &[Date]) -> Result<()> {
    if dates.is_empty() {
        return fail("E_INPUT", "no dates");
    }
    Ok(())
}

/// `true` for `BACHELIER`, `false` for `BLACK_76`.
pub(crate) fn vol_model(i: &Inputs) -> Result<bool> {
    match i.str("model")? {
        "BLACK_76" => Ok(false),
        "BACHELIER" => Ok(true),
        _ => i.fail("model", "unknown model"),
    }
}

/// `initial_variance`: `"SAMPLE"` or a number; another string is `E_INPUT`, another type
/// `E_SCHEMA`. The string check is returned apart so it can run in its spec order.
pub(crate) fn start(i: &Inputs) -> Result<std::result::Result<Start, ()>> {
    match i.req("initial_variance")? {
        Json::Str(s) if s == "SAMPLE" => Ok(Ok(Start::Sample)),
        Json::Str(_) => Ok(Err(())),
        _ => Ok(Ok(Start::Given(i.f64("initial_variance")?))),
    }
}

pub(crate) fn ints(i: &Inputs, k: &str) -> Result<Vec<i64>> {
    i.array(k)?
        .iter()
        .map(|v| {
            v.as_int()
                .map_or_else(|| i.fail(k, "expected integers"), Ok)
        })
        .collect()
}

pub(crate) fn curves(i: &Inputs) -> Result<(CurveInput, CurveInput)> {
    Ok((curve_input(i, "discount")?, curve_input(i, "projection")?))
}

pub(crate) fn futures_option(i: &Inputs) -> Result<rates_vol::FuturesOption> {
    Ok(rates_vol::FuturesOption {
        call: kind(i, "CALL", "PUT")?,
        futures_price: i.f64("futures_price")?,
        strike: i.f64("strike")?,
        expiry_years: i.f64("expiry_years")?,
        discount_factor: i.f64("discount_factor")?,
    })
}

fn joint_curve(c: &Inputs) -> Result<joint::CurveSpec> {
    let turns = match c.0.get("turns") {
        None => Vec::new(),
        Some(_) => items(c, "turns")?
            .iter()
            .map(|t| t.date("date"))
            .collect::<Result<Vec<_>>>()?,
    };
    let kind = match c.str("type")? {
        "OIS" => joint::CurveKind::Ois {
            convention: overnight(c, "convention")?,
            interpolation: interpolation(c)?,
            jumps: jumps(c, false)?,
        },
        "OIS_STEPS" => joint::CurveKind::Steps {
            convention: overnight(c, "convention")?,
            step_dates: c.dates("step_dates")?,
            jumps: jumps(c, false)?,
        },
        "PROJECTION" => {
            term_index(c)?;
            joint::CurveKind::Projection {
                discount: c.str("discount")?.to_string(),
                interpolation: interpolation(c)?,
            }
        }
        "XCCY" => {
            let (d, f) = (
                overnight(c, "domestic_convention")?,
                overnight(c, "foreign_convention")?,
            );
            let _ = (d, f);
            joint::CurveKind::Xccy {
                domestic: c.str("domestic")?.to_string(),
                foreign_projection: c.str("foreign_projection")?.to_string(),
                start: c.date("start")?,
                interpolation: interpolation(c)?,
            }
        }
        _ => return c.fail("type", "unknown curve type"),
    };
    Ok(joint::CurveSpec {
        name: c.str("name")?.to_string(),
        kind,
        turns,
    })
}

fn joint_instrument(q: &Inputs) -> Result<joint::InstrumentSpec> {
    let quote = match q.str("type")? {
        "OIS" => joint::Quote::Ois {
            tenor: tenor(q, "tenor")?,
            rate: q.f64("rate")?,
        },
        "FUTURE" => joint::Quote::Future {
            start: q.date("start")?,
            end: q.date("end")?,
            price: q.f64("price")?,
            sigma: q.f64("sigma")?,
            mean_reversion: q.f64("mean_reversion")?,
        },
        "DEPOSIT" => joint::Quote::Projection(ProjectionQuote::Deposit {
            months: q.int("months")?,
            rate: q.f64("rate")?,
        }),
        "FRA" => joint::Quote::Projection(ProjectionQuote::Fra {
            start_months: q.int("start_months")?,
            rate: q.f64("rate")?,
        }),
        "SWAP" => joint::Quote::Projection(ProjectionQuote::Swap {
            months: q.int("months")?,
            rate: q.f64("rate")?,
        }),
        "XCCY" => joint::Quote::Xccy {
            months: q.int("months")?,
            spread: q.f64("spread")?,
        },
        _ => return q.fail("type", "unknown instrument type"),
    };
    Ok(joint::InstrumentSpec {
        id: q.str("id")?.to_string(),
        curve: q.str("curve")?.to_string(),
        quote,
        turn: q.bool_or("turn", false)?,
    })
}
