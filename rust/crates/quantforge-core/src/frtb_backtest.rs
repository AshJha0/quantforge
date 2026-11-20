//! FRTB internal models approach: backtesting zones and desk-level exception limits
//! (`frtb-ima-backtest.md`, plan item K-8e, rulings KR-40 to KR-47). A port of
//! `python/quantforge_core/frtb_backtest.py`. The tables are read from
//! `specifications/06-risk/frtb-ima-backtest-tables.json`, embedded at build time.
use crate::error::{QfError, Result, err, finite};
use crate::json::{Json, parse};
use std::sync::OnceLock;

const TABLE_TEXT: &str =
    include_str!("../../../../specifications/06-risk/frtb-ima-backtest-tables.json");

/// The parsed table file.
#[derive(Debug, Clone)]
pub struct Tables {
    pub coverage: f64,
    pub amber_from: f64,
    pub red_from: f64,
    pub table_observations: i64,
    pub multiplier_250: Vec<f64>,
    pub multiplier_red: f64,
    pub desk_limit_99: i64,
    pub desk_limit_975: i64,
    pub max_observations: i64,
}

/// The tables of `frtb-ima-backtest-tables.json`, parsed once.
pub fn tables() -> &'static Tables {
    static T: OnceLock<Tables> = OnceLock::new();
    T.get_or_init(|| {
        let (doc, _) = parse(TABLE_TEXT).expect("embedded FRTB table is valid JSON");
        let num = |k: &str| doc.get(k).and_then(Json::as_f64).expect("table number");
        Tables {
            coverage: num("coverage"),
            amber_from: num("amber_from_cumulative"),
            red_from: num("red_from_cumulative"),
            table_observations: num("table_observations") as i64,
            multiplier_250: doc
                .get("multiplier_250")
                .and_then(Json::as_array)
                .expect("multiplier_250")
                .iter()
                .map(|v| v.as_f64().expect("multiplier"))
                .collect(),
            multiplier_red: num("multiplier_red"),
            desk_limit_99: num("desk_limit_99") as i64,
            desk_limit_975: num("desk_limit_975") as i64,
            max_observations: num("max_observations") as i64,
        }
    })
}

/// KR-237: the binary64 literal nearest 1/100 (not `1 - coverage`, which is 0.010000000000000009).
pub const P_99: f64 = 0.01;
pub const P_975: f64 = 0.025;
const UP: f64 = 4.149515568880993e180; // 2^600
const DOWN: f64 = 2.409919865102884e-181; // 2^-600

/// KR-237: compensated partial sums of the unnormalised weights `w_0 = 1`,
/// `w_(k+1) = w_k ((n - k) p) / ((k + 1) q)`, each with its scale count (a weight above 2^600
/// rescales the weight and the sum by 2^-600). Stops at `n`, or past the mode once the ratio is at
/// most 1/2 and the weight at most 2^-64 of the sum. Only `+ - * /`, so every build gives the same
/// bits. A port of `frtb_backtest.binomial_partial_sums`.
pub fn binomial_partial_sums(n: i64, p: f64) -> Vec<(f64, i64)> {
    binomial_partial_sums_q(n, p, 1.0 - p)
}

/// KR-237 sums with the non-exception probability `q` given (KR-253: the traffic light passes `q = c`).
pub fn binomial_partial_sums_q(n: i64, p: f64, q: f64) -> Vec<(f64, i64)> {
    let mode = ((n + 1) as f64 * p).floor();
    let (mut w, mut s, mut c, mut e) = (1.0f64, 0.0f64, 0.0f64, 0i64);
    let mut out = Vec::new();
    let mut k: i64 = 0;
    loop {
        let t = s + w;
        c += if s.abs() >= w.abs() {
            (s - t) + w
        } else {
            (w - t) + s
        };
        s = t;
        out.push((s + c, e));
        if k == n {
            return out;
        }
        let r = ((n - k) as f64 * p) / ((k + 1) as f64 * q);
        w *= r;
        k += 1;
        if k as f64 > mode && r <= 0.5 && w <= (s + c) * 5.421010862427522e-20 {
            return out;
        }
        if w > UP {
            w *= DOWN;
            s *= DOWN;
            c *= DOWN;
            e += 1;
        }
    }
}

/// `P(X <= x)` from the partial sums of [`binomial_partial_sums`].
pub fn cdf_from(sums: &[(f64, i64)], n: i64, x: i64) -> f64 {
    if x < 0 {
        return 0.0;
    }
    if x >= n || x >= sums.len() as i64 - 1 {
        return 1.0;
    }
    let (sx, ex) = sums[x as usize];
    let (st, et) = sums[sums.len() - 1];
    let mut v = sx / st;
    for _ in 0..(et - ex) {
        v *= DOWN;
    }
    v.min(1.0)
}

