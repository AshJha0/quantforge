//! The seven planted-recovery tests and the 200-seed coverage run, exactly as
//! `specifications/09-microstructure/micro-estimators.md` fixes them (HR-70, HR-71): draws from
//! `numpy.random.default_rng(seed)` (ported in `numpy_rng`) in the listed order; pass within 3 SE;
//! seed 20261118 + j for test j; seeds 70000..70199 with at most 4 misses. As the streams are
//! numpy's, the misses must be the Python and Java builds' own (70075 test 1, 70190 test 4, 70028
//! test 7). Also checks the port draw by draw against the values numpy printed (as the Java lane's
//! `NumpyRngTest`).
#![allow(clippy::unwrap_used, clippy::type_complexity)]
mod numpy_rng;

use numpy_rng::{NumpyRng, loggam};
use quantforge_core::micro_est::{self as me, Estimate, Sample};
use quantforge_core::research_w3::fsum;

fn hit(e: Estimate, truth: f64) -> bool {
    (e.value - truth).abs() <= 3.0 * e.se
}

fn impact(rng: &mut NumpyRng, lam: f64, n: usize) -> Sample {
    let (mut x, mut y) = (Vec::with_capacity(n), Vec::with_capacity(n));
    for _ in 0..n {
        let s = rng.choice(&[-1, 1]) as f64;
        let q = rng.integers(1, 101) as f64;
        let e = rng.normal(0.0, 0.05);
        x.push(s * q);
        y.push(lam * s * q + e);
    }
    Sample { x, y }
}

fn r1(rng: &mut NumpyRng) -> bool {
    let (lam, t) = (2.5, 3600.0);
    hit(me::arrival_rate(rng.poisson(lam * t), t).unwrap(), lam)
}

fn r2(rng: &mut NumpyRng) -> bool {
    let (theta, fill) = (0.4, 0.1);
    let rows: Vec<(f64, bool)> = (0..5000)
        .map(|_| {
            let life = rng.exponential(1.0 / (theta + fill));
            (life, rng.random() < theta / (theta + fill))
        })
        .collect();
    hit(me::cancel_rate(&rows).unwrap(), theta)
}

fn r3(rng: &mut NumpyRng) -> bool {
    let (kappa, s0, sinf) = (0.3, 5.0, 1.0);
    let pts: Vec<(f64, f64)> = (0..=20)
        .map(|t| {
            let t = f64::from(t);
            (
                t,
                sinf + (s0 - sinf) * (-kappa * t).exp() * rng.normal(0.0, 0.05).exp(),
            )
        })
        .collect();
    hit(me::resilience(sinf, &pts).unwrap(), kappa)
}

fn r4(rng: &mut NumpyRng) -> bool {
    let (alpha, d0) = (0.15, 1000.0);
    let lv: Vec<(f64, f64)> = (0..=30)
        .map(|k| {
            let k = f64::from(k);
            (k, d0 * (-alpha * k).exp() * rng.normal(0.0, 0.1).exp())
        })
        .collect();
    hit(me::liquidity_decay(&lv).unwrap(), alpha)
}

fn r5(rng: &mut NumpyRng) -> bool {
    let s = impact(rng, 0.002, 2000);
    hit(me::adverse_selection(&s.x, &s.y).unwrap(), 0.002)
}

fn r6(rng: &mut NumpyRng) -> bool {
    let calm = impact(rng, 0.001, 1000);
    let stressed = impact(rng, 0.004, 1000);
    let (r, _) =
        me::regime_impact(&[("calm".into(), calm), ("stressed".into(), stressed)]).unwrap();
    hit(r[0].1, 0.001) && hit(r[1].1, 0.004)
}

fn r7(rng: &mut NumpyRng) -> bool {
    let passive: Vec<f64> = (0..1000).map(|_| rng.normal(-1.0, 2.0)).collect();
    let aggressive: Vec<f64> = (0..1000).map(|_| rng.normal(1.5, 2.0)).collect();
    hit(
        me::passive_vs_aggressive(&passive, &aggressive).unwrap(),
        2.5,
    )
}

const RECOVERY: [fn(&mut NumpyRng) -> bool; 7] = [r1, r2, r3, r4, r5, r6, r7];

/// The Python build's coverage-run misses per test (`python/tests/test_stage_h_micro.py`).
const PYTHON_MISSES: [&[u32]; 7] = [&[70075], &[], &[], &[70190], &[], &[], &[70028]];

#[test]
fn single_seed_recovery() {
    for (j, f) in RECOVERY.iter().enumerate() {
        let seed = 20261118 + j as u32 + 1;
        assert!(f(&mut NumpyRng::new(seed)), "test {} seed {seed}", j + 1);
    }
}

#[test]
fn coverage_misses_match_python_and_java() {
    for (j, f) in RECOVERY.iter().enumerate() {
        let misses: Vec<u32> = (70000..70200)
            .filter(|&s| !f(&mut NumpyRng::new(s)))
            .collect();
        assert!(misses.len() <= 4, "test {}: {misses:?}", j + 1);
        assert_eq!(misses, PYTHON_MISSES[j], "test {}", j + 1);
    }
}

/// Values numpy printed (as in the Java `NumpyRngTest`): the first draws of three seeds in the
/// order the recovery tests interleave them, and two PTRS Poisson draws after 3,000 rounds.
#[test]
fn first_draws_match_numpy() {
    let want: [(u32, u64, f64, i64, i64, f64, f64, i64, i64); 3] = [
        (
            20261119,
            1684628720167899607,
            0.29071362979956594,
            -1,
            58,
            -0.06724342672535288,
            2.7156780461168064,
            9010,
            9077,
        ),
        (
            70000,
            6024274701318062869,
            0.4008755151155149,
            1,
            93,
            0.01077855715010661,
            6.522768631588426,
            8887,
            9109,
        ),
        (
            70123,
            7416423396052956773,
            0.11062102713738753,
            -1,
            39,
            0.017782774812657554,
            0.7215412971042601,
            8924,
            9023,
        ),
    ];
    for w in want {
        let mut r = NumpyRng::new(w.0);
        assert_eq!(r.next_u64(), w.1);
        assert_eq!(r.random(), w.2);
        assert_eq!(r.choice(&[-1, 1]), w.3);
        assert_eq!(r.integers(1, 101), w.4);
        assert_eq!(r.normal(0.0, 0.05), w.5);
        assert_eq!(r.exponential(2.0), w.6);
        for _ in 1..3000 {
            r.choice(&[-1, 1]);
            r.integers(1, 101);
            r.normal(0.0, 0.05);
            r.exponential(2.0);
        }
        assert_eq!(r.poisson(9000.0), w.7);
        assert_eq!(r.poisson(9000.0), w.8);
    }
}

/// A 200,000-draw ziggurat checksum (`math.fsum` in numpy's run).
#[test]
fn ziggurat_checksum() {
    let mut r = NumpyRng::new(70000);
    let mut v: Vec<f64> = (0..100_000).map(|_| r.standard_normal()).collect();
    v.extend((0..100_000).map(|_| r.standard_exponential()));
    assert_eq!(fsum(v.iter().copied()), 100216.18527592497);
    assert_eq!(v[199_999], 1.4622581364761265);
}

#[test]
fn guards() {
    assert_eq!(NumpyRng::new(1).integers(7, 8), 7);
    assert_eq!(loggam(1.0), 0.0);
    assert_eq!(loggam(2.0), 0.0);
    assert!((loggam(4.0) - 6f64.ln()).abs() < 1e-14);
    assert!(std::panic::catch_unwind(|| NumpyRng::new(1).poisson(5.0)).is_err());
}
