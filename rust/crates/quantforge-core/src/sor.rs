//! `exec.sor.allocate`: order placement over simulated lit and dark venues ([CK] Cont-Kukanov).
//!
//! Spec: `specifications/10-execution/smart-order-router.md` (rulings HR-37 to HR-40). Simulated
//! venues; router scored in simulation only.
//!
//! Cost per scenario is [CK] eq. 5 with the dark extension of HR-37:
//! `(h + f) M - sum_k (h + r_k - as_k) fill_k + theta (M + sum_k L_k + (S - A)_+)`
//! `+ lambda_u (S - A)_+ + lambda_o (A - S)_+`,
//! LIT fill = `(xi - Q)_+ - (xi - Q - L)_+`, DARK fill = `min(L, s)`, `A = M + sum fills`. The
//! expectation is exact: equally weighted `lit_samples` rows times the independent dark
//! distributions given by their tails, in rational arithmetic ([`Q`], 128-bit; a value that does
//! not fit is `E_LIMIT`), rounded half-even to 6 decimals only on output.
//!
//! Methods: `SAMPLE_AVERAGE` (HR-39; exhaustive integer search over 0..S per coordinate, HR-38,
//! ties to the lexicographically smallest `(M, L_1, ..., L_K)`; coordinate descent from the [CK]
//! Prop. 3 start when the grid exceeds 10^6 points), `CLOSED_FORM` ([CK] Prop. 3, one lit venue,
//! empirical left-inverse quantile), `STOCHASTIC_APPROX` ([CK] section 4 projected subgradient
//! with averaged iterates, rounded to the best neighbouring integer point, then polished by exact
//! coordinate descent as in the Python build).
use crate::decimal::Dec;
use crate::error::{QfError, Result, err};
use crate::json::Json;
use crate::order_book::dec;
use crate::rng::Xoshiro;
use std::cmp::Ordering;

pub const LABEL: &str = "simulated venues; router scored in simulation only";
pub const MAX_VENUES: usize = 64;
pub const MAX_SAMPLES: usize = 1_000_000;
pub const MAX_GRID: u128 = 1_000_000;

fn at(code: &'static str, path: &str, what: &str) -> QfError {
    let mut e = err(code, format!("{path}: {what}"));
    e.field = Some(path.to_string());
    e
}

fn range() -> QfError {
    err(
        "E_LIMIT",
        "rational value outside the 128-bit exact range (HR-58)",
    )
}

fn gcd(mut a: i128, mut b: i128) -> i128 {
    a = a.abs();
    b = b.abs();
    while b != 0 {
        (a, b) = (b, a % b);
    }
    a
}

/// An exact rational `n / d`, `d > 0`, in lowest terms.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Q {
    n: i128,
    d: i128,
}

impl Q {
    pub const ZERO: Q = Q { n: 0, d: 1 };
    pub const ONE: Q = Q { n: 1, d: 1 };

    pub fn new(n: i128, d: i128) -> Result<Q> {
        if d == 0 {
            return Err(err("E_DOMAIN", "division by zero"));
        }
        let g = gcd(n, d);
        let (mut n, mut d) = (n / g.max(1), d / g.max(1));
        if d < 0 {
            n = n.checked_neg().ok_or_else(range)?;
            d = d.checked_neg().ok_or_else(range)?;
        }
        Ok(Q { n, d })
    }

    pub fn int(n: i64) -> Q {
        Q {
            n: i128::from(n),
            d: 1,
        }
    }

    pub fn from_dec(x: Dec) -> Result<Q> {
        let (m, s) = x.parts();
        Q::new(m, 10i128.checked_pow(s).ok_or_else(range)?)
    }

    pub fn plus(self, o: Q) -> Result<Q> {
        let g = gcd(self.d, o.d);
        let (a, b) = (self.d / g, o.d / g);
        let n = self
            .n
            .checked_mul(b)
            .and_then(|x| o.n.checked_mul(a).and_then(|y| x.checked_add(y)))
            .ok_or_else(range)?;
        Q::new(n, a.checked_mul(o.d).ok_or_else(range)?)
    }

