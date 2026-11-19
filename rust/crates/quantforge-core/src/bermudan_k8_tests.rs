//! K-8 `CN_RANNACHER_SMOOTHED` (KR-8 as revised by KR-18): a port of java25 `BermudanK8Test` and the
//! k8 tests of `python/tests/test_stage_k_w1.py`. The Python build's values on a small grid, the
//! tangent ladder against its own bumps at 1e-8 relative on the same grid (acceptance 5), the
//! smoothing of spec step 5, exact zeros, time order 2 and space error smooth at second order.
//! Acceptance 3 (201/401/801, `QF_K8_ACCEPTANCE=1`) is the integration test
//! `tests/k8_acceptance.rs`. The shared goldens `k8_k` run in the CLI crate's golden replay.
use super::*;
use crate::json::{Json, parse};
use crate::stage_k::richardson_check;

fn repo(rel: &str) -> Json {
    let path = format!("{}/../../../{rel}", env!("CARGO_MANIFEST_DIR"));
    parse(&std::fs::read_to_string(path).unwrap()).unwrap().0
}

fn reals(v: &Json) -> Vec<f64> {
    v.as_array()
        .unwrap()
        .iter()
        .map(|x| x.as_f64().unwrap())
        .collect()
}

struct Case {
    start: f64,
    times: Vec<f64>,
    dfs: Vec<f64>,
    a: f64,
    sigma: f64,
    pay: Vec<f64>,
    rate: f64,
    payer: bool,
    notional: f64,
    exercise: Vec<f64>,
    width: f64,
}

fn ladder_case(index: usize) -> Case {
    let doc = repo("datasets/golden/stage_g/aadladder_g.json");
    let i = doc.get("cases").unwrap().as_array().unwrap()[index]
        .get("inputs")
        .unwrap();
    let c = i.get("curve").unwrap();
    let f = |k: &str| i.get(k).unwrap().as_f64().unwrap();
    Case {
        start: f("start_years"),
        times: reals(c.get("times").unwrap()),
        dfs: reals(c.get("discount_factors").unwrap()),
        a: f("mean_reversion"),
        sigma: f("sigma"),
        pay: reals(i.get("payment_times").unwrap()),
        rate: f("fixed_rate"),
        payer: i.get("swaption_type").unwrap().as_str() == Some("PAYER"),
        notional: f("notional"),
        exercise: reals(i.get("exercise_times").unwrap()),
        width: i
            .get("grid")
            .unwrap()
            .get("width")
            .unwrap()
            .as_f64()
            .unwrap(),
    }
}

fn grid(c: &Case, nx: i64, spy: i64) -> FdGrid {
    FdGrid {
        nx,
        steps_per_year: spy,
        width: c.width,
    }
}

fn swap(c: &Case) -> SwapLeg<'_> {
    SwapLeg {
        start: c.start,
        pay: &c.pay,
        fixed_rate: c.rate,
        payer: c.payer,
        notional: c.notional,
    }
}

fn ladder_of(c: &Case, nx: i64, spy: i64) -> Ladder {
    let curve = HwCurve::new(&c.times, &c.dfs).unwrap();
    ladder(
        &curve,
        &c.times,
        &c.dfs,
        c.a,
        c.sigma,
        &swap(c),
        &c.exercise,
        grid(c, nx, spy),
    )
    .unwrap()
}

fn price_of(c: &Case, dfs: &[f64], a: f64, s: f64, nx: i64, spy: i64) -> f64 {
    let curve = HwCurve::new(&c.times, dfs).unwrap();
    price(
        &curve,
        &c.times,
        dfs,
        a,
        s,
        &swap(c),
        &c.exercise,
        grid(c, nx, spy),
    )
    .unwrap()
}

fn row(l: &Ladder) -> Vec<f64> {
    let mut r = vec![l.price];
    r.extend_from_slice(&l.d_discount_factors);
    r.push(l.d_mean_reversion);
    r.push(l.d_sigma);
    r
}

fn max_abs(v: &[f64]) -> f64 {
    v.iter().fold(0.0, |m, x| m.max(x.abs()))
}

fn bump(f: impl Fn(f64) -> f64, x: f64, step: f64) -> f64 {
    let d1 = (f(x + step) - f(x - step)) / (2.0 * step);
    let d2 = (f(x + step / 2.0) - f(x - step / 2.0)) / step;
    (4.0 * d2 - d1) / 3.0
}

