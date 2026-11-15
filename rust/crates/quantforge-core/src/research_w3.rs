//! Stage J wave 3 (rulings J-W3-1 to J-W3-14): the scenario stress engine
//! (`06-risk/scenario-stress.md`), the interpolation backtests (`11-research/interp-backtest.md`)
//! and the drift detectors (`11-research/drift-detectors.md`).
// `!(x > 0.0)` reads as the spec states the domain rule (and is false for NaN, which E1 has already refused).
#![allow(clippy::neg_cmp_op_on_partial_ord)]

use crate::dates::Date;
use crate::error::{Result, fail, finite};
use crate::interp::{self, Method};

fn increasing(x: &[f64]) -> bool {
    x.windows(2).all(|w| w[1] > w[0])
}

fn tenors(t: &[f64], field: &str) -> Result<()> {
    if t.iter().any(|v| !(*v > 0.0)) || !increasing(t) {
        return fail(
            "E_DOMAIN",
            format!("{field} must be positive and strictly increasing"),
        );
    }
    Ok(())
}

/// Correctly rounded sum (Shewchuk partials, the algorithm of Python's `math.fsum`), so the
/// goldens' `fsum` results are matched exactly for finite inputs.
pub fn fsum(v: impl IntoIterator<Item = f64>) -> f64 {
    let mut p: Vec<f64> = Vec::new();
    for mut x in v {
        let mut k = 0;
        for j in 0..p.len() {
            let mut y = p[j];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            let lo = y - (hi - x);
            if lo != 0.0 {
                p[k] = lo;
                k += 1;
            }
            x = hi;
        }
        p.truncate(k);
        p.push(x);
    }
    let Some(mut hi) = p.pop() else { return 0.0 };
    let mut lo = 0.0;
    while let Some(y) = p.pop() {
        let x = hi;
        hi = x + y;
        lo = y - (hi - x);
        if lo != 0.0 {
            break;
        }
    }
    // Half-even correction when the remaining partials push the result past a tie.
    if let Some(&next) = p.last()
        && ((lo < 0.0 && next < 0.0) || (lo > 0.0 && next > 0.0))
    {
        let y = lo * 2.0;
        let x = hi + y;
        if y == x - hi {
            hi = x;
        }
    }
    hi
}

// --- Scenarios (J-W3-2 to J-W3-5) ----------------------------------------------------------

#[derive(Debug, Clone, PartialEq)]
pub struct Shock {
    pub start_yields: Vec<f64>,
    pub end_yields: Vec<f64>,
    pub shift_bp: Vec<f64>,
    pub level_bp: f64,
    pub slope_bp: f64,
}

pub fn historical_shock(
    dates: &[Date],
    tenor: &[f64],
    yields: &[Vec<f64>],
    start: Date,
    end: Date,
) -> Result<Shock> {
    finite("tenors", tenor)?;
    finite("yields", yields)?;
    let n = tenor.len();
    if dates.is_empty()
        || n == 0
        || yields.len() != dates.len()
        || yields.iter().any(|r| r.len() != n)
    {
        return fail("E_INPUT", "need one row per date and one column per tenor");
    }
    if dates.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_DATE_ORDER", "dates must be strictly increasing");
    }
    tenors(tenor, "tenors")?;
    if end <= start {
        return fail("E_DATE_ORDER", "end_date must be after start_date");
    }
    let find = |d: Date, f: &str| match dates.binary_search(&d) {
        Ok(k) => Ok(k),
        Err(_) => fail("E_DOMAIN", format!("{f} is not in dates")),
    };
    let (a, b) = (find(start, "start_date")?, find(end, "end_date")?);
    let (y0, y1) = (yields[a].clone(), yields[b].clone());
    let shift: Vec<f64> = y0.iter().zip(&y1).map(|(p, q)| 100.0 * (q - p)).collect();
    let level = fsum(shift.iter().copied()) / n as f64;
    let slope = shift[n - 1] - shift[0];
    Ok(Shock {
        start_yields: y0,
        end_yields: y1,
        shift_bp: shift,
        level_bp: level,
        slope_bp: slope,
    })
}

fn flat_linear(x: &[f64], y: &[f64], t: f64) -> f64 {
    let l = x.len() - 1;
    if t <= x[0] {
        return y[0];
    }
    if t >= x[l] {
        return y[l];
    }
    let i = x.partition_point(|k| *k <= t) - 1;
    let u = (t - x[i]) / (x[i + 1] - x[i]);
    y[i] + u * (y[i + 1] - y[i])
}