    pub fn negated(self) -> Result<Q> {
        Ok(Q {
            n: self.n.checked_neg().ok_or_else(range)?,
            d: self.d,
        })
    }

    pub fn minus(self, o: Q) -> Result<Q> {
        self.plus(o.negated()?)
    }

    pub fn times(self, o: Q) -> Result<Q> {
        let g1 = gcd(self.n, o.d).max(1);
        let g2 = gcd(o.n, self.d).max(1);
        let n = (self.n / g1).checked_mul(o.n / g2).ok_or_else(range)?;
        let d = (self.d / g2).checked_mul(o.d / g1).ok_or_else(range)?;
        Q::new(n, d)
    }

    pub fn over(self, o: Q) -> Result<Q> {
        if o.n == 0 {
            return Err(err("E_DOMAIN", "division by zero"));
        }
        self.times(Q::new(o.d, o.n)?)
    }

    pub fn is_zero(self) -> bool {
        self.n == 0
    }

    pub fn to_f64(self) -> f64 {
        self.n as f64 / self.d as f64
    }

    /// Rounded half-even to 6 decimals, as canonical decimal text (no trailing zeros).
    pub fn round6(self) -> Result<String> {
        let num = self.n.checked_mul(1_000_000).ok_or_else(range)?;
        let (mut q, r) = (num.div_euclid(self.d), num.rem_euclid(self.d));
        match r.cmp(&(self.d - r)) {
            Ordering::Greater => q += 1,
            Ordering::Equal if q % 2 != 0 => q += 1,
            _ => {}
        }
        let neg = q < 0;
        let mut t = q.unsigned_abs().to_string();
        if t.len() < 7 {
            t = format!("{}{t}", "0".repeat(7 - t.len()));
        }
        t.insert(t.len() - 6, '.');
        if neg {
            t.insert(0, '-');
        }
        Ok(Dec::parse(&t).expect("decimal text")?.to_string())
    }
}

/// Exact comparison by continued fractions: no products, so no overflow.
impl Ord for Q {
    fn cmp(&self, o: &Q) -> Ordering {
        let (qa, ra) = (self.n.div_euclid(self.d), self.n.rem_euclid(self.d));
        let (qb, rb) = (o.n.div_euclid(o.d), o.n.rem_euclid(o.d));
        if qa != qb {
            return qa.cmp(&qb);
        }
        match (ra == 0, rb == 0) {
            (true, true) => Ordering::Equal,
            (true, false) => Ordering::Less,
            (false, true) => Ordering::Greater,
            // ra/da against rb/db with both in (0, 1): compare the reciprocals, reversed.
            (false, false) => Q { n: o.d, d: rb }.cmp(&Q { n: self.d, d: ra }),
        }
    }
}

impl PartialOrd for Q {
    fn partial_cmp(&self, o: &Q) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}

fn frac(v: Option<&Json>, path: &str) -> Result<Q> {
    Q::from_dec(dec(v, path)?)
}

fn lots(v: Option<&Json>, path: &str) -> Result<i64> {
    let d = dec(v, path)?;
    if !d.on_grid(Dec::int(1))? || d.signum() < 0 {
        return Err(at(
            "E_DOMAIN",
            path,
            "not a non-negative integer number of lots",
        ));
    }
    d.to_string()
        .parse::<i64>()
        .map_err(|_| at("E_LIMIT", path, "too many lots"))
}

/// Expected cost, E min(A, S), P(A < S), E cost^2.
pub type Eval = (Q, Q, Q, Q);

/// Every grid point with its expected cost, in rank order.
pub type Ranking = Vec<(Q, Vec<i64>)>;

pub struct Problem {
    pub s: i64,
    h: Q,
    f: Q,
    theta: Q,
    lu: Q,
    lo: Q,
    lit_kind: Vec<bool>,
    qs: Vec<i64>,
    coef: Vec<Q>,
    tails: Vec<Vec<Q>>,
    lit: Vec<usize>,
    dark: Vec<usize>,
    rows: Vec<Vec<i64>>,
}

