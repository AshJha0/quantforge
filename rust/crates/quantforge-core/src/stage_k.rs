//! Stage K wave 1 (PROPOSED rulings KR-1 to KR-14, `specifications/stage-k-rulings-w1.md`): the
//! bitemporal store query, the sequential par bootstrap and its incremental update, recalibration
//! triggers, intraday delta-gamma risk with a Lagrange bound, and the Richardson guard. A port of the
//! Python build's `stage_k.py` (second reference: the Java `StageK`).
//!
//! Specifications: `01-core/bitemporal-store.md`, `02-curves/incremental-update.md`,
//! `03-calibration/recalibration-triggers.md`, `06-risk/intraday-risk-bounds.md`,
//! `06-risk/bermudan-ladder-k8.md` (`num.richardson.check`).
//!
//! Error order (HR-122, ruling KR-230): `E_LIMIT` for the input sizes (the command-line gate; here
//! the first check of each function, so a library call keeps the command-line order), the F-2
//! finite rule, structural `E_INPUT` (lengths, empty lists, log order), `E_DOMAIN`, then the
//! stale-cache `E_INPUT` of the incremental update.
// `!(x > 0.0)` style rules are written as the spec states them; NaN is refused first.
#![allow(clippy::neg_cmp_op_on_partial_ord)]

use crate::error::{QfError, Result, err};
use crate::json::Json;
use crate::research_w3::fsum;
use crate::stats::normal_cdf;

/// KR-10: the label on intraday outputs computed on simulated data.
pub const LABEL: &str = "latency-aware analytics on simulated data";
/// The generic array cap of `limits.md` (KR-231 supersedes 1,000,000).
pub const MAX_RECORDS: usize = 100_000;
/// The `limits.md` row of the stage K quote lists (KR-231).
pub const MAX_QUOTES: usize = 200;
pub const MAX_CHANGES: usize = 100_000;
pub const MAX_POSITIONS: usize = 100_000;

fn fail(code: &'static str, message: &str, field: &str) -> QfError {
    let mut e = err(code, message);
    e.field = Some(field.to_string());
    e
}

fn input(message: &str, field: &str) -> QfError {
    fail("E_INPUT", message, field)
}

fn domain(message: &str, field: &str) -> QfError {
    fail("E_DOMAIN", message, field)
}

fn limit(field: &str, max: usize) -> QfError {
    fail(
        "E_LIMIT",
        &format!("{field} is above its limit of {max}"),
        field,
    )
}

/// F-2: every Real input is finite.
fn finite(field: &str, v: impl IntoIterator<Item = f64>) -> Result<()> {
    if v.into_iter().all(f64::is_finite) {
        Ok(())
    } else {
        Err(domain(&format!("{field} must be finite"), field))
    }
}

// --- bitemporal store (KR-2, KR-3, KR-14) ----------------------------------------------------------

/// One bitemporal record; instants are whole seconds since the epoch, `valid_to` `None` is open.
#[derive(Debug, Clone, PartialEq)]
pub struct BiRecord {
    pub sequence: i64,
    pub series_id: String,
    pub valid_from: i64,
    pub valid_to: Option<i64>,
    pub knowledge_time: i64,
    pub value: Json,
    pub deleted: bool,
}

/// The answer of a query: `FOUND` with its row, `WITHDRAWN` (a deleted winner) or `NONE`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BiStatus {
    Found,
    Withdrawn,
    None,
}

impl BiStatus {
    pub fn name(self) -> &'static str {
        match self {
            BiStatus::Found => "FOUND",
            BiStatus::Withdrawn => "WITHDRAWN",
            BiStatus::None => "NONE",
        }
    }
}

/// Log checks 2 to 4 (structural `E_INPUT`), in the spec's order.
pub fn check_log(records: &[BiRecord]) -> Result<()> {
    if records.windows(2).any(|w| w[1].sequence <= w[0].sequence) {
        return Err(input("sequence must be strictly increasing", "records"));
    }
    if records
        .windows(2)
        .any(|w| w[1].knowledge_time < w[0].knowledge_time)
    {
        return Err(input("knowledge_time went backwards", "records"));
    }
    if records
        .iter()
        .any(|r| r.valid_to.is_some_and(|t| t <= r.valid_from))
    {
        return Err(input("valid_to must be after valid_from", "records"));
    }
    Ok(())
}

