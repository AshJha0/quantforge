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
//! distributions given by their tails, in exact decimals ([`Dec`]; HR-57: every value computed,
//! at the same steps as the Python build's `_r`, has `|coefficient| < 10^36` and scale <= 36, else
//! `E_LIMIT`), summed over rows and divided by the row count only on output (long division,
//! rounded half-even to 6 decimals). [`Q`] is the 128-bit rational the dark pool uses.
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

fn limit() -> QfError {
    at(
        "E_LIMIT",
        "sor",
        "decimal outside the exact range (36 digits, 36 decimals; HR-57)",
    )
}

/// HR-57/HR-58 at one exact step (Python `_r`): the result in range, else `E_LIMIT`. [`Dec`]
/// checks its range on every operation and treats a 128-bit overflow as out of range.
fn r(x: Result<Dec>) -> Result<Dec> {
    x.map_err(|_| limit())
}

fn add(a: Dec, b: Dec) -> Result<Dec> {
    r(a.checked_add(b))
}

fn sub(a: Dec, b: Dec) -> Result<Dec> {
    r(a.checked_sub(b))
}

fn mul(a: Dec, b: Dec) -> Result<Dec> {
    r(a.checked_mul(b))
}

fn mul_int(a: Dec, n: i64) -> Result<Dec> {
    mul(a, Dec::int(n))
}

/// Rounds a non-negative decimal `int.frac` (with `sticky` set when non-zero digits follow
/// `frac`) half-even to `places` decimals; returns the integer and fraction digit strings.
fn round_digits(int: &str, frac: &str, sticky: bool, places: usize) -> (String, String) {
    let mut fr: Vec<u8> = frac.bytes().collect();
    fr.resize(fr.len().max(places), b'0');
    let (kept, rest) = fr.split_at(places);
    let mut digits: Vec<u8> = int.bytes().chain(kept.iter().copied()).collect();
    let up = match rest.first() {
        None => false,
        Some(&d) if d > b'5' => true,
        Some(&d) if d < b'5' => false,
        Some(_) => {
            if sticky || rest[1..].iter().any(|&d| d != b'0') {
                true
            } else {
                digits.last().is_some_and(|&d| (d - b'0') % 2 == 1)
            }
        }
    };
    if up {
        let mut i = digits.len();
        loop {
            if i == 0 {
                digits.insert(0, b'1');
                break;
            }
            i -= 1;
            if digits[i] == b'9' {
                digits[i] = b'0';
            } else {
                digits[i] += 1;
                break;
            }
        }
    }
    let t = String::from_utf8(digits).expect("ascii digits");
    let (i, f) = t.split_at(t.len() - places);
    (i.to_string(), f.to_string())
}

/// Canonical text of a rounded value: leading zeros and trailing fraction zeros dropped, "0" for
/// zero, `-` only for a non-zero negative value.
fn canon(neg: bool, int: &str, frac: &str) -> String {
    let int = int.trim_start_matches('0');
    let frac = frac.trim_end_matches('0');
    if int.is_empty() && frac.is_empty() {
        return "0".into();
    }
    let int = if int.is_empty() { "0" } else { int };
    let mut t = String::from(if neg { "-" } else { "" });
    t.push_str(int);
    if !frac.is_empty() {
        t.push('.');
        t.push_str(frac);
    }
    t
}

/// `x / n` (`n > 0`) by long division, rounded half-even to `places` decimals, as canonical text.
fn div_round(x: Dec, n: u64, places: usize) -> String {
    let (m, s) = x.parts();
    let mut digits = m.unsigned_abs().to_string();
    let s = s as usize;
    if digits.len() <= s {
        digits = format!("{}{digits}", "0".repeat(s + 1 - digits.len()));
    }
    let point = digits.len() - s;
    let mut src: Vec<u8> = digits.into_bytes();
    src.resize(src.len().max(point + places + 1), b'0');
    let (n, mut rem) = (u128::from(n), 0u128);
    let mut q = Vec::with_capacity(src.len());
    for d in src {
        rem = rem * 10 + u128::from(d - b'0');
        q.push(b'0' + (rem / n) as u8);
        rem %= n;
    }
    let q = String::from_utf8(q).expect("ascii digits");
    let (int, frac) = q.split_at(point);
    let (int, frac) = round_digits(int, frac, rem != 0, places);
    canon(m < 0, &int, &frac)
}

/// Python `_dec18`: `x / n` rounded half-even to 18 decimals, read as binary64.
fn dec18(x: Dec, n: u64) -> f64 {
    div_round(x, n, 18).parse().expect("decimal text")
}

