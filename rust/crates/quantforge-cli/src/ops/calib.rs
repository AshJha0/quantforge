//! `calib.*` operations: read the inputs, call the library, shape the outputs.
use super::rates::overnight;
use super::risk::interpolation;
use super::risk::ois_quotes;
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::calib;
use quantforge_core::calib::FitInputs;
use quantforge_core::curve_fits;
use quantforge_core::error::Result;
use quantforge_core::json::Json;
use quantforge_core::json::obj;
use quantforge_core::risk;

super::registry! {
(op, i)
        "calib.fit" => calib_fit(i),
        "calib.check_bid_ask" => {
            let (f, b, a) = (i.reals("fitted")?, i.reals("bid")?, i.reals("ask")?);
            i.gate()?;
            let rows: Vec<Json> = calib::check_bid_ask(&f, &b, &a)?
                .into_iter()
                .map(|(k, s, d)| {
                    obj([
                        ("index", k.into()),
                        ("side", s.into()),
                        ("distance", d.into()),
                    ])
                })
                .collect();
            plain(obj([("breaches", rows.into())]))
        },
        "calib.curve_report" => {
            let c = overnight(i, "convention")?;
            let (t, q, m) = (i.date("as_of")?, ois_quotes(i)?, interpolation(i)?);
            i.gate()?;
            let r = risk::curve_report(&c, t, &q, m)?;
            let tenors: Vec<String> = q
                .iter()
                .map(|x| format!("{}{}", x.tenor.0, x.tenor.1))
                .collect();
            Ok(Outcome {
                outputs: obj([
                    ("jacobian", r.jacobian.into()),
                    ("condition_number", r.condition_number.into()),
                ]),
                diagnostics: obj([
                    ("inputs", tenors.into()),
                    ("status", "CONVERGED".into()),
                    ("max_repricing_error", r.max_repricing_error.into()),
                    ("tolerance_breaches", Json::Arr(Vec::new())),
                ]),
            })
        },
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
        },
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
}

pub(crate) fn opt_reals(i: &Inputs, k: &str) -> Result<Option<Vec<f64>>> {
    i.opt(k).map(|_| i.reals(k)).transpose()
}

pub(crate) fn calib_fit(i: &Inputs) -> Result<Outcome> {
    let model = match i.str("model")? {
        "LINEAR" => calib::Model::Linear,
        "EXPONENTIAL" => calib::Model::Exponential,
        "NELSON_SIEGEL" => calib::Model::NelsonSiegel,
        "ROSENBROCK" => calib::Model::Rosenbrock,
        _ => return i.fail("model", "unknown model"),
    };
    let method = match i.str("method")? {
        "GAUSS_NEWTON" => calib::Method::GaussNewton,
        "LEVENBERG_MARQUARDT" => calib::Method::LevenbergMarquardt,
        "BFGS" => calib::Method::Bfgs,
        _ => return i.fail("method", "unknown method"),
    };
    let f = FitInputs {
        model,
        x: opt_reals(i, "x")?.unwrap_or_default(),
        y: opt_reals(i, "y")?.unwrap_or_default(),
        start: i.reals("start")?,
        method,
        weights: opt_reals(i, "weights")?,
        regularisation: i.f64_or("regularisation", 0.0)?,
        prior: opt_reals(i, "prior")?,
        lower: opt_reals(i, "lower")?,
        upper: opt_reals(i, "upper")?,
        max_iter: i.int_or("max_iter", 1000)?,
    };
    let report = i.bool_or("report_parameters", true)?;
    i.gate()?;
    let r = calib::fit(&f)?;
    let objective = ("objective", r.objective.into());
    Ok(Outcome {
        outputs: if report {
            obj([("parameters", r.parameters.into()), objective])
        } else {
            obj([objective])
        },
        diagnostics: obj([
            ("iterations", r.iterations.into()),
            ("status", r.status.into()),
            ("residuals", r.residuals.into()),
        ]),
    })
}

/// Optional, but `null` is `E_SCHEMA` (ruling D10).
pub(crate) fn optional_reals(i: &Inputs, k: &str) -> Result<Option<Vec<f64>>> {
    match i.0.get(k) {
        None => Ok(None),
        Some(Json::Null) => i.fail(k, "must not be null"),
        _ => Ok(Some(i.reals(k)?)),
    }
}