impl Problem {
    pub fn new(inp: &Json) -> Result<Problem> {
        let s = lots(inp.get("S"), "S")?;
        if s <= 0 {
            return Err(at("E_DOMAIN", "S", "S must be positive"));
        }
        let h = frac(inp.get("h"), "h")?;
        let f = frac(inp.get("f"), "f")?;
        let theta = frac(inp.get("theta"), "theta")?;
        let lu = frac(inp.get("lambda_u"), "lambda_u")?;
        let lo = frac(inp.get("lambda_o"), "lambda_o")?;
        if [theta, lu, lo].iter().any(|g| *g < Q::ZERO) {
            return Err(at("E_DOMAIN", "lambda_u", "negative penalty"));
        }
        let venues = match inp.get("venues").and_then(Json::as_array) {
            Some(v) if !v.is_empty() => v,
            _ => return Err(at("E_INPUT", "venues", "empty")),
        };
        if venues.len() > MAX_VENUES {
            return Err(at("E_LIMIT", "venues", "more than 64 venues"));
        }
        let (mut lit_kind, mut qs, mut coef, mut tails) = (vec![], vec![], vec![], vec![]);
        for (k, v) in venues.iter().enumerate() {
            let kind = v.get("kind").and_then(Json::as_str);
            let lit = match kind {
                Some("LIT") => true,
                Some("DARK") => false,
                _ => return Err(at("E_SCHEMA", "venues", &format!("venues/{k}/kind"))),
            };
            lit_kind.push(lit);
            let r = frac(v.get("r"), &format!("venues/{k}/r"))?;
            let adv = frac(v.get("as"), &format!("venues/{k}/as"))?;
            coef.push(h.plus(r)?.minus(adv)?);
            if lit {
                qs.push(lots(v.get("Q"), &format!("venues/{k}/Q"))?);
                tails.push(vec![]);
            } else {
                qs.push(0);
                let raw = match v.get("tail") {
                    None | Some(Json::Null) => &[][..],
                    Some(t) => t
                        .as_array()
                        .ok_or_else(|| at("E_SCHEMA", "venues", "tail: not an array"))?,
                };
                let tail = raw
                    .iter()
                    .map(|t| frac(Some(t), &format!("venues/{k}/tail")))
                    .collect::<Result<Vec<Q>>>()?;
                if tail.iter().any(|t| *t < Q::ZERO || *t > Q::ONE)
                    || tail.windows(2).any(|w| w[0] < w[1])
                {
                    return Err(at(
                        "E_DOMAIN",
                        "venues",
                        &format!("venues/{k}/tail: not a tail"),
                    ));
                }
                tails.push(tail);
            }
        }
        let lit: Vec<usize> = (0..lit_kind.len()).filter(|&k| lit_kind[k]).collect();
        let dark: Vec<usize> = (0..lit_kind.len()).filter(|&k| !lit_kind[k]).collect();
        let raw_rows = match inp.get("lit_samples") {
            None | Some(Json::Null) => &[][..],
            Some(r) => r.as_array().unwrap_or(&[]),
        };
        let rows_ok = matches!(
            inp.get("lit_samples"),
            None | Some(Json::Null | Json::Arr(_))
        );
        if !lit.is_empty() && (!rows_ok || raw_rows.is_empty()) {
            return Err(at("E_INPUT", "lit_samples", "empty"));
        }
        if raw_rows.len() > MAX_SAMPLES {
            return Err(at("E_LIMIT", "lit_samples", "more than 10^6 samples"));
        }
        let mut rows = Vec::with_capacity(raw_rows.len().max(1));
        for (i, r) in raw_rows.iter().enumerate() {
            let Some(r) = r.as_array() else {
                return Err(at("E_SCHEMA", "lit_samples", &format!("lit_samples/{i}")));
            };
            rows.push(
                r.iter()
                    .map(|x| lots(Some(x), &format!("lit_samples/{i}")))
                    .collect::<Result<Vec<i64>>>()?,
            );
        }
        if rows.is_empty() {
            rows.push(vec![]);
        }
        if rows.iter().any(|r| r.len() != lit.len()) {
            return Err(at(
                "E_INPUT",
                "lit_samples",
                "one value per LIT venue per row",
            ));
        }
        Ok(Problem {
            s,
            h,
            f,
            theta,
            lu,
            lo,
            lit_kind,
            qs,
            coef,
            tails,
            lit,
            dark,
            rows,
        })
    }

