//! Microstructure estimators with planted truth (`specifications/09-microstructure/micro-estimators.md`,
//! stage H H-4b; rulings HR-70, HR-71, HR-74, HR-75 as amended (HR-66)). A port of the Python build's
//! `micro_est.py` (and the Java `MicroEstimators`): each estimator returns its point estimate and a
//! standard error; sums are correctly rounded (`math.fsum`), so an exact fit (HR-74) gives SE 0 or a
//! value at the rounding floor. Error order: a non-finite input (`E_DOMAIN`, F-2), structural
//! `E_INPUT`, then `E_DOMAIN`, then value-dependent `E_INPUT`.
// `!(x > 0.0)` style rules are written as the spec states them; NaN is refused first.
#![allow(clippy::neg_cmp_op_on_partial_ord)]

use crate::error::{QfError, Result, err};
use crate::research_w3::fsum;

/// An estimate and its standard error.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Estimate {
    pub value: f64,
    pub se: f64,
}

/// A regime's impact sample.
#[derive(Debug, Clone, PartialEq)]
pub struct Sample {
    pub x: Vec<f64>,
    pub y: Vec<f64>,
}

pub(crate) fn fail(code: &'static str, message: &str, field: &str) -> QfError {
    let mut e = err(code, message);
    e.field = Some(field.to_string());
    e
}

pub(crate) fn finite(field: &str, v: &[f64]) -> Result<()> {
    if v.iter().all(|a| a.is_finite()) {
        Ok(())
    } else {
        Err(fail("E_DOMAIN", &format!("{field} must be finite"), field))
    }
}

/// OLS through the origin: beta = sum xy / sum x^2, s2 = SSR / (n - 1), SE = sqrt(s2 / sum x^2).
fn ols_origin(x: &[f64], y: &[f64], field: &str) -> Result<Estimate> {
    if x.len() != y.len() || x.len() < 2 {
        return Err(fail(
            "E_INPUT",
            "x and y need equal lengths of at least 2",
            field,
        ));
    }
    let n = x.len();
    let sxx = fsum(x.iter().map(|a| a * a));
    if sxx == 0.0 {
        return Err(fail("E_INPUT", "the sum of x^2 is 0", field));
    }
    let beta = fsum(x.iter().zip(y).map(|(a, b)| a * b)) / sxx;
    let ssr = fsum(x.iter().zip(y).map(|(a, b)| {
        let r = b - beta * a;
        r * r
    }));
    Ok(Estimate {
        value: beta,
        se: (ssr / (n - 1) as f64 / sxx).sqrt(),
    })
}

/// OLS with intercept: the slope and its SE with n - 2 degrees of freedom.
fn ols_slope(t: &[f64], y: &[f64], field: &str) -> Result<Estimate> {
    let n = t.len() as f64;
    let tm = fsum(t.iter().copied()) / n;
    let ym = fsum(y.iter().copied()) / n;
    let stt = fsum(t.iter().map(|a| (a - tm) * (a - tm)));
    if stt == 0.0 {
        return Err(fail("E_INPUT", "all abscissae are equal", field));
    }
    let slope = fsum(t.iter().zip(y).map(|(a, b)| (a - tm) * (b - ym))) / stt;
    let icpt = ym - slope * tm;
    let ssr = fsum(t.iter().zip(y).map(|(a, b)| {
        let r = b - icpt - slope * a;
        r * r
    }));
    Ok(Estimate {
        value: slope,
        se: (ssr / (n - 2.0) / stt).sqrt(),
    })
}

/// `micro.est.arrival_rate`: Poisson MLE lambda = N / T, SE = sqrt(lambda / T).
pub fn arrival_rate(count: i64, window: f64) -> Result<Estimate> {
    finite("window", &[window])?;
    if count < 0 {
        return Err(fail("E_DOMAIN", "count must be non-negative", "count"));
    }
    if !(window > 0.0) {
        return Err(fail("E_DOMAIN", "window must be positive", "window"));
    }
    let lam = count as f64 / window;
    Ok(Estimate {
        value: lam,
        se: (lam / window).sqrt(),
    })
}