#[derive(Debug, Clone, PartialEq)]
pub struct Replay {
    pub applied_bp: Vec<f64>,
    pub shocked_yields: Vec<f64>,
    pub pnl: Option<f64>,
}

pub fn replay(
    base_tenors: &[f64],
    base_yields: &[f64],
    shock_tenors: &[f64],
    shock_bp: &[f64],
    scale: f64,
    dv01: Option<&[f64]>,
) -> Result<Replay> {
    finite("base_tenors", base_tenors)?;
    finite("base_yields", base_yields)?;
    finite("shock_tenors", shock_tenors)?;
    finite("shock_bp", shock_bp)?;
    finite("scale", &scale)?;
    finite("dv01", &dv01)?;
    if base_tenors.is_empty() || base_yields.len() != base_tenors.len() {
        return fail("E_INPUT", "base_yields must match base_tenors");
    }
    if shock_tenors.is_empty() || shock_bp.len() != shock_tenors.len() {
        return fail("E_INPUT", "shock_bp must match shock_tenors");
    }
    if dv01.is_some_and(|d| d.len() != base_tenors.len()) {
        return fail("E_INPUT", "dv01 must match base_tenors");
    }
    tenors(base_tenors, "base_tenors")?;
    tenors(shock_tenors, "shock_tenors")?;
    let applied: Vec<f64> = base_tenors
        .iter()
        .map(|t| scale * flat_linear(shock_tenors, shock_bp, *t))
        .collect();
    let shocked = base_yields
        .iter()
        .zip(&applied)
        .map(|(y, a)| y + a / 100.0)
        .collect();
    let pnl = dv01.map(|d| -fsum(d.iter().zip(&applied).map(|(d, a)| d * a)));
    Ok(Replay {
        applied_bp: applied,
        shocked_yields: shocked,
        pnl,
    })
}

// --- Interpolation backtests (J-W3-8, J-W3-9) ----------------------------------------------

#[derive(Debug, Clone, PartialEq)]
pub struct Backtest<E> {
    pub errors: E,
    pub max_abs_error: f64,
    pub rmse: f64,
}

fn summary(e: &[f64]) -> (f64, f64) {
    let mx = e.iter().fold(0.0_f64, |m, v| m.max(v.abs()));
    (mx, (fsum(e.iter().map(|v| v * v)) / e.len() as f64).sqrt())
}

fn min_knots(m: Method) -> usize {
    match m {
        Method::CubicNatural | Method::Tension(_) => 3,
        Method::CubicNotAKnot => 4,
        _ => 2,
    }
}

pub fn interp_loo(method: Method, x: &[f64], y: &[f64]) -> Result<Backtest<Vec<f64>>> {
    finite("x", x)?;
    finite("y", y)?;
    let n = x.len();
    if y.len() != n || n < 3 || n - 1 < min_knots(method) {
        return fail(
            "E_INPUT",
            "need equal lengths, n >= 3 and n - 1 at the method's minimum knots",
        );
    }
    if !increasing(x) {
        return fail("E_INPUT", "knots must be strictly increasing");
    }
    let mut errors = Vec::with_capacity(n - 2);
    for i in 1..n - 1 {
        let xs: Vec<f64> = x
            .iter()
            .enumerate()
            .filter(|(j, _)| *j != i)
            .map(|(_, v)| *v)
            .collect();
        let ys: Vec<f64> = y
            .iter()
            .enumerate()
            .filter(|(j, _)| *j != i)
            .map(|(_, v)| *v)
            .collect();
        errors.push(interp::evaluate(method, &xs, &ys, &[x[i]])?.values[0] - y[i]);
    }
    let (max_abs_error, rmse) = summary(&errors);
    Ok(Backtest {
        errors,
        max_abs_error,
        rmse,
    })
}