/// Python `bermudan_k8.bermudan_ladder` (spec 0.2.0) on the aadladder_g-0001..0003 inputs, grid
/// 41/20 (2026-11-19); the same rows as `BermudanK8Test.PYTHON_41_20`.
const PYTHON_41_20: [[f64; 13]; 3] = [
    [
        22287.53461841767,
        0.0,
        211358.63631459567,
        162687.8910175668,
        139306.3793174654,
        -231877.5339021703,
        -347142.401546213,
        0.0,
        0.0,
        0.0,
        0.0,
        -50599.24923667921,
        2228993.5084961606,
    ],
    [
        14219.03198224864,
        0.0,
        90811.61296827145,
        131329.76588168432,
        150157.18125350963,
        -142268.28751103743,
        -277083.57865698315,
        0.0,
        0.0,
        0.0,
        0.0,
        -49394.77704993134,
        2086503.2182632545,
    ],
    [
        13716.96718870294,
        0.0,
        -85323.69457718439,
        -129308.55315145763,
        -138026.26813797135,
        154928.16366504165,
        276491.2939629992,
        0.0,
        0.0,
        0.0,
        0.0,
        -48789.9281811259,
        2034661.6889618998,
    ],
];

#[test]
fn matches_python_on_small_grid() {
    for (k, want) in PYTHON_41_20.iter().enumerate() {
        let c = ladder_case(k);
        let got = row(&ladder_of(&c, 41, 20));
        let scale = max_abs(want);
        for j in 0..got.len() {
            assert!(
                (got[j] - want[j]).abs() <= 1e-10 * scale,
                "{k}/{j}: {} vs {}",
                got[j],
                want[j]
            );
        }
        let p = price_of(&c, &c.dfs, c.a, c.sigma, 41, 20);
        assert!((got[0] - p).abs() <= 1e-9 * got[0].abs());
    }
}

#[test]
fn ladder_equals_its_own_bumps() {
    let c = ladder_case(1);
    let l = ladder_of(&c, 41, 20);
    let scale = max_abs(&l.d_discount_factors);
    for j in 0..c.dfs.len() {
        let got = bump(
            |x| {
                let mut d = c.dfs.clone();
                d[j] = x;
                price_of(&c, &d, c.a, c.sigma, 41, 20)
            },
            c.dfs[j],
            1e-4 * c.dfs[j],
        );
        assert!(
            (got - l.d_discount_factors[j]).abs() <= 1e-8 * scale,
            "{j}: {got}"
        );
    }
    let ga = bump(
        |x| price_of(&c, &c.dfs, x, c.sigma, 41, 20),
        c.a,
        1e-3 * c.a,
    );
    assert!(
        (ga - l.d_mean_reversion).abs() <= 1e-8 * ga.abs(),
        "a: {ga}"
    );
    let gs = bump(
        |x| price_of(&c, &c.dfs, c.a, x, 41, 20),
        c.sigma,
        1e-3 * c.sigma,
    );
    assert!((gs - l.d_sigma).abs() <= 1e-8 * gs.abs(), "sigma: {gs}");
}

#[test]
fn smoothing_worked_example() {
    let v = vec![vec![0.0]; 3];
    let got = smoothed_max(&v, &[vec![1.0], vec![0.0], vec![-1.0]]);
    assert_eq!(got[0][0], 1.0);
    assert!((got[1][0] - 1.0 / 18.0).abs() <= 1e-16);
    assert_eq!(got[2][0], 0.0);
    let mirror = smoothed_max(&v, &[vec![-1.0], vec![0.0], vec![1.0]]);
    assert_eq!(mirror[0][0], 0.0);
    assert!((mirror[1][0] - 1.0 / 18.0).abs() <= 1e-16);
    assert_eq!(mirror[2][0], 1.0);
}

#[test]
fn hat_part_closed_form() {
    let cases = [
        (1.0, 2.0),
        (1.0, -0.5),
        (-0.5, 1.0),
        (-1.0, -2.0),
        (0.0, 1.0),
        (1.0, 0.0),
        (0.0, -1.0),
    ];
    let n = 200_000;
    for (p, q) in cases {
        let mut want = 0.0;
        for i in 0..n {
            let u = (f64::from(i) + 0.5) / f64::from(n);
            want += (1.0 - u) * (p + (q - p) * u).max(0.0);
        }
        want /= f64::from(n);
        let got = hat_part(&[p], &[q])[0];
        assert!((want - got).abs() <= 1e-9, "{p},{q}");
    }
}