/// `core.store.bitemporal_query`: the record with the highest sequence among those known by `K`
/// (inclusive) whose valid interval holds `V`. A deleted winner is `WITHDRAWN`: it masks older
/// records, never a fall-back.
pub fn bitemporal_query<'a>(
    records: &'a [BiRecord],
    series_id: &str,
    knowledge_as_of: i64,
    valid_at: i64,
) -> Result<(BiStatus, Option<&'a BiRecord>)> {
    query_within(records, series_id, knowledge_as_of, valid_at, MAX_RECORDS)
}

fn query_within<'a>(
    records: &'a [BiRecord],
    series_id: &str,
    knowledge_as_of: i64,
    valid_at: i64,
    max: usize,
) -> Result<(BiStatus, Option<&'a BiRecord>)> {
    if records.len() > max {
        return Err(limit("records", max));
    }
    if records.iter().any(|r| r.value.has_non_finite()) {
        return Err(domain("a record value is NaN or infinite", "records"));
    }
    check_log(records)?;
    let mut best: Option<&BiRecord> = None;
    for r in records {
        if r.series_id == series_id
            && r.knowledge_time <= knowledge_as_of
            && r.valid_from <= valid_at
            && r.valid_to.is_none_or(|t| valid_at < t)
            && best.is_none_or(|b| r.sequence > b.sequence)
        {
            best = Some(r);
        }
    }
    Ok(match best {
        None => (BiStatus::None, None),
        Some(r) if r.deleted => (BiStatus::Withdrawn, None),
        Some(r) => (BiStatus::Found, Some(r)),
    })
}

// --- par bootstrap and incremental update (KR-5) ---------------------------------------------------

/// Continues `P_k = (1 - S_k sum_(i<k) P_i) / (1 + S_k)` after the pillars in `head`. The running
/// sum is accumulated left to right, so a continuation is bit-identical to a full build.
fn bootstrap_from(quotes: &[f64], head: &[f64]) -> Vec<f64> {
    let mut out = head.to_vec();
    let mut acc = 0.0;
    for p in &out {
        acc += p;
    }
    for &s in &quotes[head.len()..] {
        let p = (1.0 - s * acc) / (1.0 + s);
        out.push(p);
        acc += p;
    }
    out
}

fn check_quotes(quotes: &[f64], field: &str) -> Result<()> {
    if quotes.iter().any(|s| !(*s > -1.0)) {
        return Err(domain("every quote must be above -1", field));
    }
    Ok(())
}

/// `curve.bootstrap.par_annual`: discount factors of annual par swaps with accrual 1.
pub fn par_annual(quotes: &[f64]) -> Result<Vec<f64>> {
    if quotes.len() > MAX_QUOTES {
        return Err(limit("quotes", MAX_QUOTES));
    }
    finite("quotes", quotes.iter().copied())?;
    if quotes.is_empty() {
        return Err(input("quotes must hold at least one quote", "quotes"));
    }
    check_quotes(quotes, "quotes")?;
    Ok(bootstrap_from(quotes, &[]))
}

/// The result of an incremental update.
#[derive(Debug, Clone, PartialEq)]
pub struct Update {
    pub discount_factors: Vec<f64>,
    pub first_changed_index: Option<usize>,
    pub recomputed: usize,
}

