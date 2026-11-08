//! VIX-style index from a given option strip (`05-volatility/vix-index.md`, rulings E-B5, E-B6).
use crate::error::{Result, fail};

const N30: f64 = 43_200.0;
const N365: f64 = 525_600.0;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Quote {
    pub strike: f64,
    pub call_bid: f64,
    pub call_ask: f64,
    pub put_bid: f64,
    pub put_ask: f64,
}

impl Quote {
    fn call_mid(&self) -> f64 {
        (self.call_bid + self.call_ask) / 2.0
    }
    fn put_mid(&self) -> f64 {
        (self.put_bid + self.put_ask) / 2.0
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Term {
    pub forward: f64,
    pub k0: f64,
    pub variance: f64,
    pub strikes_used: Vec<f64>,
    pub t: f64,
}

/// Selected out-of-the-money strikes walking away from `k0` (exclusive), with their quote:
/// a zero bid is skipped, and the second consecutive zero bid stops the walk.
fn walk<'a>(
    side: impl Iterator<Item = &'a Quote>,
    bid: fn(&Quote) -> f64,
    mid: fn(&Quote) -> f64,
) -> Vec<(f64, f64)> {
    let (mut out, mut zeros) = (Vec::new(), 0);
    for q in side {
        if bid(q) == 0.0 {
            zeros += 1;
            if zeros == 2 {
                break;
            }
            continue;
        }
        zeros = 0;
        out.push((q.strike, mid(q)));
    }
    out
}

pub fn term_variance(minutes: i64, rate: f64, strip: &[Quote]) -> Result<Term> {
    if minutes < 1 {
        return fail("E_INPUT", "minutes_to_expiry must be at least 1");
    }
    let mut s = strip.to_vec();
    s.sort_by(|a, b| a.strike.total_cmp(&b.strike));
    if s.len() < 3 || s.windows(2).any(|w| w[0].strike == w[1].strike) {
        return fail("E_INPUT", "need at least 3 distinct strikes");
    }
    if s.iter()
        .any(|q| q.call_bid > q.call_ask || q.put_bid > q.put_ask)
    {
        return fail("E_INPUT", "a bid is above its ask");
    }
    let quotes = |q: &Quote| [q.call_bid, q.call_ask, q.put_bid, q.put_ask];
    if s.iter()
        .any(|q| quotes(q).iter().any(|v| v.is_nan() || *v < 0.0))
    {
        return fail("E_DOMAIN", "quotes must not be negative");
    }
    let t = minutes as f64 / N365;
    let growth = (rate * t).exp();
    let mut star = &s[0];
    for q in &s[1..] {
        if (q.call_mid() - q.put_mid()).abs() < (star.call_mid() - star.put_mid()).abs() {
            star = q;
        }
    }
    let forward = star.strike + growth * (star.call_mid() - star.put_mid());
    let Some(i0) = s.iter().rposition(|q| q.strike <= forward) else {
        return fail("E_INPUT", "no strike at or below the forward");
    };
    let k0 = s[i0].strike;
    let mut used = walk(s[..i0].iter().rev(), |q| q.put_bid, Quote::put_mid);
    used.reverse();
    used.push((k0, (s[i0].call_mid() + s[i0].put_mid()) / 2.0));
    used.extend(walk(s[i0 + 1..].iter(), |q| q.call_bid, Quote::call_mid));
    let k: Vec<f64> = used.iter().map(|u| u.0).collect();
    let n = k.len();
    let gap = |i: usize| match (i, n) {
        (_, 1) => 0.0,
        (0, _) => k[1] - k[0],
        (i, n) if i == n - 1 => k[i] - k[i - 1],
        (i, _) => (k[i + 1] - k[i - 1]) / 2.0,
    };
    let sum: f64 = used
        .iter()
        .enumerate()
        .map(|(i, &(ki, q))| gap(i) / (ki * ki) * q)
        .sum();
    let variance = 2.0 / t * growth * sum - (forward / k0 - 1.0).powi(2) / t;
    Ok(Term {
        forward,
        k0,
        variance,
        strikes_used: k,
        t,
    })
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Index {
    pub index: f64,
    pub near_variance: f64,
    pub next_variance: f64,
}

/// Interpolates to 30 days with no extrapolation (ruling E-B6). The bracket rule is checked
/// before either term is built.
pub fn index(near: (i64, f64, &[Quote]), next: (i64, f64, &[Quote])) -> Result<Index> {
    let (n1, n2) = (near.0 as f64, next.0 as f64);
    if !(near.0 < next.0 && n1 <= N30 && N30 <= n2) {
        return fail(
            "E_INPUT",
            "terms must satisfy N1 < N2 and N1 <= 43200 <= N2",
        );
    }
    let a = term_variance(near.0, near.1, near.2)?;
    let b = term_variance(next.0, next.1, next.2)?;
    let bracket = (a.t * a.variance * (n2 - N30) / (n2 - n1)
        + b.t * b.variance * (N30 - n1) / (n2 - n1))
        * N365
        / N30;
    if bracket.is_nan() || bracket < 0.0 {
        return fail("E_DOMAIN", "negative variance in time");
    }
    Ok(Index {
        index: 100.0 * bracket.sqrt(),
        near_variance: a.variance,
        next_variance: b.variance,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn q(strike: f64, cb: f64, ca: f64, pb: f64, pa: f64) -> Quote {
        Quote {
            strike,
            call_bid: cb,
            call_ask: ca,
            put_bid: pb,
            put_ask: pa,
        }
    }

    fn example() -> Vec<Quote> {
        vec![
            q(110.0, 0.3, 0.5, 10.0, 11.0),
            q(90.0, 10.5, 11.5, 0.5, 0.7),
            q(95.0, 6.0, 6.6, 1.4, 1.6),
            q(100.0, 2.9, 3.1, 2.9, 3.3),
            q(105.0, 1.0, 1.2, 5.8, 6.6),
        ]
    }

    #[test]
    fn worked_example() {
        let t = term_variance(43_200, 0.0, &example()).unwrap();
        assert!((t.forward - 99.9).abs() < 1e-12);
        assert_eq!(t.k0, 95.0);
        assert_eq!(t.strikes_used, vec![90.0, 95.0, 100.0, 105.0, 110.0]);
        assert!((t.variance - 0.0818816).abs() < 1e-7);
        let i = index((43_200, 0.0, &example()), (43_200 * 2, 0.0, &example())).unwrap();
        assert!((i.index - 100.0 * t.variance.sqrt()).abs() < 1e-12);
    }

    #[test]
    fn zero_bids_skip_then_stop() {
        let mut s = example();
        s.push(q(85.0, 15.0, 16.0, 0.0, 0.1));
        s.push(q(80.0, 20.0, 21.0, 0.05, 0.1));
        s.push(q(75.0, 25.0, 26.0, 0.0, 0.05));
        s.push(q(70.0, 30.0, 31.0, 0.0, 0.05));
        s.push(q(65.0, 35.0, 36.0, 0.05, 0.1));
        let t = term_variance(43_200, 0.01, &s).unwrap();
        assert_eq!(t.strikes_used, vec![80.0, 90.0, 95.0, 100.0, 105.0, 110.0]);
    }

    #[test]
    fn checks() {
        let e = example();
        let code = |r: Result<Term>| r.unwrap_err().code;
        assert_eq!(code(term_variance(0, 0.0, &e)), "E_INPUT");
        assert_eq!(code(term_variance(10, 0.0, &e[..2])), "E_INPUT");
        let mut d = e.clone();
        d[0].strike = 90.0;
        assert_eq!(code(term_variance(10, 0.0, &d)), "E_INPUT");
        let mut b = e.clone();
        b[0].call_bid = 1.0;
        assert_eq!(code(term_variance(10, 0.0, &b)), "E_INPUT");
        let mut n = e.clone();
        n[0].put_bid = -1.0;
        assert_eq!(code(term_variance(10, 0.0, &n)), "E_DOMAIN");
        let mut low = e.clone();
        for x in &mut low {
            x.call_bid += 50.0;
            x.call_ask += 50.0;
        }
        assert!(term_variance(10, 0.0, &low).is_ok());
        let mut high = e;
        for x in &mut high {
            x.put_bid += 50.0;
            x.put_ask += 50.0;
        }
        assert_eq!(code(term_variance(10, 0.0, &high)), "E_INPUT");
        let s = example();
        let bad = index((43_300, 0.0, &s), (50_000, 0.0, &s)).unwrap_err();
        assert_eq!(bad.code, "E_INPUT");
        assert_eq!(
            index((40_000, 0.0, &s), (40_000, 0.0, &s))
                .unwrap_err()
                .code,
            "E_INPUT"
        );
    }
}