pub fn surface_holdout(
    method: Method,
    expiries: &[f64],
    strikes: &[f64],
    vols: &[Vec<f64>],
    holdout: &[i64],
) -> Result<Backtest<Vec<Vec<f64>>>> {
    finite("expiries", expiries)?;
    finite("strikes", strikes)?;
    finite("vols", vols)?;
    let m = strikes.len();
    if expiries.is_empty() || vols.len() != expiries.len() || vols.iter().any(|r| r.len() != m) {
        return fail(
            "E_INPUT",
            "vols must have one row per expiry and one column per strike",
        );
    }
    if !increasing(strikes) {
        return fail("E_INPUT", "strikes must be strictly increasing");
    }
    if holdout.is_empty()
        || holdout.iter().any(|h| !(*h > 0 && *h < m as i64 - 1))
        || holdout.windows(2).any(|w| w[1] <= w[0])
    {
        return fail(
            "E_INPUT",
            "holdout must be distinct sorted interior strike indices",
        );
    }
    let held: Vec<usize> = holdout.iter().map(|h| *h as usize).collect();
    let kept: Vec<usize> = (0..m).filter(|j| !held.contains(j)).collect();
    if kept.len() < min_knots(method) {
        return fail("E_INPUT", "too few kept strikes for the method");
    }
    if expiries.iter().any(|t| !(*t > 0.0)) {
        return fail("E_DOMAIN", "expiries must be positive");
    }
    if vols.iter().flatten().any(|v| !(*v > 0.0)) {
        return fail("E_DOMAIN", "vols must be positive");
    }
    let ks: Vec<f64> = kept.iter().map(|j| strikes[*j]).collect();
    let at: Vec<f64> = held.iter().map(|h| strikes[*h]).collect();
    let mut errors = Vec::with_capacity(expiries.len());
    for (t, row) in expiries.iter().zip(vols) {
        let w: Vec<f64> = kept.iter().map(|j| row[*j] * row[*j] * t).collect();
        let fit = interp::evaluate(method, &ks, &w, &at)?.values;
        if fit.iter().any(|v| !(*v > 0.0)) {
            return fail("E_DOMAIN", "interpolated total variance is not positive");
        }
        errors.push(
            fit.iter()
                .zip(&held)
                .map(|(v, h)| (v / t).sqrt() - row[*h])
                .collect::<Vec<_>>(),
        );
    }
    let flat: Vec<f64> = errors.iter().flatten().copied().collect();
    let (max_abs_error, rmse) = summary(&flat);
    Ok(Backtest {
        errors,
        max_abs_error,
        rmse,
    })
}

// --- Drift detectors (J-W3-10 to J-W3-13) ---------------------------------------------------

#[derive(Debug, Clone, PartialEq)]
pub struct Alarms {
    pub alarms: Vec<i64>,
    pub directions: Vec<i64>,
}

/// J-W3-10: tabular two-sided CUSUM on `z = (x - mu0) / sigma`; alarm when a sum exceeds `h`.
pub fn cusum(
    x: &[f64],
    k: f64,
    h: f64,
    mu0: f64,
    sigma: f64,
    reset: bool,
) -> Result<(Alarms, f64, f64)> {
    finite("x", x)?;
    finite("k", &(k, h))?;
    finite("mu0", &(mu0, sigma))?;
    if x.is_empty() {
        return fail("E_INPUT", "x must not be empty");
    }
    if !(k > 0.0) || !(h > 0.0) || !(sigma > 0.0) {
        return fail("E_DOMAIN", "k, h and sigma must be positive");
    }
    let (mut sp, mut sm) = (0.0_f64, 0.0_f64);
    let mut a = Alarms {
        alarms: vec![],
        directions: vec![],
    };
    for (t, v) in x.iter().enumerate() {
        let z = (v - mu0) / sigma;
        sp = 0.0_f64.max(sp + z - k);
        sm = 0.0_f64.max(sm - z - k);
        if sp > h || sm > h {
            a.alarms.push(t as i64);
            a.directions.push(if sp > h { 1 } else { -1 });
            if !reset {
                break;
            }
            sp = 0.0;
            sm = 0.0;
        }
    }
    Ok((a, sp, sm))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Direction {
    Up,
    Down,
    Both,
}

/// J-W3-11 (as corrected): running mean at each step, restart every counter after an alarm.
pub fn page_hinkley(
    x: &[f64],
    delta: f64,
    lambda: f64,
    dir: Direction,
    reset: bool,
) -> Result<Alarms> {
    finite("x", x)?;
    finite("delta", &(delta, lambda))?;
    if x.is_empty() {
        return fail("E_INPUT", "x must not be empty");
    }
    if !(delta >= 0.0) || !(lambda > 0.0) {
        return fail("E_DOMAIN", "delta must be >= 0 and lambda > 0");
    }
    let mut a = Alarms {
        alarms: vec![],
        directions: vec![],
    };
    let (mut n, mut total, mut up, mut up_min, mut dn, mut dn_min) = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0);
    for (t, v) in x.iter().enumerate() {
        n += 1.0;
        total += v;
        let mean = total / n;
        up += v - mean - delta;
        dn += mean - v - delta;
        up_min = f64::min(up_min, up);
        dn_min = f64::min(dn_min, dn);
        let hit_up = dir != Direction::Down && up - up_min > lambda;
        let hit_dn = dir != Direction::Up && dn - dn_min > lambda;
        if hit_up || hit_dn {
            a.alarms.push(t as i64);
            a.directions.push(if hit_up { 1 } else { -1 });
            if !reset {
                break;
            }
            (n, total, up, up_min, dn, dn_min) = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0);
        }
    }
    Ok(a)
}