/// `P(X <= x)` for `X ~ Binomial(n, p)`, `0 < p < 1` (KR-237).
pub fn binomial_cdf(n: i64, x: i64, p: f64) -> f64 {
    if x < 0 {
        return 0.0;
    }
    if x >= n {
        return 1.0;
    }
    cdf_from(&binomial_partial_sums(n, p), n, x)
}

/// Dekker's exact product `a * b = hi + lo` (Veltkamp split by 2^27 + 1); only `+ - *` (KR-253).
fn two_prod(a: f64, b: f64) -> (f64, f64) {
    let p = a * b;
    let t = 134_217_729.0 * a;
    let ah = t - (t - a);
    let al = a - ah;
    let t = 134_217_729.0 * b;
    let bh = t - (t - b);
    let bl = b - bh;
    (p, ((ah * bh - p) + ah * bl + al * bh) + al * bl)
}

fn dd_mul(a: (f64, f64), b: (f64, f64)) -> (f64, f64) {
    let (p, lo) = two_prod(a.0, b.0);
    let e = lo + (a.0 * b.1 + a.1 * b.0);
    let s = p + e;
    (s, e - (s - p))
}

/// KR-253: `q^n` by right-to-left binary powering in double-double; `q^1` is `q` exactly.
pub fn power(q: f64, n: i64) -> f64 {
    let (mut r, mut b, mut m) = ((1.0, 0.0), (q, 0.0), n);
    while m != 0 {
        if m & 1 != 0 {
            r = dd_mul(r, b);
        }
        m >>= 1;
        if m != 0 {
            b = dd_mul(b, b);
        }
    }
    r.0 + r.1
}

/// KR-253: `P(X <= x)`, `X ~ Binomial(n, 1 - c)`, with `q = c` exact: `x = 0` is `c^n`, otherwise the KR-237
/// sums with `q = c`.
pub fn traffic_light_cdf(n: i64, x: i64, c: f64) -> f64 {
    if x == 0 {
        return power(c, n);
    }
    if x >= n {
        return 1.0;
    }
    cdf_from(&binomial_partial_sums_q(n, 1.0 - c, c), n, x)
}

fn first_from(sums: &[(f64, i64)], n: i64, level: f64) -> i64 {
    (0..=n)
        .find(|&k| cdf_from(sums, n, k) >= level)
        .unwrap_or(n)
}

/// The smallest `k` in `0..=n` with `P(X <= k) >= level` (exists: `P(X <= n) = 1`).
pub fn first_at_least(n: i64, p: f64, level: f64) -> i64 {
    first_from(&binomial_partial_sums(n, p), n, level)
}

fn coded(code: &'static str, field: &str, message: String) -> QfError {
    let mut e = err(code, message);
    e.field = Some(field.to_string());
    e
}

fn observations(n: i64) -> Result<()> {
    let max = tables().max_observations;
    if n > max {
        return Err(coded(
            "E_LIMIT",
            "observations",
            format!("observations is above its limit of {max}"),
        ));
    }
    if n < 1 {
        return Err(coded(
            "E_DOMAIN",
            "observations",
            "observations must be at least 1".to_string(),
        ));
    }
    Ok(())
}

fn count(n: i64, x: i64, field: &str) -> Result<()> {
    if !(0..=n).contains(&x) {
        return Err(coded(
            "E_DOMAIN",
            field,
            format!("{field} must be in [0, observations]"),
        ));
    }
    Ok(())
}

/// The bank-wide zone (MAR32.5, MAR32.9, MAR99.8, MAR99.17).
#[derive(Debug, Clone, PartialEq)]
pub struct Zone {
    pub exceptions: i64,
    pub cumulative_probability: f64,
    pub zone: &'static str,
    pub amber_from: i64,
    pub red_from: i64,
    /// Published for 250 observations only (KR-42).
    pub multiplier: Option<f64>,
}

