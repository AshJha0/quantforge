//! Stage J wave 1 research operations: backtester, purged CV, Viterbi regimes and research
//! statistics (`specifications/11-research/`, rulings J-1 to J-19).
use crate::credit_options::normal_inv;
use crate::error::{Result, fail};
use crate::stats::normal_cdf;

/// `-0.0` becomes `0.0` (rule F-3).
fn pz(x: f64) -> f64 {
    x + 0.0
}

// ---------------------------------------------------------------- backtester

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Engine {
    Event,
    Vector,
}

#[derive(Debug, Clone, Copy)]
pub struct Costs {
    pub half_spread_bps: f64,
    pub commission_per_unit: f64,
    pub fixed_per_trade: f64,
    pub multiplier: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Backtest {
    pub positions: Vec<f64>,
    pub trades: Vec<f64>,
    pub pnl_gross: Vec<f64>,
    pub cost: Vec<f64>,
    pub pnl_net: Vec<f64>,
    pub equity: Vec<f64>,
    pub total_gross: f64,
    pub total_spread_cost: f64,
    pub total_commission: f64,
    pub total_fixed_cost: f64,
    pub total_net: f64,
    pub turnover: f64,
    pub trade_count: i64,
    pub max_drawdown: f64,
}

pub fn backtest(
    prices: &[f64],
    targets: &[f64],
    lag: i64,
    c: Costs,
    engine: Engine,
) -> Result<Backtest> {
    let t = prices.len();
    if targets.len() != t || t < 2 || lag < 0 || lag >= t as i64 {
        return fail(
            "E_INPUT",
            "targets must match prices, T >= 2 and 0 <= lag < T",
        );
    }
    if prices.iter().any(|&p| p <= 0.0)
        || c.half_spread_bps < 0.0
        || c.commission_per_unit < 0.0
        || c.fixed_per_trade < 0.0
        || c.multiplier <= 0.0
    {
        return fail(
            "E_DOMAIN",
            "prices and multiplier must be positive, costs non-negative",
        );
    }
    let lag = lag as usize;
    let hs = c.half_spread_bps / 10_000.0;
    let m = c.multiplier;
    // Per-bar spread, commission and fixed costs.
    let (q, d, g, s, cm, f) = match engine {
        Engine::Event => {
            let mut v: [Vec<f64>; 6] = Default::default();
            let mut prev = 0.0;
            for k in 0..t {
                let qk = if k >= lag { targets[k - lag] } else { 0.0 };
                let dk = qk - prev;
                let gk = if k >= 1 {
                    prev * (prices[k] - prices[k - 1]) * m
                } else {
                    0.0
                };
                let sk = dk.abs() * prices[k] * hs * m;
                let ck = dk.abs() * c.commission_per_unit;
                let fk = if dk != 0.0 { c.fixed_per_trade } else { 0.0 };
                for (vec, x) in v.iter_mut().zip([qk, dk, gk, sk, ck, fk]) {
                    vec.push(x);
                }
                prev = qk;
            }
            let [q, d, g, s, cm, f] = v;
            (q, d, g, s, cm, f)
        }
        Engine::Vector => {
            let q: Vec<f64> = (0..t)
                .map(|k| if k >= lag { targets[k - lag] } else { 0.0 })
                .collect();
            let lagged: Vec<f64> = std::iter::once(0.0)
                .chain(q[..t - 1].iter().copied())
                .collect();
            let d: Vec<f64> = q.iter().zip(&lagged).map(|(a, b)| a - b).collect();
            let dp: Vec<f64> = std::iter::once(0.0)
                .chain(prices.windows(2).map(|w| w[1] - w[0]))
                .collect();
            let g: Vec<f64> = lagged
                .iter()
                .zip(&dp)
                .enumerate()
                .map(|(k, (a, b))| if k == 0 { 0.0 } else { a * b * m })
                .collect();
            let s = d
                .iter()
                .zip(prices)
                .map(|(x, p)| x.abs() * p * hs * m)
                .collect();
            let cm = d.iter().map(|x| x.abs() * c.commission_per_unit).collect();
            let f = d
                .iter()
                .map(|&x| if x != 0.0 { c.fixed_per_trade } else { 0.0 })
                .collect();
            (q, d, g, s, cm, f)
        }
    };
    let cost: Vec<f64> = (0..t).map(|k| s[k] + cm[k] + f[k]).collect();
    let net: Vec<f64> = (0..t).map(|k| g[k] - cost[k]).collect();
    let mut equity = Vec::with_capacity(t);
    let (mut e, mut peak, mut mdd) = (0.0, 0.0_f64, 0.0_f64);
    for &n in &net {
        e += n;
        peak = peak.max(e);
        mdd = mdd.max(peak - e);
        equity.push(pz(e));
    }
    let sum = |v: &[f64]| pz(v.iter().sum::<f64>());
    let turnover = pz(d.iter().zip(prices).map(|(x, p)| x.abs() * p * m).sum());
    let fix = |v: Vec<f64>| v.into_iter().map(pz).collect::<Vec<f64>>();
    Ok(Backtest {
        total_gross: sum(&g),
        total_spread_cost: sum(&s),
        total_commission: sum(&cm),
        total_fixed_cost: sum(&f),
        total_net: sum(&net),
        turnover,
        trade_count: d.iter().filter(|&&x| x != 0.0).count() as i64,
        max_drawdown: pz(mdd),
        positions: fix(q),
        trades: fix(d),
        pnl_gross: fix(g),
        cost: fix(cost),
        pnl_net: fix(net),
        equity,
    })
}

// ---------------------------------------------------------------- purged CV

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Fold {
    pub test: Vec<usize>,
    pub train: Vec<usize>,
}

pub fn purged_kfold(
    t0: &[f64],
    t1: &[f64],
    k: i64,
    embargo_pct: f64,
) -> Result<(Vec<Fold>, usize)> {
    let n = t0.len();
    if t1.len() != n || k < 2 || k > n as i64 || t0.windows(2).any(|w| w[1] < w[0]) {
        return fail(
            "E_INPUT",
            "t0 and t1 lengths must match, 2 <= n_splits <= n, t0 non-decreasing",
        );
    }
    if t0.iter().zip(t1).any(|(a, b)| b < a) || !(0.0..1.0).contains(&embargo_pct) {
        return fail("E_DOMAIN", "t1 >= t0 and 0 <= embargo_pct < 1 are required");
    }
    let k = k as usize;
    let h = (embargo_pct * n as f64).floor() as usize;
    let (base, extra) = (n / k, n % k);
    let mut folds = Vec::with_capacity(k);
    let mut a = 0;
    for fidx in 0..k {
        let b = a + base + usize::from(fidx < extra);
        let lo = t0[a];
        let hi = t1[a..b].iter().copied().fold(f64::NEG_INFINITY, f64::max);
        let train = (0..n)
            .filter(|&j| {
                !(a..b).contains(&j) && !(b..b + h).contains(&j) && !(t0[j] <= hi && t1[j] >= lo)
            })
            .collect();
        folds.push(Fold {
            test: (a..b).collect(),
            train,
        });
        a = b;
    }
    Ok((folds, h))
}

fn binomial(n: u64, k: u64) -> u128 {
    let mut r: u128 = 1;
    for i in 0..k {
        r = r * u128::from(n - i) / u128::from(i + 1);
    }
    r
}

/// `(C(N, k), k C(N, k) / N)`.
pub fn cpcv_paths(n: i64, k: i64) -> Result<(i64, i64)> {
    if n < 2 || k < 1 || k >= n || n > 64 {
        return fail("E_INPUT", "2 <= n_groups and 1 <= n_test_groups < n_groups");
    }
    let (n, k) = (n as u64, k as u64);
    Ok((binomial(n, k) as i64, binomial(n - 1, k - 1) as i64))
}

// ---------------------------------------------------------------- Viterbi

/// `log_e[t][j]` is the log emission of observation `t` under state `j`.
pub fn viterbi(
    initial: &[f64],
    transition: &[Vec<f64>],
    log_e: &[Vec<f64>],
) -> Result<(Vec<usize>, f64)> {
    let k = initial.len();
    let la: Vec<Vec<f64>> = transition
        .iter()
        .map(|r| r.iter().map(|x| x.ln()).collect())
        .collect();
    let mut delta: Vec<f64> = (0..k).map(|j| initial[j].ln() + log_e[0][j]).collect();
    let mut back: Vec<Vec<usize>> = Vec::with_capacity(log_e.len());
    for e in &log_e[1..] {
        let mut next = vec![0.0; k];
        let mut bp = vec![0; k];
        for j in 0..k {
            let (mut best, mut arg) = (delta[0] + la[0][j], 0);
            for i in 1..k {
                let v = delta[i] + la[i][j];
                if v > best {
                    best = v;
                    arg = i;
                }
            }
            next[j] = best + e[j];
            bp[j] = arg;
        }
        back.push(bp);
        delta = next;
    }
    let mut end = 0;
    for j in 1..k {
        if delta[j] > delta[end] {
            end = j;
        }
    }
    let lp = delta[end];
    if lp == f64::NEG_INFINITY {
        return fail("E_DOMAIN", "every path has probability zero");
    }
    let mut states = vec![end];
    for bp in back.iter().rev() {
        let s = bp[*states.last().unwrap_or(&0)];
        states.push(s);
    }
    states.reverse();
    Ok((states, lp))
}

/// Checks and runs Viterbi. `emission` is either direct probabilities (`T x K`) or
/// `(observations, means, sds)`.
pub fn regime_viterbi(
    initial: &[f64],
    transition: &[Vec<f64>],
    emission: Option<&[Vec<f64>]>,
    gaussian: Option<(&[f64], &[f64], &[f64])>,
) -> Result<(Vec<usize>, f64)> {
    let k = initial.len();
    let shapes_ok = k >= 1
        && transition.len() == k
        && transition.iter().all(|r| r.len() == k)
        && match (emission, gaussian) {
            (Some(e), None) => !e.is_empty() && e.iter().all(|r| r.len() == k),
            (None, Some((y, m, s))) => !y.is_empty() && m.len() == k && s.len() == k,
            _ => false,
        };
    if !shapes_ok {
        return fail(
            "E_INPUT",
            "exactly one emission form, with shapes K, K x K and T x K",
        );
    }
    let bad_row =
        |r: &[f64]| r.iter().any(|&x| x < 0.0) || (r.iter().sum::<f64>() - 1.0).abs() > 1e-9;
    if bad_row(initial) || transition.iter().any(|r| bad_row(r)) {
        return fail(
            "E_DOMAIN",
            "probabilities must be non-negative and rows sum to 1",
        );
    }
    let log_e: Vec<Vec<f64>> = match (emission, gaussian) {
        (Some(e), _) => {
            if e.iter().flatten().any(|&x| x < 0.0) {
                return fail("E_DOMAIN", "a negative emission");
            }
            e.iter()
                .map(|r| r.iter().map(|x| x.ln()).collect())
                .collect()
        }
        (None, Some((y, m, s))) => {
            if s.iter().any(|&x| x <= 0.0) {
                return fail("E_DOMAIN", "sds must be positive");
            }
            let c = (2.0 * std::f64::consts::PI).ln() / 2.0;
            y.iter()
                .map(|&yt| {
                    (0..k)
                        .map(|j| -s[j].ln() - c - (yt - m[j]).powi(2) / (2.0 * s[j] * s[j]))
                        .collect()
                })
                .collect()
        }
        (None, None) => unreachable!("shapes checked"),
    };
    viterbi(initial, transition, &log_e)
}

// ---------------------------------------------------------------- statistics

pub const EULER_GAMMA: f64 = 0.577_215_664_901_532_9;

/// `(z, Phi(z))` of the PSR against `benchmark`.
pub fn psr(sr: f64, n_obs: i64, skew: f64, kurtosis: f64, benchmark: f64) -> Result<(f64, f64)> {
    if n_obs < 2 {
        return fail("E_INPUT", "n_obs >= 2");
    }
    if kurtosis < 1.0 {
        return fail("E_DOMAIN", "kurtosis >= 1");
    }
    let v = 1.0 - skew * sr + (kurtosis - 1.0) / 4.0 * sr * sr;
    if v <= 0.0 {
        return fail("E_DOMAIN", "the PSR variance term is not positive");
    }
    let z = (sr - benchmark) * ((n_obs - 1) as f64).sqrt() / v.sqrt();
    Ok((pz(z), normal_cdf(z)))
}

/// `(sr0, z, dsr)`.
pub fn dsr(
    sr: f64,
    n_obs: i64,
    skew: f64,
    kurtosis: f64,
    n_trials: i64,
    sr_variance: f64,
) -> Result<(f64, f64, f64)> {
    if n_obs < 2 || n_trials < 1 {
        return fail("E_INPUT", "n_obs >= 2 and n_trials >= 1");
    }
    if sr_variance < 0.0 {
        return fail("E_DOMAIN", "sr_variance >= 0");
    }
    let sr0 = if n_trials == 1 {
        0.0
    } else {
        let n = n_trials as f64;
        sr_variance.sqrt()
            * ((1.0 - EULER_GAMMA) * normal_inv(1.0 - 1.0 / n)
                + EULER_GAMMA * normal_inv(1.0 - 1.0 / (n * std::f64::consts::E)))
    };
    let (z, p) = psr(sr, n_obs, skew, kurtosis, sr0)?;
    Ok((pz(sr0), z, p))
}

#[derive(Debug, Clone, PartialEq)]
pub struct Power {
    pub z_sum: f64,
    pub mds: f64,
    pub se_at_zero: f64,
    pub target: Option<(f64, f64)>,
}

pub fn power(years: f64, alpha: f64, power: f64, sr_target: Option<f64>) -> Result<Power> {
    let unit = |x: f64| x > 0.0 && x < 1.0;
    if years <= 0.0
        || !unit(alpha)
        || !unit(power)
        || alpha >= power
        || sr_target.is_some_and(|s| s <= 0.0)
    {
        return fail(
            "E_DOMAIN",
            "years > 0, 0 < alpha < power < 1, sr_target > 0",
        );
    }
    let z_sum = normal_inv(1.0 - alpha) + normal_inv(power);
    Ok(Power {
        z_sum,
        mds: z_sum / years.sqrt(),
        se_at_zero: 1.0 / years.sqrt(),
        target: sr_target.map(|s| ((z_sum / s).powi(2), ((1.0 + s * s / 2.0) / years).sqrt())),
    })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Metric {
    Sharpe,
    Mean,
}

fn mean_sd(x: &[f64]) -> (f64, f64) {
    let n = x.len() as f64;
    let m = x.iter().sum::<f64>() / n;
    let v = x.iter().map(|v| (v - m).powi(2)).sum::<f64>() / (n - 1.0);
    (m, v.sqrt())
}

fn metric(x: &[f64], m: Metric) -> f64 {
    let (mu, sd) = mean_sd(x);
    match m {
        Metric::Mean => mu,
        Metric::Sharpe => mu / sd,
    }
}

/// Lexicographic combinations of `r` out of `0..n`.
fn combinations(n: usize, r: usize) -> Vec<Vec<usize>> {
    let mut out = Vec::new();
    let mut c: Vec<usize> = (0..r).collect();
    loop {
        out.push(c.clone());
        let Some(i) = (0..r).rev().find(|&i| c[i] != i + n - r) else {
            return out;
        };
        c[i] += 1;
        for j in i + 1..r {
            c[j] = c[j - 1] + 1;
        }
    }
}

/// `(pbo, logits)` by CSCV.
pub fn pbo(perf: &[Vec<f64>], s: i64, m: Metric) -> Result<(f64, Vec<f64>)> {
    let t = perf.len();
    let n = perf.first().map_or(0, Vec::len);
    if n < 2
        || perf.iter().any(|r| r.len() != n)
        || s < 2
        || s % 2 != 0
        || t % (s as usize) != 0
        || t / (s as usize) < 2
    {
        return fail(
            "E_INPUT",
            "N >= 2 equal rows; S even, 2 <= S, T divisible by S, >= 2 rows per block",
        );
    }
    let s = s as usize;
    let rows = t / s;
    let col = |idx: &[usize], j: usize| -> Vec<f64> {
        idx.iter()
            .flat_map(|&b| (b * rows..(b + 1) * rows).map(move |r| r))
            .map(|r| perf[r][j])
            .collect()
    };
    if m == Metric::Sharpe {
        for b in 0..s {
            for j in 0..n {
                if mean_sd(&col(&[b], j)).1 == 0.0 {
                    return fail("E_DOMAIN", "a block has zero standard deviation");
                }
            }
        }
    }
    let mut logits = Vec::new();
    for train in combinations(s, s / 2) {
        let test: Vec<usize> = (0..s).filter(|b| !train.contains(b)).collect();
        let tr: Vec<f64> = (0..n).map(|j| metric(&col(&train, j), m)).collect();
        let te: Vec<f64> = (0..n).map(|j| metric(&col(&test, j), m)).collect();
        let mut best = 0;
        for j in 1..n {
            if tr[j] > tr[best] {
                best = j;
            }
        }
        let x = te[best];
        let below = te.iter().filter(|&&v| v < x).count() as f64;
        let equal = te.iter().filter(|&&v| v == x).count() as f64;
        let r = below + (equal + 1.0) / 2.0;
        let omega = r / (n as f64 + 1.0);
        logits.push(pz((omega / (1.0 - omega)).ln()));
    }
    let p = logits.iter().filter(|&&l| l <= 0.0).count() as f64 / logits.len() as f64;
    Ok((p, logits))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A small deterministic generator for the property tests.
    struct Lcg(u64);
    impl Lcg {
        fn next(&mut self) -> f64 {
            self.0 = self
                .0
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(1_442_695_040_888_963_407);
            (self.0 >> 11) as f64 / (1u64 << 53) as f64
        }
        fn normal(&mut self) -> f64 {
            let (u, v) = (self.next().max(1e-300), self.next());
            (-2.0 * u.ln()).sqrt() * (2.0 * std::f64::consts::PI * v).cos()
        }
    }

    fn walk(g: &mut Lcg, t: usize) -> Vec<f64> {
        let mut p = vec![100.0];
        for _ in 1..t {
            let last = *p.last().unwrap();
            p.push(last * (0.01 * g.normal()).exp());
        }
        p
    }

    const ZERO: Costs = Costs {
        half_spread_bps: 0.0,
        commission_per_unit: 0.0,
        fixed_per_trade: 0.0,
        multiplier: 1.0,
    };

    fn close(a: f64, b: f64, tol: f64) -> bool {
        (a - b).abs() <= tol * a.abs().max(b.abs()).max(1.0)
    }

    #[test]
    fn event_equals_vector_and_attribution_closes() {
        let mut g = Lcg(7);
        for case in 0..50 {
            let t = 2 + case % 40;
            let p = walk(&mut g, t);
            let q: Vec<f64> = (0..t).map(|_| (g.next() * 7.0).floor() - 3.0).collect();
            let c = Costs {
                half_spread_bps: g.next() * 10.0,
                commission_per_unit: g.next() * 0.05,
                fixed_per_trade: g.next(),
                multiplier: 1.0 + g.next() * 9.0,
            };
            let lag = (case % t) as i64;
            let a = backtest(&p, &q, lag, c, Engine::Event).unwrap();
            let b = backtest(&p, &q, lag, c, Engine::Vector).unwrap();
            for (x, y) in a
                .equity
                .iter()
                .zip(&b.equity)
                .chain(a.pnl_net.iter().zip(&b.pnl_net))
            {
                assert!(close(*x, *y, 1e-10));
            }
            assert!(close(a.total_net, b.total_net, 1e-10));
            assert!(close(a.max_drawdown, b.max_drawdown, 1e-10));
            assert_eq!(a.trade_count, b.trade_count);
            let largest = [
                a.total_gross,
                a.total_spread_cost,
                a.total_commission,
                a.total_fixed_cost,
            ]
            .iter()
            .fold(0.0_f64, |m, v| m.max(v.abs()));
            let lhs = a.total_gross - a.total_spread_cost - a.total_commission - a.total_fixed_cost;
            assert!((lhs - a.total_net).abs() <= 1e-12 * largest.max(1.0));
        }
    }

    #[test]
    fn zero_costs_and_doubling() {
        let mut g = Lcg(11);
        let p = walk(&mut g, 60);
        let q: Vec<f64> = (0..60).map(|_| (g.next() * 5.0).floor() - 2.0).collect();
        let a = backtest(&p, &q, 1, ZERO, Engine::Event).unwrap();
        assert_eq!(a.pnl_net, a.pnl_gross);
        let c = Costs {
            half_spread_bps: 3.0,
            commission_per_unit: 0.02,
            fixed_per_trade: 0.5,
            multiplier: 2.0,
        };
        let c2 = Costs {
            half_spread_bps: 6.0,
            commission_per_unit: 0.04,
            fixed_per_trade: 1.0,
            ..c
        };
        let (x, y) = (
            backtest(&p, &q, 1, c, Engine::Event).unwrap(),
            backtest(&p, &q, 1, c2, Engine::Event).unwrap(),
        );
        assert_eq!(2.0 * x.total_spread_cost, y.total_spread_cost);
        assert_eq!(2.0 * x.total_commission, y.total_commission);
        assert_eq!(2.0 * x.total_fixed_cost, y.total_fixed_cost);
    }

    #[test]
    fn look_ahead_canary() {
        let mut g = Lcg(3);
        let t = 2000;
        let p = walk(&mut g, t);
        // Decided at t with knowledge of p_{t+1}; shifted one bar so lag 0 holds it over the move.
        let mut q = vec![0.0; t];
        for k in 1..t {
            q[k - 1] = (p[k] - p[k - 1]).signum();
        }
        let peek = q;
        let at0 = backtest(&p, &peek, 0, ZERO, Engine::Event)
            .unwrap()
            .total_gross;
        let at1 = backtest(&p, &peek, 1, ZERO, Engine::Event)
            .unwrap()
            .total_gross;
        let scale: f64 = p.windows(2).map(|w| (w[1] - w[0]).abs()).sum();
        assert!(at0 > 0.9 * scale, "canary detected at lag 0");
        assert!(at1.abs() < 0.2 * scale, "no edge at lag 1");
    }

    #[test]
    fn purged_train_never_overlaps_and_plain_kfold() {
        let mut g = Lcg(5);
        for case in 0..40 {
            let n = 5 + case;
            let mut t0 = Vec::new();
            let mut x = 0.0;
            for _ in 0..n {
                x += (g.next() * 3.0).floor();
                t0.push(x);
            }
            let t1: Vec<f64> = t0.iter().map(|v| v + (g.next() * 5.0).floor()).collect();
            let k = 2 + (case % (n - 1)).min(6) as i64;
            let (folds, _) = purged_kfold(&t0, &t1, k, 0.05).unwrap();
            for f in &folds {
                let lo = t0[f.test[0]];
                let hi = f.test.iter().map(|&i| t1[i]).fold(f64::MIN, f64::max);
                assert!(f.train.iter().all(|&j| !(t0[j] <= hi && t1[j] >= lo)));
            }
            let plain = purged_kfold(&t0, &t0, k, 0.0).unwrap().0;
            let distinct = t0.windows(2).all(|w| w[0] < w[1]);
            if distinct {
                for f in &plain {
                    let want: Vec<usize> = (0..n).filter(|i| !f.test.contains(i)).collect();
                    assert_eq!(f.train, want);
                }
            }
        }
    }

    fn brute(init: &[f64], a: &[Vec<f64>], e: &[Vec<f64>]) -> (Vec<usize>, f64) {
        let (k, t) = (init.len(), e.len());
        let mut best = (vec![], f64::NEG_INFINITY);
        for code in 0..k.pow(t as u32) {
            let s: Vec<usize> = (0..t).map(|i| code / k.pow(i as u32) % k).collect();
            let mut lp = init[s[0]].ln() + e[0][s[0]].ln();
            for i in 1..t {
                lp += a[s[i - 1]][s[i]].ln() + e[i][s[i]].ln();
            }
            if lp > best.1 {
                best = (s, lp);
            }
        }
        best
    }

    #[test]
    fn viterbi_equals_brute_force() {
        let mut g = Lcg(9);
        let mut row = |g: &mut Lcg, k: usize| {
            let v: Vec<f64> = (0..k).map(|_| 0.05 + g.next()).collect();
            let s: f64 = v.iter().sum();
            v.into_iter().map(|x| x / s).collect::<Vec<f64>>()
        };
        for case in 0..200 {
            let k = 1 + case % 3;
            let t = 1 + case % 6;
            let init = row(&mut g, k);
            let a: Vec<Vec<f64>> = (0..k).map(|_| row(&mut g, k)).collect();
            let e: Vec<Vec<f64>> = (0..t).map(|_| (0..k).map(|_| g.next()).collect()).collect();
            let (s, lp) = regime_viterbi(&init, &a, Some(&e), None).unwrap();
            let (bs, blp) = brute(&init, &a, &e);
            assert!(close(lp, blp, 1e-12));
            assert_eq!(s, bs);
        }
    }

    #[test]
    fn viterbi_ties_take_smallest_index() {
        let init = [0.5, 0.5];
        let a = vec![vec![0.5, 0.5], vec![0.5, 0.5]];
        let e = vec![vec![0.3, 0.3]; 3];
        assert_eq!(
            regime_viterbi(&init, &a, Some(&e), None).unwrap().0,
            vec![0, 0, 0]
        );
    }

    #[test]
    fn dsr_monotone_and_psr_half() {
        let mut last = 1.0;
        for n in [1, 2, 5, 10, 100, 1000] {
            let d = dsr(0.1, 1000, -0.5, 5.0, n, 0.002).unwrap().2;
            assert!(d <= last);
            last = d;
        }
        let mut last = 1.0;
        for v in [0.0, 0.001, 0.002, 0.01] {
            let d = dsr(0.1, 1000, -0.5, 5.0, 50, v).unwrap().2;
            assert!(d <= last);
            last = d;
        }
        assert_eq!(psr(0.13, 500, 0.3, 4.0, 0.13).unwrap().1, 0.5);
    }

    #[test]
    fn pbo_bounds_and_dominance() {
        let mut g = Lcg(13);
        for _ in 0..20 {
            let perf: Vec<Vec<f64>> = (0..24)
                .map(|_| (0..5).map(|_| g.normal()).collect())
                .collect();
            let (p, l) = pbo(&perf, 6, Metric::Sharpe).unwrap();
            assert!((0.0..=1.0).contains(&p));
            assert_eq!(l.len(), 20);
            let dom: Vec<Vec<f64>> = perf
                .iter()
                .map(|r| {
                    let mut r = r.clone();
                    r[2] = r.iter().fold(f64::MIN, |m, v| m.max(*v)) + 1.0 + g.next();
                    r
                })
                .collect();
            assert_eq!(pbo(&dom, 6, Metric::Mean).unwrap().0, 0.0);
        }
    }

    #[test]
    fn cpcv_counts() {
        assert_eq!(cpcv_paths(6, 2).unwrap(), (15, 5));
        assert_eq!(cpcv_paths(64, 32).unwrap().0, 1_832_624_140_942_590_534);
    }
}