pub const PSI_FLOOR: f64 = 1e-4;

#[derive(Debug, Clone, PartialEq)]
pub struct Psi {
    pub psi: f64,
    pub reference_shares: Vec<f64>,
    pub test_shares: Vec<f64>,
    pub alarm: bool,
}

/// J-W3-12: bins at the reference's type-1 quantiles, shares floored at `1e-4`, no renormalising.
pub fn psi(reference: &[f64], test: &[f64], bins: i64, threshold: f64) -> Result<Psi> {
    finite("reference", reference)?;
    finite("test", test)?;
    finite("threshold", &threshold)?;
    if bins < 2 {
        return fail("E_INPUT", "bins must be at least 2");
    }
    let b = bins as usize;
    if reference.len() < b || test.len() < b {
        return fail(
            "E_INPUT",
            "reference and test need at least bins values each",
        );
    }
    if !(threshold > 0.0) {
        return fail("E_DOMAIN", "threshold must be positive");
    }
    let mut r = reference.to_vec();
    r.sort_by(f64::total_cmp);
    let n = r.len();
    let edges: Vec<f64> = (1..b).map(|j| r[(j * n).div_ceil(b) - 1]).collect();
    let shares = |s: &[f64]| -> Vec<f64> {
        let mut c = vec![0usize; b];
        for v in s {
            c[edges.partition_point(|e| *e < *v)] += 1;
        }
        c.iter()
            .map(|k| (*k as f64 / s.len() as f64).max(PSI_FLOOR))
            .collect()
    };
    let (rs, ts) = (shares(reference), shares(test));
    let value = fsum(ts.iter().zip(&rs).map(|(a, e)| (a - e) * (a / e).ln()));
    Ok(Psi {
        psi: value,
        reference_shares: rs,
        test_shares: ts,
        alarm: value > threshold,
    })
}

/// `D n m` as an integer: max `|i m - j n|` over the merged order, ties stepped together.
fn ks_d_scaled(a: &[f64], b: &[f64]) -> i128 {
    let (mut xa, mut xb) = (a.to_vec(), b.to_vec());
    xa.sort_by(f64::total_cmp);
    xb.sort_by(f64::total_cmp);
    let (n, m) = (xa.len(), xb.len());
    let (mut i, mut j, mut best) = (0usize, 0usize, 0i128);
    while i < n || j < m {
        let v = f64::min(
            if i < n { xa[i] } else { f64::INFINITY },
            if j < m { xb[j] } else { f64::INFINITY },
        );
        while i < n && xa[i] == v {
            i += 1;
        }
        while j < m && xb[j] == v {
            j += 1;
        }
        best = best.max((i as i128 * m as i128 - j as i128 * n as i128).abs());
    }
    best
}

fn binom_u128(n: u128, k: u128) -> Option<u128> {
    let mut c: u128 = 1;
    for i in 0..k {
        c = c.checked_mul(n - i)? / (i + 1);
    }
    Some(c)
}

/// `P(D' n m >= d)` under the continuous null by counting lattice paths with `|i m - j n| < d`.
/// Counts in 128 bits while `C(n + m, n)` fits (every golden); otherwise the same walk on path
/// probabilities in binary64 (checked fallback; not used by any golden).
fn ks_p(n: usize, m: usize, d: i128) -> f64 {
    if d <= 0 {
        return 1.0;
    }
    let inside = |i: usize, j: usize| (i as i128 * m as i128 - j as i128 * n as i128).abs() < d;
    if let Some(total) = binom_u128((n + m) as u128, n.min(m) as u128) {
        let mut row = vec![0u128; m + 1];
        row[0] = 1;
        for j in 1..=m {
            row[j] = if inside(0, j) { row[j - 1] } else { 0 };
        }
        for i in 1..=n {
            row[0] = if inside(i, 0) { row[0] } else { 0 };
            for j in 1..=m {
                row[j] = if inside(i, j) { row[j] + row[j - 1] } else { 0 };
            }
        }
        return (total - row[m]) as f64 / total as f64;
    }
    ks_p_walk(n, m, d)
}