    pub fn venues(&self) -> usize {
        self.lit_kind.len()
    }

    fn tail(&self, k: usize, s: i64) -> Q {
        let t = &self.tails[k];
        if s <= 0 {
            Q::ONE
        } else if (s as usize) <= t.len() {
            t[s as usize - 1]
        } else {
            Q::ZERO
        }
    }

    /// Distribution of min(L, s) for dark venue k (zero-probability values dropped).
    fn dark_dist(&self, k: usize, l: i64) -> Result<Vec<(i64, Q)>> {
        let mut out = Vec::new();
        for j in 0..l {
            out.push((j, self.tail(k, j).minus(self.tail(k, j + 1))?));
        }
        out.push((l, self.tail(k, l)));
        Ok(out.into_iter().filter(|(_, p)| !p.is_zero()).collect())
    }

    fn scenario_cost(&self, m: i64, l: &[i64], fills: &[i64]) -> Result<(Q, i64)> {
        let a = m + fills.iter().sum::<i64>();
        let (under, over) = ((self.s - a).max(0), (a - self.s).max(0));
        let mut c = self.h.plus(self.f)?.times(Q::int(m))?;
        for k in 0..l.len() {
            c = c.minus(self.coef[k].times(Q::int(fills[k]))?)?;
        }
        let posted = m + l.iter().sum::<i64>() + under;
        c = c.plus(self.theta.times(Q::int(posted))?)?;
        c = c.plus(self.lu.times(Q::int(under))?)?;
        c = c.plus(self.lo.times(Q::int(over))?)?;
        Ok((c, a))
    }

    /// Exact (expected cost, E min(A, S), P(A < S), E cost^2).
    pub fn evaluate(&self, m: i64, l: &[i64]) -> Result<Eval> {
        let dists = self
            .dark
            .iter()
            .map(|&k| self.dark_dist(k, l[k]))
            .collect::<Result<Vec<_>>>()?;
        let (mut cost, mut fill, mut under, mut sq) = (Q::ZERO, Q::ZERO, Q::ZERO, Q::ZERO);
        let w_row = Q::new(1, self.rows.len() as i128)?;
        for row in &self.rows {
            let mut base = vec![0i64; l.len()];
            for (i, &k) in self.lit.iter().enumerate() {
                let x = row[i] - self.qs[k];
                base[k] = x.max(0) - (x - l[k]).max(0);
            }
            let mut idx = vec![0usize; dists.len()];
            loop {
                let mut p = w_row;
                let mut fills = base.clone();
                for (d, &k) in self.dark.iter().enumerate() {
                    let (j, pj) = dists[d][idx[d]];
                    fills[k] = j;
                    p = p.times(pj)?;
                }
                let (c, a) = self.scenario_cost(m, l, &fills)?;
                let pc = p.times(c)?;
                cost = cost.plus(pc)?;
                sq = sq.plus(pc.times(c)?)?;
                fill = fill.plus(p.times(Q::int(a.min(self.s)))?)?;
                if a < self.s {
                    under = under.plus(p)?;
                }
                // Odometer over the dark distributions, last venue fastest (itertools.product).
                if !next_index(&mut idx, |d| dists[d].len()) {
                    break;
                }
            }
        }
        Ok((cost, fill, under, sq))
    }

    fn cost(&self, t: &[i64]) -> Result<Q> {
        Ok(self.evaluate(t[0], &t[1..])?.0)
    }