#[test]
fn smoothing_keeps_the_pointwise_max_away_from_the_crossing() {
    let n = 41;
    let mut v = vec![vec![0.0]; n];
    let mut f = vec![0.0; n];
    let mut j = usize::MAX;
    for i in 0..n {
        let x = -1.0 + 2.0 * i as f64 / (n - 1) as f64;
        f[i] = (x - 0.013) * (1.0 + 0.3 * x + 0.2 * x * x);
        v[i][0] = f[i];
        if j == usize::MAX && f[i] > 0.0 {
            j = i;
        }
    }
    let got = smoothed_max(&v, &vec![vec![0.0]; n]);
    for i in 0..n - 2 {
        if i >= j + 2 {
            assert!((got[i][0] - f[i]).abs() <= 1e-14, "node {i}");
        } else if i + 2 < j {
            assert_eq!(got[i][0], 0.0, "node {i}");
        } else {
            assert_ne!(got[i][0], f[i].max(0.0), "node {i}");
        }
    }
}

/// KR-18 a: curve nodes the price does not depend on (0.4986 years, and those after the last
/// payment) give exactly 0.
#[test]
fn curve_nodes_the_price_does_not_depend_on_give_exact_zeros() {
    for index in 0..3 {
        let d = ladder_of(&ladder_case(index), 41, 20).d_discount_factors;
        for (k, x) in d.iter().enumerate() {
            assert_eq!(k == 0 || k >= 6, *x == 0.0, "{index}/{k}");
        }
    }
}

#[test]
fn time_order_is_two_on_every_entry() {
    let c = ladder_case(0);
    let rows: Vec<Vec<f64>> = [10, 20, 40]
        .iter()
        .map(|s| row(&ladder_of(&c, 41, *s)))
        .collect();
    for k in [0, 2, 3, 4, 5, 6, 11, 12] {
        let rc = richardson_check(&[rows[0][k], rows[1][k], rows[2][k]], 2.0, 2.0).unwrap();
        assert_eq!(rc.status, "OK", "entry {k}");
        assert!((rc.observed_order.unwrap() - 2.0).abs() <= 0.1, "entry {k}");
    }
}

#[test]
fn space_error_is_smooth_second_order() {
    let c = ladder_case(0);
    let reference = row(&ladder_of(&c, 321, 20));
    let grids = [61_i64, 81, 101, 131, 161];
    let judged = [0, 2, 3, 4, 5, 6, 11, 12];
    let scaled: Vec<Vec<f64>> = grids
        .iter()
        .map(|nx| {
            let r = row(&ladder_of(&c, *nx, 20));
            let c2 = ((nx - 1) * (nx - 1)) as f64;
            judged
                .iter()
                .map(|q| (r[*q] - reference[*q]) * c2 / (1.0 - c2 / (320.0 * 320.0)))
                .collect()
        })
        .collect();
    for q in 0..judged.len() {
        let mean = scaled.iter().map(|s| s[q]).sum::<f64>() / scaled.len() as f64;
        for s in &scaled {
            assert!(
                (s[q] - mean).abs() <= 0.1 * mean.abs(),
                "entry {}",
                judged[q]
            );
        }
    }
}

#[test]
fn dual_arithmetic() {
    let u = [2.0, 1.0, 0.0];
    let v = [4.0, 0.0, 1.0];
    assert_eq!(mul(&u, &v), vec![8.0, 4.0, 2.0]);
    assert_eq!(div(&u, &v), vec![0.5, 0.25, -0.125]);
    assert_eq!(add(&u, &v), vec![6.0, 1.0, 1.0]);
    assert_eq!(sub(&u, &v), vec![-2.0, 1.0, -1.0]);
    assert_eq!(scale(2.0, &u), vec![4.0, 2.0, 0.0]);
}

#[test]
fn checks_run_in_the_g18_order() {
    let c = ladder_case(0);
    let curve = HwCurve::new(&c.times, &c.dfs).unwrap();
    let mut g = grid(&c, 41, 20);
    g.width = 0.0;
    let bad = [1.5];
    let e = ladder(&curve, &c.times, &c.dfs, c.a, c.sigma, &swap(&c), &bad, g).unwrap_err();
    assert_eq!(e.code, "E_INPUT");
    let e = price(
        &curve,
        &c.times,
        &c.dfs,
        c.a,
        c.sigma,
        &swap(&c),
        &c.exercise,
        g,
    )
    .unwrap_err();
    assert_eq!(e.code, "E_DOMAIN");
    let e = price(
        &curve,
        &c.times,
        &c.dfs,
        c.a,
        0.0,
        &swap(&c),
        &c.exercise,
        g,
    )
    .unwrap_err();
    assert_eq!(e.code, "E_DOMAIN");
}
