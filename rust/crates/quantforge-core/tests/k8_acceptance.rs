//! K-8 acceptance 3 (`specifications/06-risk/bermudan-ladder-k8.md`): `num.richardson.check` on
//! 201/401/801 for the three `aadladder_g` cases against `oracle/K8_ACCEPTANCE_W2.json`. Runs only with
//! `QF_K8_ACCEPTANCE=1` (about a minute); moved here from `src/bermudan_k8_tests.rs` so the skipped body
//! is not counted as uncovered library lines by the per-file coverage gate (R6-26). Same test, unchanged.
use quantforge_core::bermudan_k8::{Ladder, ladder};
use quantforge_core::json::{Json, parse};
use quantforge_core::shortrate::{FdGrid, HwCurve, SwapLeg};
use quantforge_core::stage_k::richardson_check;

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

/// Acceptance 3: on 201/401/801, `num.richardson.check` with assumed order 2 gives OK and an
/// observed order in [1.5, 2.5] on the price and every ladder entry not exactly zero on all three
/// grids; the values must equal the Python record to 1e-9 of the row scale.
#[test]
fn acceptance_3_observed_order() {
    if std::env::var("QF_K8_ACCEPTANCE").as_deref() != Ok("1") {
        return;
    }
    let record = repo("oracle/K8_ACCEPTANCE_W2.json");
    let py_values = record.get("values").unwrap();
    let mut bad = Vec::new();
    let mut worst_gap: f64 = 0.0;
    for index in 0..3 {
        let c = ladder_case(index);
        let py = py_values
            .get(&format!("aadladder_g-000{}", index + 1))
            .unwrap();
        let mut rows = Vec::new();
        for (nx, spy) in [(201, 100), (401, 200), (801, 400)] {
            let r = row(&ladder_of(&c, nx, spy));
            let p = reals(py.get(&format!("{nx}/{spy}")).unwrap());
            let scale = max_abs(&p);
            for k in 0..r.len() {
                worst_gap = worst_gap.max((r[k] - p[k]).abs() / scale);
            }
            rows.push(r);
        }
        for k in 0..rows[0].len() {
            let vals = [rows[0][k], rows[1][k], rows[2][k]];
            if vals.iter().all(|x| *x == 0.0) {
                continue;
            }
            let rc = richardson_check(&vals, 2.0, 2.0).unwrap();
            let ok =
                rc.status == "OK" && rc.observed_order.is_some_and(|o| (1.5..=2.5).contains(&o));
            if !ok {
                bad.push(format!(
                    "[{index}, {k}, {}, {:?}]",
                    rc.status, rc.observed_order
                ));
            }
            println!(
                "K-8 acceptance 3 (Rust): case {index} entry {k} order {:?}",
                rc.observed_order
            );
        }
    }
    println!(
        "K-8 acceptance 3 (Rust): failures={bad:?} max_gap_vs_python_relative_to_row_scale={worst_gap:e}"
    );
    assert!(
        worst_gap <= 1e-9,
        "Rust differs from the Python record by {worst_gap}"
    );
    assert!(bad.is_empty(), "K-8 acceptance 3 fails on {bad:?}");
}