    /// [CK] Prop. 3 for one lit venue, F the empirical CDF of xi, left-inverse quantile.
    pub fn closed_form(&self) -> Result<Vec<i64>> {
        if self.lit_kind != [true] {
            return Err(at(
                "E_DOMAIN",
                "method",
                "CLOSED_FORM needs exactly one LIT venue",
            ));
        }
        let mut xs: Vec<i64> = self.rows.iter().map(|r| r[0]).collect();
        xs.sort_unstable();
        let (n, q0, s) = (xs.len() as i128, self.qs[0], self.s);
        let r_eff = self.coef[0].minus(self.h)?;
        let num = self.h.times(Q::int(2))?.plus(self.f)?.plus(r_eff)?;
        let base = self.h.plus(r_eff)?.plus(self.theta)?;
        let cdf = |x: i64| Q::new(xs.iter().filter(|&&v| v <= x).count() as i128, n);
        let thr = |x: i64| -> Result<Option<Q>> {
            let fx = cdf(x)?;
            if fx.is_zero() {
                Ok(None)
            } else {
                Ok(Some(num.over(fx)?.minus(base)?))
            }
        };
        let (lo_t, hi_t) = (thr(q0 + s)?, thr(q0)?);
        if lo_t.is_none_or(|t| self.lu <= t) {
            return Ok(vec![0, s]);
        }
        if hi_t.is_some_and(|t| self.lu >= t) {
            return Ok(vec![s, 0]);
        }
        let target = num.over(self.lu.plus(base)?)?;
        let mut q = None;
        for &v in &xs {
            if cdf(v)? >= target {
                q = Some(v);
                break;
            }
        }
        let q = q.ok_or_else(|| at("E_DOMAIN", "method", "no quantile reaches the target"))?;
        let m = (s - q + q0).max(0).min(s);
        Ok(vec![m, s - m])
    }

    fn grid_points(&self) -> u128 {
        (self.s as u128 + 1)
            .checked_pow(self.venues() as u32 + 1)
            .unwrap_or(u128::MAX)
    }

    /// The best point and, when `ranking`, every grid point with its cost in rank order.
    pub fn sample_average(&self, ranking: bool) -> Result<(Vec<i64>, Ranking)> {
        let dim = self.venues() + 1;
        if self.grid_points() <= MAX_GRID {
            let mut scored = Vec::new();
            let mut t = vec![0i64; dim];
            loop {
                scored.push((self.cost(&t)?, t.clone()));
                let width = self.s as usize + 1;
                let mut idx: Vec<usize> = t.iter().map(|&v| v as usize).collect();
                if !next_index(&mut idx, |_| width) {
                    break;
                }
                t = idx.iter().map(|&v| v as i64).collect();
            }
            scored.sort();
            let best = scored[0].1.clone();
            return Ok((best, if ranking { scored } else { vec![] }));
        }
        if ranking {
            return Err(at(
                "E_LIMIT",
                "ranking",
                "ranking needs a grid of at most 10^6 points",
            ));
        }
        Ok((self.descent(None)?, vec![]))
    }

    fn start(&self) -> Result<Vec<i64>> {
        if self.lit_kind == [true] {
            return self.closed_form();
        }
        let mut t = vec![0i64; self.venues() + 1];
        if self.lit_kind[0] {
            t[1] = self.s;
        }
        Ok(t)
    }

    /// Exact coordinate descent on the sample-average cost from `start` (default the [CK]
    /// single-venue start); each pass tries every value 0..S per coordinate.
    pub fn descent(&self, start: Option<Vec<i64>>) -> Result<Vec<i64>> {
        let mut best = match start {
            Some(t) => t,
            None => self.start()?,
        };
        let mut cur = self.cost(&best)?;
        let mut changed = true;
        while changed {
            changed = false;
            for i in 0..best.len() {
                for v in 0..=self.s {
                    let mut t = best.clone();
                    t[i] = v;
                    let c = self.cost(&t)?;
                    if (c, &t) < (cur, &best) {
                        (best, cur, changed) = (t, c, true);
                    }
                }
            }
        }
        Ok(best)
    }