/// `micro.est.cancel_rate`: censored exponential MLE theta = C / sum L, SE = theta / sqrt(C).
/// `orders` are (lifetime, cancelled).
pub fn cancel_rate(orders: &[(f64, bool)]) -> Result<Estimate> {
    let life: Vec<f64> = orders.iter().map(|o| o.0).collect();
    let c = orders.iter().filter(|o| o.1).count();
    finite("orders", &life)?;
    if life.iter().any(|l| !(*l > 0.0)) {
        return Err(fail("E_DOMAIN", "lifetimes must be positive", "orders"));
    }
    if c == 0 {
        return Err(fail("E_INPUT", "no cancelled order", "orders"));
    }
    let theta = c as f64 / fsum(life);
    Ok(Estimate {
        value: theta,
        se: theta / (c as f64).sqrt(),
    })
}

/// `micro.est.resilience`: kappa = -slope of ln(S - `S_inf`) on t; `points` are (t, S).
pub fn resilience(s_inf: f64, points: &[(f64, f64)]) -> Result<Estimate> {
    finite("s_inf", &[s_inf])?;
    for p in points {
        finite("points", &[p.0, p.1])?;
    }
    if points.len() < 3 {
        return Err(fail("E_INPUT", "need at least 3 points", "points"));
    }
    if points.iter().any(|p| p.1 <= s_inf) {
        return Err(fail("E_DOMAIN", "every spread must exceed s_inf", "points"));
    }
    let t: Vec<f64> = points.iter().map(|p| p.0).collect();
    let y: Vec<f64> = points.iter().map(|p| (p.1 - s_inf).ln()).collect();
    let e = ols_slope(&t, &y, "points")?;
    Ok(Estimate {
        value: -e.value,
        se: e.se,
    })
}

/// `micro.est.liquidity_decay`: alpha = -slope of ln D on k; `levels` are (k, D).
pub fn liquidity_decay(levels: &[(f64, f64)]) -> Result<Estimate> {
    for p in levels {
        finite("levels", &[p.0, p.1])?;
    }
    if levels.len() < 3 {
        return Err(fail("E_INPUT", "need at least 3 levels", "levels"));
    }
    if levels.iter().any(|p| p.1 <= 0.0) {
        return Err(fail("E_DOMAIN", "every depth must be positive", "levels"));
    }
    let k: Vec<f64> = levels.iter().map(|p| p.0).collect();
    let y: Vec<f64> = levels.iter().map(|p| p.1.ln()).collect();
    let e = ols_slope(&k, &y, "levels")?;
    Ok(Estimate {
        value: -e.value,
        se: e.se,
    })
}

/// `micro.est.adverse_selection`: dm = `lambda_as` s q + e, OLS through the origin.
pub fn adverse_selection(x: &[f64], y: &[f64]) -> Result<Estimate> {
    finite("x", x)?;
    finite("y", y)?;
    ols_origin(x, y, "x")
}

/// `micro.est.regime_impact`: adverse selection per regime label (returned in code-point order)
/// and the ratio stressed / calm.
pub fn regime_impact(regimes: &[(String, Sample)]) -> Result<(Vec<(String, Estimate)>, f64)> {
    let mut sorted: Vec<&(String, Sample)> = regimes.iter().collect();
    // Code-point order, as Python sorts strings: Rust's `str` order on UTF-8 bytes is the same.
    sorted.sort_by(|a, b| a.0.cmp(&b.0));
    sorted.dedup_by(|a, b| a.0 == b.0);
    for (k, s) in &sorted {
        finite(&format!("regimes.{k}"), &s.x)?;
        finite(&format!("regimes.{k}"), &s.y)?;
    }
    for need in ["calm", "stressed"] {
        if !sorted.iter().any(|r| r.0 == need) {
            return Err(fail(
                "E_INPUT",
                &format!("regime '{need}' is missing"),
                "regimes",
            ));
        }
    }
    for (k, s) in &sorted {
        if s.x.len() != s.y.len() || s.x.len() < 2 {
            return Err(fail(
                "E_INPUT",
                "x and y need equal lengths of at least 2",
                &format!("regimes.{k}"),
            ));
        }
    }
    let mut out = Vec::with_capacity(sorted.len());
    for (k, s) in &sorted {
        out.push((k.clone(), ols_origin(&s.x, &s.y, &format!("regimes.{k}"))?));
    }
    let get = |name: &str| out.iter().find(|r| r.0 == name).map_or(0.0, |r| r.1.value);
    let calm = get("calm");
    if calm == 0.0 {
        return Err(fail(
            "E_DOMAIN",
            "calm lambda_as is 0; the ratio is undefined",
            "regimes",
        ));
    }
    let ratio = get("stressed") / calm;
    Ok((out, ratio))
}