/// The fallback: probability that a uniform random path reaches `(i, j)` inside the band.
fn ks_p_walk(n: usize, m: usize, d: i128) -> f64 {
    let inside = |i: usize, j: usize| (i as i128 * m as i128 - j as i128 * n as i128).abs() < d;
    let mut row = vec![0.0f64; m + 1];
    row[0] = 1.0;
    for i in 0..=n {
        let mut next = vec![0.0f64; m + 1];
        for j in 0..=m {
            if !inside(i, j) {
                row[j] = 0.0;
                continue;
            }
            let left = (n - i + m - j) as f64;
            if left == 0.0 {
                continue;
            }
            if i < n {
                next[j] += row[j] * (n - i) as f64 / left;
            }
            if j < m {
                row[j + 1] += row[j] * (m - j) as f64 / left;
            }
        }
        if i == n {
            return 1.0 - row[m];
        }
        row = next;
    }
    1.0
}

/// J-W3-13: two-sample KS statistic and exact two-sided p-value.
pub fn ks(a: &[f64], b: &[f64], level: f64) -> Result<(f64, f64, bool)> {
    finite("a", a)?;
    finite("b", b)?;
    finite("level", &level)?;
    if a.is_empty() || b.is_empty() {
        return fail("E_INPUT", "a and b must not be empty");
    }
    if !(level > 0.0 && level < 1.0) {
        return fail("E_DOMAIN", "level must lie in (0, 1)");
    }
    let (n, m) = (a.len(), b.len());
    let d = ks_d_scaled(a, b);
    let p = ks_p(n, m, d);
    Ok((d as f64 / (n as f64 * m as f64), p, p <= level))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cusum_hand_case() {
        let (a, sp, sm) = cusum(&[0.0, 3.0, 3.0], 0.5, 4.0, 0.0, 1.0, true).unwrap();
        assert_eq!(
            (a.alarms, a.directions, sp, sm),
            (vec![2], vec![1], 0.0, 0.0)
        );
    }

    #[test]
    fn page_hinkley_constant_series_never_alarms() {
        let a = page_hinkley(&[1.0; 50], 0.0, 1.0, Direction::Both, true).unwrap();
        assert_eq!(a.alarms, Vec::<i64>::new());
    }

    #[test]
    fn psi_identical_samples_zero() {
        let x: Vec<f64> = (0..100).map(f64::from).collect();
        let p = psi(&x, &x, 10, 0.25).unwrap();
        assert_eq!(p.psi, 0.0);
        assert!(p.reference_shares.iter().all(|s| (*s - 0.1).abs() < 1e-15));
    }

    #[test]
    fn ks_fallback_agrees_with_exact_count() {
        // n = m = 4 separated samples: D = 1, p = 2 / C(8, 4).
        let (d, p, _) = ks(&[1.0, 2.0, 3.0, 4.0], &[5.0, 6.0, 7.0, 8.0], 0.05).unwrap();
        assert_eq!(d, 1.0);
        assert!((p - 2.0 / 70.0).abs() < 1e-15);
        // The probability walk gives the same tail as the 128-bit count.
        for (n, m) in [(4usize, 4usize), (7, 5), (12, 9)] {
            for dd in 1..=(n * m) as i128 {
                let exact = ks_p(n, m, dd);
                let walk = ks_p_walk(n, m, dd);
                assert!((exact - walk).abs() < 1e-13, "{n} {m} {dd}");
            }
        }
    }

    #[test]
    fn replay_flat_outside() {
        let r = replay(
            &[0.5, 1.0, 40.0],
            &[1.0, 1.0, 1.0],
            &[1.0, 10.0],
            &[10.0, 20.0],
            1.0,
            Some(&[1.0, 1.0, 1.0]),
        )
        .unwrap();
        assert_eq!(r.applied_bp, vec![10.0, 10.0, 20.0]);
        assert_eq!(r.pnl, Some(-40.0));
    }
}