    /// [CK] section 4: projected subgradient on X in [0, S]^(K+1), step / sqrt(n), iterates
    /// averaged; the average is rounded to the best floor/ceiling neighbour (HR-38), then polished
    /// by exact coordinate descent (the cost is flat where a posted size is beyond every outflow
    /// and theta = 0, so the averaged iterate can stop anywhere on that plateau).
    pub fn stochastic(&self, iterations: i64, step: f64, seed: u64) -> Result<Vec<i64>> {
        let mut rng = Xoshiro::seeded(seed, 0);
        let k_n = self.venues();
        let s_f = self.s as f64;
        let mut x: Vec<f64> = self.start()?.iter().map(|&v| v as f64).collect();
        let mut avg = vec![0.0f64; k_n + 1];
        let (h, f, th, lu, lo) = (
            self.h.to_f64(),
            self.f.to_f64(),
            self.theta.to_f64(),
            self.lu.to_f64(),
            self.lo.to_f64(),
        );
        let coef: Vec<f64> = self.coef.iter().map(|c| c.to_f64()).collect();
        let tails: Vec<Vec<f64>> = self
            .tails
            .iter()
            .map(|t| t.iter().map(|v| v.to_f64()).collect())
            .collect();
        let nrows = self.rows.len();
        for n in 1..=iterations.max(0) {
            let pick = ((rng.next_uniform() * nrows as f64) as usize).min(nrows - 1);
            let row = &self.rows[pick];
            let mut room = vec![0.0f64; k_n];
            let mut fills = vec![0.0f64; k_n];
            for (i, &k) in self.lit.iter().enumerate() {
                let xi = (row[i] - self.qs[k]) as f64;
                fills[k] = xi.max(0.0).min(x[k + 1]);
                room[k] = if xi > x[k + 1] { 1.0 } else { 0.0 };
            }
            for &k in &self.dark {
                let u = rng.next_uniform();
                let mut s = 0usize;
                while s < tails[k].len() && u < tails[k][s] {
                    s += 1;
                }
                fills[k] = (s as f64).min(x[k + 1]);
                room[k] = if s as f64 > x[k + 1] { 1.0 } else { 0.0 };
            }
            let a = x[0] + fills.iter().sum::<f64>();
            let g_a = (if a < s_f { -(lu + th) } else { 0.0 }) + (if a > s_f { lo } else { 0.0 });
            let mut grad = vec![h + f + th + g_a];
            grad.extend((0..k_n).map(|k| th + room[k] * (g_a - coef[k])));
            let eta = step / (n as f64).sqrt();
            for (v, g) in x.iter_mut().zip(&grad) {
                *v = (*v - eta * g).max(0.0).min(s_f);
            }
            for (a, v) in avg.iter_mut().zip(&x) {
                *a += (v - *a) / n as f64;
            }
        }
        // Every floor/ceiling combination, in lexicographic order; the best (cost, point) wins.
        let opts: Vec<Vec<i64>> = avg
            .iter()
            .map(|a| {
                let (lo, hi) = (a.floor() as i64, a.ceil() as i64);
                if lo == hi { vec![lo] } else { vec![lo, hi] }
            })
            .collect();
        let mut idx = vec![0usize; opts.len()];
        let mut best: Option<(Q, Vec<i64>)> = None;
        loop {
            let t: Vec<i64> = idx.iter().zip(&opts).map(|(&i, o)| o[i]).collect();
            let c = self.cost(&t)?;
            if best.as_ref().is_none_or(|(bc, bt)| (c, &t) < (*bc, bt)) {
                best = Some((c, t));
            }
            if !next_index(&mut idx, |d| opts[d].len()) {
                break;
            }
        }
        let rounded = best.map(|b| b.1).unwrap_or_default();
        self.descent(Some(rounded))
    }
}

/// Advances a lexicographic odometer (last position fastest, as `itertools.product`); false once
/// every combination has been visited (at once for an empty odometer).
fn next_index(idx: &mut [usize], len: impl Fn(usize) -> usize) -> bool {
    for d in (0..idx.len()).rev() {
        idx[d] += 1;
        if idx[d] < len(d) {
            return true;
        }
        idx[d] = 0;
    }
    false
}

fn point(t: &[i64]) -> (Json, Json) {
    (
        Json::Str(t[0].to_string()),
        Json::Arr(t[1..].iter().map(|v| Json::Str(v.to_string())).collect()),
    )
}