fn mean_var(v: &[f64]) -> (f64, f64) {
    let n = v.len() as f64;
    let m = fsum(v.iter().copied()) / n;
    (m, fsum(v.iter().map(|a| (a - m) * (a - m))) / (n - 1.0))
}

/// `micro.est.passive_vs_aggressive`: delta = mean(aggressive) - mean(passive), Welch SE.
pub fn passive_vs_aggressive(passive: &[f64], aggressive: &[f64]) -> Result<Estimate> {
    finite("passive", passive)?;
    finite("aggressive", aggressive)?;
    if passive.len() < 2 {
        return Err(fail(
            "E_INPUT",
            "need at least 2 fills per class",
            "passive",
        ));
    }
    if aggressive.len() < 2 {
        return Err(fail(
            "E_INPUT",
            "need at least 2 fills per class",
            "aggressive",
        ));
    }
    let (pm, pv) = mean_var(passive);
    let (am, av) = mean_var(aggressive);
    Ok(Estimate {
        value: am - pm,
        se: (av / aggressive.len() as f64 + pv / passive.len() as f64).sqrt(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn code(r: Result<impl std::fmt::Debug>) -> (&'static str, String) {
        let e = r.unwrap_err();
        (e.code, e.field.unwrap_or_default())
    }

    #[test]
    fn arrival_rate_values_and_errors() {
        let e = arrival_rate(50, 10.0).unwrap();
        assert_eq!((e.value, e.se), (5.0, 0.5_f64.sqrt()));
        assert_eq!(
            code(arrival_rate(1, f64::NAN)),
            ("E_DOMAIN", "window".into())
        );
        assert_eq!(code(arrival_rate(-1, 1.0)), ("E_DOMAIN", "count".into()));
        assert_eq!(code(arrival_rate(1, 0.0)), ("E_DOMAIN", "window".into()));
    }

    #[test]
    fn cancel_rate_values_and_errors() {
        let e = cancel_rate(&[(1.0, true), (3.0, false), (4.0, true)]).unwrap();
        assert_eq!(e.value, 0.25);
        assert_eq!(e.se, 0.25 / 2.0_f64.sqrt());
        assert_eq!(
            code(cancel_rate(&[(f64::INFINITY, true)])),
            ("E_DOMAIN", "orders".into())
        );
        assert_eq!(
            code(cancel_rate(&[(0.0, true)])),
            ("E_DOMAIN", "orders".into())
        );
        assert_eq!(
            code(cancel_rate(&[(1.0, false)])),
            ("E_INPUT", "orders".into())
        );
    }

    #[test]
    fn resilience_exact_fit_and_errors() {
        // S - 1 = e^{-2t}: kappa 2, exact fit.
        let pts: Vec<(f64, f64)> = (0..4)
            .map(|t| (f64::from(t), 1.0 + (-2.0 * f64::from(t)).exp()))
            .collect();
        let e = resilience(1.0, &pts).unwrap();
        assert!((e.value - 2.0).abs() < 1e-12 && e.se < 1e-7);
        assert_eq!(
            code(resilience(f64::NAN, &pts)),
            ("E_DOMAIN", "s_inf".into())
        );
        assert_eq!(
            code(resilience(1.0, &[(0.0, f64::NAN)])),
            ("E_DOMAIN", "points".into())
        );
        assert_eq!(
            code(resilience(1.0, &pts[..2])),
            ("E_INPUT", "points".into())
        );
        assert_eq!(code(resilience(5.0, &pts)), ("E_DOMAIN", "points".into()));
        let same_t = [(1.0, 2.0), (1.0, 3.0), (1.0, 4.0)];
        assert_eq!(code(resilience(1.0, &same_t)), ("E_INPUT", "points".into()));
    }

    #[test]
    fn liquidity_decay_values_and_errors() {
        let lv: Vec<(f64, f64)> = (0..5)
            .map(|k| (f64::from(k), 100.0 * (-0.5 * f64::from(k)).exp()))
            .collect();
        let e = liquidity_decay(&lv).unwrap();
        assert!((e.value - 0.5).abs() < 1e-12);
        assert_eq!(
            code(liquidity_decay(&[(0.0, f64::INFINITY)])),
            ("E_DOMAIN", "levels".into())
        );
        assert_eq!(
            code(liquidity_decay(&lv[..2])),
            ("E_INPUT", "levels".into())
        );
        assert_eq!(
            code(liquidity_decay(&[(0.0, 1.0), (1.0, 0.0), (2.0, 1.0)])),
            ("E_DOMAIN", "levels".into())
        );
        assert_eq!(
            code(liquidity_decay(&[(2.0, 1.0), (2.0, 2.0), (2.0, 3.0)])),
            ("E_INPUT", "levels".into())
        );
    }

    #[test]
    fn adverse_selection_values_and_errors() {
        let e = adverse_selection(&[1.0, 2.0, 3.0], &[2.0, 4.0, 6.0]).unwrap();
        assert_eq!((e.value, e.se), (2.0, 0.0));
        assert_eq!(
            code(adverse_selection(&[f64::NAN], &[1.0])),
            ("E_DOMAIN", "x".into())
        );
        assert_eq!(
            code(adverse_selection(&[1.0], &[f64::NAN])),
            ("E_DOMAIN", "y".into())
        );
        assert_eq!(
            code(adverse_selection(&[1.0, 2.0], &[1.0])),
            ("E_INPUT", "x".into())
        );
        assert_eq!(
            code(adverse_selection(&[0.0, 0.0], &[1.0, 2.0])),
            ("E_INPUT", "x".into())
        );
    }

    fn reg(name: &str, x: &[f64], y: &[f64]) -> (String, Sample) {
        (
            name.into(),
            Sample {
                x: x.to_vec(),
                y: y.to_vec(),
            },
        )
    }

    #[test]
    fn regime_impact_values_and_errors() {
        let calm = reg("calm", &[1.0, 2.0], &[1.0, 2.0]);
        let stressed = reg("stressed", &[1.0, 2.0], &[3.0, 6.0]);
        let (out, ratio) = regime_impact(&[stressed.clone(), calm.clone()]).unwrap();
        assert_eq!(
            out.iter().map(|r| r.0.as_str()).collect::<Vec<_>>(),
            ["calm", "stressed"]
        );
        assert_eq!(ratio, 3.0);
        let bad = reg("calm", &[f64::NAN, 1.0], &[1.0, 1.0]);
        assert_eq!(code(regime_impact(&[bad, stressed.clone()])).0, "E_DOMAIN");
        assert_eq!(
            code(regime_impact(std::slice::from_ref(&calm))),
            ("E_INPUT", "regimes".into())
        );
        let short = reg("stressed", &[1.0], &[1.0]);
        assert_eq!(
            code(regime_impact(&[calm.clone(), short])),
            ("E_INPUT", "regimes.stressed".into())
        );
        let zero = reg("calm", &[1.0, 2.0], &[0.0, 0.0]);
        assert_eq!(
            code(regime_impact(&[zero, stressed])),
            ("E_DOMAIN", "regimes".into())
        );
    }

    #[test]
    fn passive_vs_aggressive_values_and_errors() {
        let e = passive_vs_aggressive(&[1.0, 3.0], &[4.0, 6.0]).unwrap();
        assert_eq!((e.value, e.se), (3.0, 2.0_f64.sqrt())); // var 2 in each class: sqrt(2/2 + 2/2)
        assert_eq!(
            code(passive_vs_aggressive(&[f64::NAN, 1.0], &[1.0, 2.0])),
            ("E_DOMAIN", "passive".into())
        );
        assert_eq!(
            code(passive_vs_aggressive(&[1.0, 2.0], &[f64::NAN, 1.0])),
            ("E_DOMAIN", "aggressive".into())
        );
        assert_eq!(
            code(passive_vs_aggressive(&[1.0], &[1.0, 2.0])),
            ("E_INPUT", "passive".into())
        );
        assert_eq!(
            code(passive_vs_aggressive(&[1.0, 2.0], &[1.0])),
            ("E_INPUT", "aggressive".into())
        );
    }
}
