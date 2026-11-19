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

/// Compensated running sum of binomial terms in log space, with a running log binomial
/// coefficient, as `var::traffic_light` builds its terms.
struct Terms {
    n: i64,
    lp: f64,
    lq: f64,
    ln_choose: f64,
    sum: f64,
    comp: f64,
    k: i64,
}

impl Terms {
    fn new(n: i64, p: f64) -> Terms {
        Terms {
            n,
            lp: p.ln(),
            lq: (-p).ln_1p(),
            ln_choose: 0.0,
            sum: 0.0,
            comp: 0.0,
            k: -1,
        }
    }

    /// Adds the next term and returns the partial sum `P(X <= k)`.
    fn next_sum(&mut self) -> f64 {
        self.k += 1;
        let k = self.k;
        if k > 0 {
            self.ln_choose += ((self.n - k + 1) as f64).ln() - (k as f64).ln();
        }
        let term = (self.ln_choose + k as f64 * self.lp + (self.n - k) as f64 * self.lq).exp();
        let t = self.sum + term;
        self.comp += if self.sum.abs() >= term.abs() {
            (self.sum - t) + term
        } else {
            (term - t) + self.sum
        };
        self.sum = t;
        self.sum + self.comp
    }
}

/// `P(X <= x)` for `X ~ Binomial(n, p)`, `0 < p < 1`.
pub fn binomial_cdf(n: i64, x: i64, p: f64) -> f64 {
    if x < 0 {
        return 0.0;
    }
    if x >= n {
        return 1.0;
    }
    let mut t = Terms::new(n, p);
    let mut s = 0.0;
    for _ in 0..=x {
        s = t.next_sum();
    }
    s.min(1.0)
}

/// The smallest `k` in `0..=n` with `P(X <= k) >= level`.
pub fn first_at_least(n: i64, p: f64, level: f64) -> i64 {
    let mut t = Terms::new(n, p);
    for k in 0..n {
        if t.next_sum() >= level {
            return k;
        }
    }
    n
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
    let p = 1.0 - t.coverage;
    let amber = first_at_least(observations_n, p, t.amber_from);
    let red = first_at_least(observations_n, p, t.red_from);
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
        cumulative_probability: binomial_cdf(observations_n, x, p),
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
        cumulative_probability_99: binomial_cdf(observations_n, x99, 0.01),
        cumulative_probability_975: binomial_cdf(observations_n, x975, 0.025),
        breach_99: b99,
        breach_975: b975,
        eligible: !(b99 || b975),
    })
}

/// Exception counts of a P&L series against VaR.
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

/// `risk.frtb.backtest.count` (MAR32.5(1)-(2), MAR32.18(1)-(2)): VaR is positive for a loss; a day
/// is an exception when `-pnl` strictly exceeds VaR or either value is missing (`None`).
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