/// `risk.frtb.backtest.zone`.
pub fn zone(observations_n: i64, actual: i64, hypothetical: i64) -> Result<Zone> {
    observations(observations_n)?;
    count(observations_n, actual, "exceptions_actual")?;
    count(observations_n, hypothetical, "exceptions_hypothetical")?;
    let t = tables();
    let x = actual.max(hypothetical);
    let sums = binomial_partial_sums(observations_n, P_99);
    let amber = first_from(&sums, observations_n, t.amber_from);
    let red = first_from(&sums, observations_n, t.red_from);
    let name = if x >= red {
        "RED"
    } else if x >= amber {
        "AMBER"
    } else {
        "GREEN"
    };
    let multiplier = (observations_n == t.table_observations).then(|| {
        usize::try_from(x)
            .ok()
            .and_then(|i| t.multiplier_250.get(i).copied())
            .unwrap_or(t.multiplier_red)
    });
    Ok(Zone {
        exceptions: x,
        cumulative_probability: cdf_from(&sums, observations_n, x),
        zone: name,
        amber_from: amber,
        red_from: red,
        multiplier,
    })
}

/// Desk eligibility (MAR32.18, MAR32.19).
#[derive(Debug, Clone, PartialEq)]
pub struct Desk {
    pub exceptions_99: i64,
    pub exceptions_975: i64,
    pub cumulative_probability_99: f64,
    pub cumulative_probability_975: f64,
    pub breach_99: bool,
    pub breach_975: bool,
    pub eligible: bool,
}

/// `risk.frtb.backtest.desk`: counts `[99% actual, 99% hypothetical, 97.5% actual, 97.5% hypothetical]`.
pub fn desk(observations_n: i64, counts: [i64; 4]) -> Result<Desk> {
    observations(observations_n)?;
    let fields = [
        "exceptions_99_actual",
        "exceptions_99_hypothetical",
        "exceptions_975_actual",
        "exceptions_975_hypothetical",
    ];
    for (f, x) in fields.iter().zip(counts) {
        count(observations_n, x, f)?;
    }
    let t = tables();
    let x99 = counts[0].max(counts[1]);
    let x975 = counts[2].max(counts[3]);
    let (b99, b975) = (x99 > t.desk_limit_99, x975 > t.desk_limit_975);
    Ok(Desk {
        exceptions_99: x99,
        exceptions_975: x975,
        cumulative_probability_99: binomial_cdf(observations_n, x99, P_99),
        cumulative_probability_975: binomial_cdf(observations_n, x975, P_975),
        breach_99: b99,
        breach_975: b975,
        eligible: !(b99 || b975),
    })
}

/// Exception counts of a P&L series against value at risk.
#[derive(Debug, Clone, PartialEq)]
pub struct Count {
    pub observations: i64,
    pub exceptions_actual: i64,
    pub exceptions_hypothetical: i64,
    pub exceptions: i64,
    pub days_actual: Vec<i64>,
    pub days_hypothetical: Vec<i64>,
}

fn days(var: &[Option<f64>], pnl: &[Option<f64>]) -> Vec<i64> {
    var.iter()
        .zip(pnl)
        .enumerate()
        .filter(|(_, (v, q))| match (v, q) {
            (Some(v), Some(q)) => -q > *v,
            _ => true,
        })
        .map(|(t, _)| t as i64)
        .collect()
}

/// `risk.frtb.backtest.count` (MAR32.5(1)-(2), MAR32.18(1)-(2)): value at risk is positive for a loss; a day
/// is an exception when `-pnl` strictly exceeds it or either value is missing (`None`).
pub fn count_exceptions(
    var: &[Option<f64>],
    actual: &[Option<f64>],
    hypothetical: &[Option<f64>],
) -> Result<Count> {
    finite(
        "var",
        &var.iter().flatten().copied().collect::<Vec<f64>>()[..],
    )?;
    finite(
        "actual",
        &actual.iter().flatten().copied().collect::<Vec<f64>>()[..],
    )?;
    finite(
        "hypothetical",
        &hypothetical.iter().flatten().copied().collect::<Vec<f64>>()[..],
    )?;
    let n = var.len();
    if n == 0 {
        return Err(coded("E_INPUT", "var", "var is empty".to_string()));
    }
    if actual.len() != n {
        return Err(coded(
            "E_INPUT",
            "actual",
            "actual and var differ in length".to_string(),
        ));
    }
    if hypothetical.len() != n {
        return Err(coded(
            "E_INPUT",
            "hypothetical",
            "hypothetical and var differ in length".to_string(),
        ));
    }
    let (a, h) = (days(var, actual), days(var, hypothetical));
    let (na, nh) = (a.len() as i64, h.len() as i64);
    Ok(Count {
        observations: n as i64,
        exceptions_actual: na,
        exceptions_hypothetical: nh,
        exceptions: na.max(nh),
        days_actual: a,
        days_hypothetical: h,
    })
}