/// `curve.incremental.update`: copies the pillars before the first changed quote and solves the
/// rest. The cache must equal the bootstrap of `previous_quotes` bit for bit (`E_INPUT` otherwise;
/// the sign of zero counts).
pub fn incremental_update(
    previous_quotes: &[f64],
    previous_dfs: &[f64],
    new_quotes: &[f64],
) -> Result<Update> {
    for (field, xs) in [
        ("previous_quotes", previous_quotes),
        ("previous_discount_factors", previous_dfs),
        ("new_quotes", new_quotes),
    ] {
        if xs.len() > MAX_QUOTES {
            return Err(limit(field, MAX_QUOTES));
        }
    }
    finite("previous_quotes", previous_quotes.iter().copied())?;
    finite("previous_discount_factors", previous_dfs.iter().copied())?;
    finite("new_quotes", new_quotes.iter().copied())?;
    let n = previous_quotes.len();
    if n < 1 || previous_dfs.len() != n || new_quotes.len() != n {
        return Err(input(
            "previous_quotes, previous_discount_factors and new_quotes must have one equal, non-zero length",
            "new_quotes",
        ));
    }
    check_quotes(previous_quotes, "previous_quotes")?;
    check_quotes(new_quotes, "new_quotes")?;
    let fresh = bootstrap_from(previous_quotes, &[]);
    if fresh
        .iter()
        .zip(previous_dfs)
        .any(|(a, b)| a.to_bits() != b.to_bits())
    {
        return Err(input(
            "previous_discount_factors is not the bootstrap of previous_quotes",
            "previous_discount_factors",
        ));
    }
    let Some(j) = previous_quotes
        .iter()
        .zip(new_quotes)
        .position(|(a, b)| a != b)
    else {
        return Ok(Update {
            discount_factors: previous_dfs.to_vec(),
            first_changed_index: None,
            recomputed: 0,
        });
    };
    Ok(Update {
        discount_factors: bootstrap_from(new_quotes, &previous_dfs[..j]),
        first_changed_index: Some(j),
        recomputed: n - j,
    })
}

// --- recalibration trigger (KR-6, KR-13) -----------------------------------------------------------

/// The result of a trigger check.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Trigger {
    pub fire: bool,
    pub sigma: f64,
    pub threshold: f64,
    /// KR-232: `P(|T_(n-1)| > k)`, the rate on noise with sigma estimated from the window.
    pub false_alarm_rate: f64,
    /// KR-232: the known-sigma rate `2 Phi(-k)` of KR-6.
    pub nominal_rate: f64,
}

/// Sample standard deviation (divisor n - 1) with exactly rounded sums for the mean and the
/// squared deviations, as Python's `math.fsum`.
fn sample_sd(xs: &[f64]) -> f64 {
    let n = xs.len() as f64;
    let mean = fsum(xs.iter().copied()) / n;
    (fsum(xs.iter().map(|x| (x - mean) * (x - mean))) / (n - 1.0)).sqrt()
}

/// `calib.trigger.check`: fires iff `|x_now - x_ref| > k sigma sqrt(d)`, strictly.
pub fn trigger_check(
    changes: &[f64],
    x_ref: f64,
    x_now: f64,
    days_since: f64,
    k: f64,
) -> Result<Trigger> {
    trigger_within(changes, x_ref, x_now, days_since, k, MAX_CHANGES)
}

fn trigger_within(
    changes: &[f64],
    x_ref: f64,
    x_now: f64,
    days_since: f64,
    k: f64,
    max: usize,
) -> Result<Trigger> {
    if changes.len() > max {
        return Err(limit("changes", max));
    }
    finite("changes", changes.iter().copied())?;
    finite(
        "x_ref, x_now, days_since and k",
        [x_ref, x_now, days_since, k],
    )?;
    if changes.len() < 2 {
        return Err(input(
            "changes must hold at least two one-day changes",
            "changes",
        ));
    }
    if !(k > 0.0) {
        return Err(domain("k must be above 0", "k"));
    }
    if !(days_since >= 1.0) {
        return Err(domain("days_since must be at least 1", "days_since"));
    }
    let sigma = sample_sd(changes);
    let top = changes.iter().fold(0.0f64, |m, c| m.max(c.abs()));
    if sigma <= NOISE_FLOOR * top {
        return Err(domain(
            "the changes have no noise scale (sigma at or below 2^-26 max|c|)",
            "changes",
        ));
    }
    let threshold = k * sigma * days_since.sqrt();
    Ok(Trigger {
        fire: (x_now - x_ref).abs() > threshold,
        sigma,
        threshold,
        false_alarm_rate: student_t_two_sided_tail(changes.len() as i64 - 1, k),
        // 2 (1 - Phi(k)) of KR-6, as 2 Phi(-k): the normal CDF forms the Gaussian factor from k itself,
        // so it keeps full precision in the far tail (a bare erfc(k / sqrt 2) loses 1.2e-13 at k = 30).
        nominal_rate: 2.0 * normal_cdf(-k),
    })
}

/// KR-233: sigma at or below `2^-26 max|c_i|` is no noise scale.
pub const NOISE_FLOOR: f64 = 1.4901161193847656e-8; // 2^-26