/// HR-40 standard error (Python `_se`): a = E[c^2], b = E[c], each exact, rounded half-even to 18
/// decimals and read as binary64; `se = sqrt(max(a - b * b, 0) / n_rows)` in binary64 (no fused
/// multiply-add), written from its exact binary value rounded half-even to 6 decimals.
fn std_err(sum_cost: Dec, sum_sq: Dec, n_rows: u64) -> String {
    let (a, b) = (dec18(sum_sq, n_rows), dec18(sum_cost, n_rows));
    let bb = b * b;
    let se = ((a - bb).max(0.0) / n_rows as f64).sqrt();
    // 1100 fraction digits hold every binary64 value exactly.
    let t = format!("{se:.1100}");
    let (int, frac) = t.split_once('.').expect("fixed text");
    let (int, frac) = round_digits(int, frac, false, 6);
    canon(false, &int, &frac)
}

fn to_f64(x: Dec) -> f64 {
    x.to_string().parse().expect("decimal text")
}

fn frac(v: Option<&Json>, path: &str) -> Result<Dec> {
    dec(v, path)
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

/// Row sums (each divided by the row count only on output): cost, E min(A, S), P(A < S), cost^2.
pub type Eval = (Dec, Dec, Dec, Dec);

/// Every grid point with its summed cost, in rank order.
pub type Ranking = Vec<(Dec, Vec<i64>)>;

pub struct Problem {
    pub s: i64,
    h: Dec,
    f: Dec,
    theta: Dec,
    lu: Dec,
    lo: Dec,
    lit_kind: Vec<bool>,
    qs: Vec<i64>,
    coef: Vec<Dec>,
    tails: Vec<Vec<Dec>>,
    lit: Vec<usize>,
    dark: Vec<usize>,
    rows: Vec<Vec<i64>>,
    want_sq: bool,
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
        if [theta, lu, lo].iter().any(|g| g.signum() < 0) {
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
        let one = Dec::int(1);
        for (k, v) in venues.iter().enumerate() {
            let kind = v.get("kind").and_then(Json::as_str);
            let lit = match kind {
                Some("LIT") => true,
                Some("DARK") => false,
                _ => return Err(at("E_SCHEMA", "venues", &format!("venues/{k}/kind"))),
            };
            lit_kind.push(lit);
            let rk = frac(v.get("r"), &format!("venues/{k}/r"))?;
            let hr = add(h, rk)?;
            let adv = frac(v.get("as"), &format!("venues/{k}/as"))?;
            coef.push(sub(hr, adv)?);
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
                    .collect::<Result<Vec<Dec>>>()?;
                if tail.iter().any(|t| t.signum() < 0 || *t > one)
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
        let want_sq = matches!(inp.get("report_se"), Some(Json::Bool(true)));
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
            want_sq,
        })
    }

    pub fn venues(&self) -> usize {
        self.lit_kind.len()
    }

    /// The number of `lit_samples` rows (1 when there are none).
    pub fn n_rows(&self) -> u64 {
        self.rows.len() as u64
    }

    fn tail(&self, k: usize, s: i64) -> Dec {
        let t = &self.tails[k];
        if s <= 0 {
            Dec::int(1)
        } else if (s as usize) <= t.len() {
            t[s as usize - 1]
        } else {
            Dec::ZERO
        }
    }

    /// Distribution of min(L, s) for dark venue k (zero-probability values dropped).
    fn dark_dist(&self, k: usize, l: i64) -> Result<Vec<(i64, Dec)>> {
        let mut out = Vec::new();
        for j in 0..l {
            out.push((j, sub(self.tail(k, j), self.tail(k, j + 1))?));
        }
        out.push((l, self.tail(k, l)));
        Ok(out.into_iter().filter(|(_, p)| !p.is_zero()).collect())
    }

    /// Cost of one scenario, each step range-checked (HR-57) in the order of the Python build.
    fn scenario_cost(&self, m: i64, l: &[i64], fills: &[i64]) -> Result<(Dec, i64)> {
        let a = m + fills.iter().sum::<i64>();
        let (under, over) = ((self.s - a).max(0), (a - self.s).max(0));
        let mut c = mul_int(add(self.h, self.f)?, m)?;
        for k in 0..l.len() {
            if fills[k] != 0 {
                c = sub(c, mul_int(self.coef[k], fills[k])?)?;
            }
        }
        if !self.theta.is_zero() {
            let posted = m + l.iter().sum::<i64>() + under;
            c = add(c, mul_int(self.theta, posted)?)?;
        }
        if under != 0 {
            c = add(c, mul_int(self.lu, under)?)?;
        }
        if over != 0 {
            c = add(c, mul_int(self.lo, over)?)?;
        }
        Ok((c, a))
    }

    /// Exact row sums (cost, min(A, S), [A < S], cost^2), each step range-checked (HR-57); divide
    /// by [`Problem::n_rows`] for the expectations. cost^2 is summed only when `report_se` is set.
    pub fn evaluate(&self, m: i64, l: &[i64]) -> Result<Eval> {
        let dists = self
            .dark
            .iter()
            .map(|&k| self.dark_dist(k, l[k]))
            .collect::<Result<Vec<_>>>()?;
        let (mut cost, mut fill, mut under, mut sq) = (Dec::ZERO, Dec::ZERO, Dec::ZERO, Dec::ZERO);
        for row in &self.rows {
            let mut base = vec![0i64; l.len()];
            for (i, &k) in self.lit.iter().enumerate() {
                let x = row[i] - self.qs[k];
                base[k] = x.max(0) - (x - l[k]).max(0);
            }
            let mut idx = vec![0usize; dists.len()];
            loop {
                let mut p = Dec::int(1);
                let mut fills = base.clone();
                for (d, &k) in self.dark.iter().enumerate() {
                    let (j, pj) = dists[d][idx[d]];
                    fills[k] = j;
                    p = mul(p, pj)?;
                }
                let (c, a) = self.scenario_cost(m, l, &fills)?;
                cost = add(cost, mul(p, c)?)?;
                if self.want_sq {
                    sq = add(sq, mul(mul(p, c)?, c)?)?;
                }
                fill = add(fill, mul_int(p, a.min(self.s))?)?;
                if a < self.s {
                    under = add(under, p)?;
                }
                // Odometer over the dark distributions, last venue fastest (itertools.product).
                if !next_index(&mut idx, |d| dists[d].len()) {
                    break;
                }
            }
        }
        Ok((cost, fill, under, sq))
    }

    fn cost(&self, t: &[i64]) -> Result<Dec> {
        Ok(self.evaluate(t[0], &t[1..])?.0)
    }

    /// [CK] Prop. 3 for one lit venue, F the empirical CDF of xi, left-inverse quantile, compared
    /// in the cross-multiplied form `(lambda_u + base) n F(x) <= num n` of the Python build, each
    /// step range-checked (HR-57).
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
        let (n, q0, s) = (xs.len() as i64, self.qs[0], self.s);
        let r_eff = sub(self.coef[0], self.h)?;
        let num = add(add(add(self.h, self.h)?, self.f)?, r_eff)?;
        let base = add(add(self.h, r_eff)?, self.theta)?;
        let count = |x: i64| xs.iter().filter(|&&v| v <= x).count() as i64;
        let lb = add(self.lu, base)?;
        let numn = mul_int(num, n)?;
        let (c_lo, c_hi) = (count(q0 + s), count(q0));
        if c_lo == 0 || mul_int(lb, c_lo)? <= numn {
            return Ok(vec![0, s]);
        }
        if c_hi != 0 && mul_int(lb, c_hi)? >= numn {
            return Ok(vec![s, 0]);
        }
        if lb.is_zero() {
            return Err(at(
                "E_DOMAIN",
                "lambda_u",
                "lambda_u + h + r + theta is zero",
            ));
        }
        let mut q = *xs.last().expect("at least one row");
        for &v in &xs {
            let lhs = mul_int(lb, count(v))?;
            let hit = if lb.signum() > 0 {
                lhs >= numn
            } else {
                lhs <= numn
            };
            if hit {
                q = v;
                break;
            }
        }
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
            to_f64(self.h),
            to_f64(self.f),
            to_f64(self.theta),
            to_f64(self.lu),
            to_f64(self.lo),
        );
        let coef: Vec<f64> = self.coef.iter().map(|c| to_f64(*c)).collect();
        let tails: Vec<Vec<f64>> = self
            .tails
            .iter()
            .map(|t| t.iter().map(|v| to_f64(*v)).collect())
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
        let mut best: Option<(Dec, Vec<i64>)> = None;
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
    let n = p.n_rows();
    let (m, l) = point(&best);
    let mut out = vec![
        ("L".to_string(), l),
        ("M".to_string(), m),
        (
            "expected_cost".to_string(),
            Json::Str(div_round(cost, n, 6)),
        ),
    ];
    let report_se = matches!(inp.get("report_se"), Some(Json::Bool(true)));
    if report_se {
        out.push(("expected_cost_se".into(), Json::Str(std_err(cost, sq, n))));
    }
    out.push(("expected_fill".into(), Json::Str(div_round(fill, n, 6))));
    if report_se {
        out.push(("label".into(), LABEL.into()));
    }
    out.push(("p_underfill".into(), Json::Str(div_round(under, n, 6))));
    if want_rank {
        let rows = ranking
            .iter()
            .map(|(c, t)| {
                let (m, l) = point(t);
                Ok(Json::Obj(vec![
                    ("L".into(), l),
                    ("M".into(), m),
                    ("expected_cost".into(), Json::Str(div_round(*c, n, 6))),
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
