//! Stage D operations: read the inputs, call the library, shape the outputs.
use crate::input::Inputs;
use crate::ops::{Outcome, plain};
use crate::ops_b::{
    curve_input, index, interpolation, items, jumps, ois_quotes_at, overnight, pillars_json,
    projection_quotes_at, repricing, solve_method, sub, tenor,
};
use quantforge_core::conventions::{self, Overnight};
use quantforge_core::curve::{Curve, Discount};
use quantforge_core::curve_fits;
use quantforge_core::dates::Date;
use quantforge_core::error::{Result, fail};
use quantforge_core::json::{Json, obj};
use quantforge_core::ois;
use quantforge_core::rates_d::{self, CsaFx, Shift, StepCurve};

fn fixings(i: &Inputs) -> Result<Vec<(Date, f64)>> {
    items(i, "fixings")?
        .iter()
        .map(|f| Ok((f.date("date")?, f.f64("rate")?)))
        .collect()
}

fn dated(i: &Inputs, k: &str, v: &str) -> Result<Vec<(Date, f64)>> {
    items(i, k)?
        .iter()
        .map(|f| Ok((f.date("date")?, f.f64(v)?)))
        .collect()
}

/// An `OVERNIGHT` record: a known non-overnight id is `E_INPUT`, an unknown one `E_SCHEMA`.
fn overnight_record(i: &Inputs) -> Result<Overnight> {
    let id = i.str("convention")?;
    match (conventions::overnight(id), conventions::lookup(id)) {
        (Some(c), _) => Ok(c),
        (None, Some(_)) => fail("E_INPUT", "convention is not OVERNIGHT"),
        (None, None) => i.fail("convention", "unknown convention"),
    }
}

fn compounded(r: rates_d::Compounded) -> Json {
    obj([
        ("compounded_rate", r.compounded_rate.into()),
        ("accrual", r.accrual.into()),
        ("interest", r.interest.into()),
    ])
}

/// Ruling C9 and D10: present, but `null` allowed.
fn present(i: &Inputs, k: &str) -> Result<()> {
    match i.0.get(k) {
        None => i.fail(k, "is required"),
        _ => Ok(()),
    }
}

/// Optional, but `null` is `E_SCHEMA` (ruling D10).
fn optional_reals(i: &Inputs, k: &str) -> Result<Option<Vec<f64>>> {
    match i.0.get(k) {
        None => Ok(None),
        Some(Json::Null) => i.fail(k, "must not be null"),
        _ => Ok(Some(i.reals(k)?)),
    }
}

fn nonempty_dates(dates: &[Date]) -> Result<()> {
    if dates.is_empty() {
        return fail("E_INPUT", "no dates");
    }
    Ok(())
}

pub fn dispatch(op: &str, i: &Inputs) -> Result<Outcome> {
    match op {
        "rates.ois.compound_dated" => {
            let c = overnight_record(i);
            let (s, e) = (i.date("start")?, i.date("end")?);
            let m = match Shift::parse(i.str("method")?) {
                Some(m) => m,
                None => return i.fail("method", "unknown method"),
            };
            let (k, f) = (i.int("shift_days")?, fixings(i)?);
            i.gate()?;
            let r = rates_d::compound_dated(&c?, s, e, m, k, &f)?;
            plain(compounded(r))
        }
        "rates.fallback.rate" => {
            let Some((index, spread)) = rates_d::fallback_spread(i.str("ibor")?) else {
                return i.fail("ibor", "not a listed IBOR");
            };
            let (s, e, f) = (i.date("start")?, i.date("end")?, fixings(i)?);
            i.gate()?;
            let c = conventions::overnight(index).expect("listed index");
            let r = rates_d::compound_dated(&c, s, e, Shift::ObservationShift, 2, &f)?;
            plain(obj([
                ("compounded_rate", r.compounded_rate.into()),
                ("spread_adjustment", spread.into()),
                ("fallback_rate", (r.compounded_rate + spread).into()),
            ]))
        }
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
        }
        "rates.ois.fit_steps" => {
            let c = overnight(i, "convention")?;
            let (t, steps) = (i.date("as_of")?, i.dates("step_dates")?);
            let mut quotes = Vec::new();
            for q in items(i, "quotes")? {
                quotes.push((tenor(&q, "tenor")?, q.f64("rate")?));
            }
            let j = jumps(i, true)?;
            i.gate()?;
            let fit = rates_d::fit_steps(&c, t, &steps, &quotes, &j)?;
            Ok(Outcome {
                outputs: obj([
                    ("base_rate", fit.base_rate.into()),
                    ("step_rates", fit.step_rates.into()),
                ]),
                diagnostics: repricing(fit.max_repricing_error),
            })
        }
        "rates.futures.convexity" => {
            let (p, s, e) = (i.f64("price")?, i.f64("start_years")?, i.f64("end_years")?);
            let (v, a) = (i.f64("sigma")?, i.f64("mean_reversion")?);
            let r = rates_d::convexity(p, s, e, v, a)?;
            plain(obj([
                ("futures_rate", r.futures_rate.into()),
                ("convexity", r.convexity.into()),
                ("forward_rate", r.forward_rate.into()),
            ]))
        }
        "rates.csa.discount" => {
            let (c, s) = (curve_input(i, "curve")?, i.f64("collateral_spread")?);
            present(i, "fx")?;
            let fx = match i.opt("fx") {
                None => None,
                Some(_) => {
                    let f = sub(i, "fx")?;
                    Some(CsaFx {
                        spot: f.f64("spot")?,
                        forwards: dated(&f, "forwards", "forward")?,
                    })
                }
            };
            let dates = i.dates("dates")?;
            i.gate()?;
            let d = rates_d::csa_discount(&Curve::new(&c)?, s, fx.as_ref(), &dates)?;
            plain(obj([("discount_factors", d.into())]))
        }
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
        }
        "rates.curve.joint_bootstrap" => {
            let c = overnight(i, "convention")?;
            index(i)?;
            let (t, q) = (i.date("as_of")?, ois_quotes_at(i, "ois_quotes")?);
            let p = projection_quotes_at(i, "term_quotes")?;
            let (m, method) = (interpolation(i)?, solve_method(i)?);
            i.gate()?;
            let (d, p) = rates_d::joint_bootstrap(&c, t, &q, &p, m, method)?;
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
        }
        "calib.curve.smooth" => {
            let (k, m, y) = (
                i.reals("knots")?,
                i.reals("maturities")?,
                i.reals("zero_rates")?,
            );
            let (l, w) = (i.f64("lambda")?, optional_reals(i, "weights")?);
            i.gate()?;
            let s = curve_fits::smooth(&k, &m, &y, l, w.as_deref())?;
            plain(obj([
                ("forwards", s.forwards.into()),
                ("fitted", s.fitted.into()),
                ("objective", s.objective.into()),
            ]))
        }
        "calib.curve.robust" => {
            let (m, y) = (i.reals("maturities")?, i.reals("zero_rates")?);
            let (tau, delta) = (i.f64("tau")?, i.f64("delta")?);
            i.gate()?;
            let r = curve_fits::robust(&m, &y, tau, delta)?;
            let outliers: Vec<Json> = r.outliers.iter().map(|j| (*j as i64).into()).collect();
            plain(obj([
                ("betas", r.betas.to_vec().into()),
                ("residuals", r.residuals.into()),
                ("outliers", outliers.into()),
                ("objective", r.objective.into()),
            ]))
        }
        _ => crate::ops_d2::dispatch(op, i),
    }
}