const TWO_OVER_PI: f64 = 0.6366197723675814;
const T_UP: f64 = 3.273390607896142e150; // 2^500
const T_DOWN: f64 = 3.054936363499605e-151; // 2^-500
const T_STOP: f64 = 8.673617379884035e-19; // 2^-60

fn t_step(t: f64, j: i64, c2: f64, odd: bool) -> f64 {
    if odd {
        (t * ((2 * j + 2) as f64 * c2)) / (2 * j + 3) as f64
    } else {
        (t * ((2 * j + 1) as f64 * c2)) / (2 * j + 2) as f64
    }
}

/// `P(|T_nu| > k)` for an integer `nu >= 1` and `k > 0`, by the stated algorithm of KR-232: the
/// closed-form finite sum of the t distribution where the tail is at least 1/8, else its remainder
/// series (positive terms, no cancellation). Only `+ - * /`, `sqrt` and one `atan2` (odd `nu`), so
/// the four builds agree to the last bit except through `atan2`. A port of Python's
/// `stage_k.student_t_two_sided_tail`.
pub fn student_t_two_sided_tail(nu: i64, k: f64) -> f64 {
    let rn = (nu as f64).sqrt();
    let (s, c, c2);
    if k <= rn {
        let den = nu as f64 + k * k;
        c2 = nu as f64 / den;
        let root = den.sqrt();
        s = k / root;
        c = rn / root;
    } else {
        let r = rn / k;
        let w = (1.0 + r * r).sqrt();
        s = 1.0 / w;
        c = r / w;
        c2 = c * c;
    }
    let odd = nu % 2 == 1;
    let m = if odd { (nu - 1) / 2 } else { nu / 2 };
    let (mut t, mut total, mut e) = (1.0f64, 0.0f64, 0u32);
    for j in 0..m {
        if e == 0 {
            total += t;
        }
        t = t_step(t, j, c2, odd);
        if 0.0 < t && t < T_DOWN {
            t *= T_UP;
            e += 1;
        }
    }
    let a = if odd {
        TWO_OVER_PI * (c.atan2(s) - s * c * total)
    } else {
        1.0 - s * total
    };
    if a >= 0.125 {
        return a;
    }
    let (mut rem, mut j) = (0.0f64, m);
    loop {
        rem += t;
        t = t_step(t, j, c2, odd);
        j += 1;
        if t <= rem * T_STOP {
            break;
        }
        if t < T_DOWN {
            t *= T_UP;
            rem *= T_UP;
            e += 1;
        }
    }
    let mut out = if odd {
        TWO_OVER_PI * s * c * rem
    } else {
        s * rem
    };
    for _ in 0..e {
        out *= T_DOWN;
    }
    out
}

// --- intraday delta-gamma with a Lagrange bound (KR-7, KR-10, KR-12) -------------------------------

/// A zero-coupon position: value `N exp(-y T)`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ZeroPosition {
    pub notional: f64,
    pub maturity: f64,
    pub yield_: f64,
}

/// The Lagrange bound `|h|^3 M3 / 6` with `M3 = T^3 |N| exp(-T min(y, y + h))` (KR-15), in the
/// order of KR-234.
pub fn position_bound(p: &ZeroPosition, shift: f64) -> f64 {
    let (t, ah) = (p.maturity, shift.abs());
    let e = (-t * p.yield_.min(p.yield_ + shift)).exp();
    ah * ah * ah * (t * t * t * p.notional.abs() * e) / 6.0
}

/// KR-234: `16 u`.
pub const ROUNDING_FACTOR: f64 = 1.7763568394002505e-15; // 2^-49

/// The rounding allowance `rho` of KR-234: covers the binary64 error of the estimate, of the
/// computed Lagrange bound and of the binary64 revaluation of the position.
pub fn position_rounding(p: &ZeroPosition, shift: f64) -> f64 {
    let (t, ah) = (p.maturity, shift.abs());
    let v = p.notional * (-p.yield_ * t).exp();
    let g = (-shift * t).exp_m1().abs();
    let scale = 1.0 + t * p.yield_.abs() + t * ah;
    ROUNDING_FACTOR
        * scale
        * (v.abs() * (t * ah + t * t * (shift * shift) + g) + position_bound(p, shift))
}