/// The `exec.sor.allocate` result for the raw input object.
pub fn allocate(inp: &Json) -> Result<Json> {
    let p = Problem::new(inp)?;
    let method = match inp.get("method") {
        None | Some(Json::Null) => "SAMPLE_AVERAGE",
        Some(m) => m.as_str().unwrap_or(""),
    };
    let want_rank = matches!(inp.get("ranking"), Some(Json::Bool(true)));
    let mut ranking = vec![];
    let best = match method {
        "CLOSED_FORM" => {
            let ml = p.closed_form()?;
            vec![ml[0], ml[1]]
        }
        "STOCHASTIC_APPROX" => {
            let int = |k: &str, d: i64| match inp.get(k) {
                None | Some(Json::Null) => Ok(d),
                Some(v) => v
                    .as_int()
                    .ok_or_else(|| at("E_SCHEMA", k, "expected an integer")),
            };
            let step = match inp.get("step") {
                None | Some(Json::Null) => 1.0,
                Some(v) => v
                    .as_f64()
                    .ok_or_else(|| at("E_SCHEMA", "step", "expected a number"))?,
            };
            let seed = int("seed", 0)?;
            if seed < 0 {
                return Err(at("E_DOMAIN", "seed", "negative seed"));
            }
            p.stochastic(int("iterations", 10_000)?, step, seed as u64)?
        }
        "SAMPLE_AVERAGE" => {
            let (b, r) = p.sample_average(want_rank)?;
            ranking = r;
            b
        }
        _ => return Err(at("E_SCHEMA", "method", "unknown method")),
    };
    let (cost, fill, under, sq) = p.evaluate(best[0], &best[1..])?;
    let (m, l) = point(&best);
    let mut out = vec![
        ("L".to_string(), l),
        ("M".to_string(), m),
        ("expected_cost".to_string(), Json::Str(cost.round6()?)),
    ];
    if matches!(inp.get("report_se"), Some(Json::Bool(true))) {
        let var = sq.minus(cost.times(cost)?)?.to_f64().max(0.0);
        let se = var.sqrt() / (p.rows.len() as f64).sqrt();
        let t = format!("{se:.6}");
        let t = Dec::parse(&t).expect("fixed text")?.to_string();
        out.push(("expected_cost_se".into(), Json::Str(t)));
    }
    out.push(("expected_fill".into(), Json::Str(fill.round6()?)));
    if matches!(inp.get("report_se"), Some(Json::Bool(true))) {
        out.push(("label".into(), LABEL.into()));
    }
    out.push(("p_underfill".into(), Json::Str(under.round6()?)));
    if want_rank {
        let rows = ranking
            .iter()
            .map(|(c, t)| {
                let (m, l) = point(t);
                Ok(Json::Obj(vec![
                    ("L".into(), l),
                    ("M".into(), m),
                    ("expected_cost".into(), Json::Str(c.round6()?)),
                ]))
            })
            .collect::<Result<Vec<Json>>>()?;
        out.push(("ranking".into(), Json::Arr(rows)));
    }
    Ok(Json::Obj(out))
}

#[cfg(test)]
mod tests {
    use super::Q;

    #[test]
    fn rational_arithmetic_and_rounding() {
        let a = Q::new(1, 3).unwrap();
        let b = Q::new(1, 6).unwrap();
        assert_eq!(a.plus(b).unwrap(), Q::new(1, 2).unwrap());
        assert!(a > b && b.minus(a).unwrap() < Q::ZERO);
        assert_eq!(Q::new(5, 10_000_000).unwrap().round6().unwrap(), "0"); // half-even down
        assert_eq!(
            Q::new(15, 10_000_000).unwrap().round6().unwrap(),
            "0.000002"
        );
        assert_eq!(Q::new(-7, 1).unwrap().round6().unwrap(), "-7");
        assert_eq!(Q::new(2, 3).unwrap().round6().unwrap(), "0.666667");
        let big = Q::new(i128::MAX / 3, 7).unwrap();
        assert!(big > Q::new(i128::MAX / 3 - 1, 7).unwrap());
        assert!(big.times(big).is_err_and(|e| e.code == "E_LIMIT"));
    }
}