/// `V' h + V'' h^2 / 2` with `V = N exp(-y T)`, as `v * (-T h + T T h h / 2)` (KR-234).
pub fn position_estimate(p: &ZeroPosition, shift: f64) -> f64 {
    let t = p.maturity;
    let v = p.notional * (-p.yield_ * t).exp();
    v * (-t * shift + t * t * shift * shift / 2.0)
}

/// The delta-gamma estimate and the remainder bound of a book.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Intraday {
    pub estimate_pnl: f64,
    pub bound: f64,
}

/// `risk.intraday.delta_gamma_bound`: the delta-gamma P&L of a parallel yield move and a bound on
/// its distance from the full revaluation: the per-position Lagrange bounds (no netting: their
/// signs are unknown in general) plus the binary64 rounding allowance (KR-234), one exactly
/// rounded sum.
pub fn delta_gamma_bound(positions: &[ZeroPosition], shift: f64) -> Result<Intraday> {
    intraday_within(positions, shift, MAX_POSITIONS)
}

fn intraday_within(positions: &[ZeroPosition], shift: f64, max: usize) -> Result<Intraday> {
    if positions.len() > max {
        return Err(limit("positions", max));
    }
    finite(
        "positions",
        positions
            .iter()
            .flat_map(|p| [p.notional, p.maturity, p.yield_]),
    )?;
    finite("shift", [shift])?;
    if positions.is_empty() {
        return Err(input("positions must not be empty", "positions"));
    }
    if positions.iter().any(|p| !(p.maturity > 0.0)) {
        return Err(domain(
            "every maturity must be above 0",
            "positions.maturity",
        ));
    }
    Ok(Intraday {
        estimate_pnl: fsum(positions.iter().map(|p| position_estimate(p, shift))),
        bound: fsum(
            positions
                .iter()
                .map(|p| position_bound(p, shift))
                .chain(positions.iter().map(|p| position_rounding(p, shift))),
        ),
    })
}

/// Full revaluation `sum N (exp(-(y + h) T) - exp(-y T))`; a test helper, not an operation.
pub fn zero_revalue(positions: &[ZeroPosition], shift: f64) -> f64 {
    fsum(
        positions
            .iter()
            .map(|p| p.notional * (-p.yield_ * p.maturity).exp() * (-shift * p.maturity).exp_m1()),
    )
}

// --- Richardson guard (KR-9, KR-12) ----------------------------------------------------------------

/// The Richardson verdict: `OK`, `ORDER_MISMATCH` or `NON_MONOTONE`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Richardson {
    pub status: &'static str,
    pub observed_order: Option<f64>,
    pub extrapolated: Option<f64>,
}

/// `num.richardson.check`: extrapolates only when the differences keep one sign and the observed
/// order is within 0.5 of the assumed order.
pub fn richardson_check(values: &[f64], ratio: f64, assumed_order: f64) -> Result<Richardson> {
    finite(
        "values, ratio and assumed_order",
        values.iter().copied().chain([ratio, assumed_order]),
    )?;
    let &[f1, f2, f3] = values else {
        return Err(input(
            "values must hold exactly three grid values",
            "values",
        ));
    };
    if !(ratio > 1.0) {
        return Err(domain("ratio must be above 1", "ratio"));
    }
    if !(assumed_order > 0.0) {
        return Err(domain("assumed_order must be above 0", "assumed_order"));
    }
    let (d1, d2) = (f1 - f2, f2 - f3);
    if d1 == 0.0 || d2 == 0.0 || (d1 > 0.0) != (d2 > 0.0) {
        return Ok(Richardson {
            status: "NON_MONOTONE",
            observed_order: None,
            extrapolated: None,
        });
    }
    let observed = (d1 / d2).ln() / ratio.ln();
    if !((observed - assumed_order).abs() <= 0.5) {
        return Ok(Richardson {
            status: "ORDER_MISMATCH",
            observed_order: Some(observed),
            extrapolated: None,
        });
    }
    let rp = ratio.powf(assumed_order);
    Ok(Richardson {
        status: "OK",
        observed_order: Some(observed),
        extrapolated: Some((rp * f3 - f2) / (rp - 1.0)),
    })
}

#[cfg(test)]
#[path = "stage_k_tests.rs"]
mod tests;

#[cfg(test)]
#[path = "stage_k_incremental_b_tests.rs"]
mod incremental_b_tests;
