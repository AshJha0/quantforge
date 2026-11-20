//! Tests of `xva_aad` (06-risk/xva-aad-adjustments.md): identities of the backward pass on 1,000
//! seeded random requests, the overlap branches, exact zeros and the `wrt` rules. The goldens run
//! through the CLI (`golden_replay`, conformance).
use super::*;
use crate::xva::{AdjInputs, Name, adjustments};

struct Lcg(u64);

impl Lcg {
    fn next(&mut self) -> f64 {
        self.0 = self
            .0
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        (self.0 >> 11) as f64 / (1u64 << 53) as f64
    }
}

fn scalar(g: &Gradient, k: &str) -> f64 {
    match g.iter().find(|(n, _)| *n == k) {
        Some((_, Entry::Scalar(v))) => *v,
        _ => panic!("no scalar {k}"),
    }
}

fn profile(g: &Gradient, k: &str) -> Vec<f64> {
    match g.iter().find(|(n, _)| *n == k) {
        Some((_, Entry::Profile(v))) => v.clone(),
        _ => panic!("no profile {k}"),
    }
}

fn near(a: f64, b: f64, tol: f64) -> bool {
    (a - b).abs() <= tol * 1f64.max(a.abs().max(b.abs()))
}

fn base() -> AdjInputs {
    AdjInputs {
        times: vec![0.5, 1.0, 1.5, 2.0],
        discount_factors: vec![0.985, 0.97, 0.955, 0.94],
        ee: vec![120.0, 150.0, 130.0, 80.0],
        ene: vec![-60.0, -90.0, -100.0, -70.0],
        counterparty: Name {
            hazard_rate: 0.02,
            recovery: 0.4,
        },
        own: Name {
            hazard_rate: 0.01,
            recovery: 0.4,
        },
        borrow_spread: 0.008,
        lend_spread: 0.008,
        exclude_dva_overlap: false,
        im: None,
        capital: None,
    }
}

fn find<'a>(g: &'a [(&'static str, Gradient)], o: &str) -> &'a Gradient {
    &g.iter().find(|(n, _)| *n == o).unwrap().1
}

#[test]
fn golden_one_selected_entries() {
    // aadadj_k-0001 (oracle, 50 digits): d cva / d h_c, d cva / d R_c, d fca / d s_b, d cva / d ee[1].
    let x = base();
    let g = gradient(&x, &keys(false, false));
    let cva = find(&g, "cva");
    assert!(near(
        scalar(cva, "counterparty.hazard_rate"),
        133.0258166316599,
        1e-12
    ));
    assert!(near(
        scalar(cva, "counterparty.recovery"),
        -4.51643629000504,
        1e-12
    ));
    assert!(near(profile(cva, "ee")[1], 0.005704780048492856, 1e-12));
    assert_eq!(profile(cva, "own.hazard_buckets")[3], 0.0);
    let fca = find(&g, "fca");
    assert!(near(
        scalar(fca, "funding.borrow_spread"),
        226.952805418071,
        1e-12
    ));
    assert_eq!(g.len(), 5);
}

#[test]
fn identities_on_random_requests() {
    let mut r = Lcg(20_261_120);
    for _ in 0..1000 {
        let n = 1 + (r.next() * 6.0) as usize;
        let scale = 10f64.powf(-3.0 + 9.0 * r.next());
        let mut acc = 0.0;
        let mut x = base();
        x.times.clear();
        x.discount_factors.clear();
        x.ee.clear();
        x.ene.clear();
        let mut im = vec![];
        let mut cap = vec![];
        for _ in 0..n {
            acc += 0.01 + 3.0 * r.next();
            x.times.push(acc);
            x.discount_factors.push(0.3 + 0.75 * r.next());
            x.ee.push(if r.next() < 0.15 {
                0.0
            } else {
                scale * r.next()
            });
            x.ene.push(if r.next() < 0.15 {
                0.0
            } else {
                -scale * r.next()
            });
            im.push(scale * r.next());
            cap.push(scale * r.next());
        }
        x.counterparty = Name {
            hazard_rate: if r.next() < 0.5 { 0.0 } else { 0.6 * r.next() },
            recovery: 0.999_999 * r.next(),
        };
        x.own = Name {
            hazard_rate: if r.next() < 0.5 { 0.0 } else { 0.1 * r.next() },
            recovery: 0.99 * r.next(),
        };
        x.borrow_spread = 0.03 * r.next();
        x.lend_spread = 0.03 * r.next();
        x.exclude_dva_overlap = r.next() < 0.5;
        x.im = Some((im, 0.02 * r.next()));
        x.capital = Some((cap.clone(), 0.15 * r.next()));
        let v = adjustments(&x).unwrap();
        let g = gradient(&x, &keys(true, true));
        for (o, row) in &g {
            for name in ["counterparty", "own"] {
                let flat = scalar(row, &format!("{name}.hazard_rate"));
                let sum: f64 = profile(row, &format!("{name}.hazard_buckets")).iter().sum();
                assert!(near(flat, sum, 1e-11), "{o} {name} {flat} {sum}");
            }
        }
        let rc = x.counterparty.recovery;
        let rb = x.own.recovery;
        assert!(near(
            scalar(find(&g, "cva"), "counterparty.recovery"),
            -v.cva / (1.0 - rc),
            1e-12
        ));
        assert!(near(
            scalar(find(&g, "dva"), "own.recovery"),
            -v.dva / (1.0 - rb),
            1e-12
        ));
        let gk = profile(find(&g, "kva"), "capital");
        let lin: f64 = gk.iter().zip(&cap).map(|(a, b)| a * b).sum();
        assert!(near(lin, v.kva.unwrap(), 1e-12));
        let ge = profile(find(&g, "cva"), "ee");
        let lin: f64 = ge.iter().zip(&x.ee).map(|(a, b)| a * b).sum();
        assert!(near(lin, v.cva, 1e-12));
        let fva = find(&g, "fva");
        let d = scalar(find(&g, "fca"), "counterparty.hazard_rate")
            - scalar(find(&g, "fba"), "counterparty.hazard_rate");
        assert_eq!(scalar(fva, "counterparty.hazard_rate"), d);
        let mva = find(&g, "mva");
        let s = x.im.as_ref().unwrap().1;
        assert!(near(scalar(mva, "im_spread") * s, v.mva.unwrap(), 1e-12));
    }
}

#[test]
fn overlap_branches() {
    // On the kink: 0.005 - 0.01 x 0.5 = 0 exactly; the linear branch (KR-264).
    let mut x = base();
    x.own = Name {
        hazard_rate: 0.01,
        recovery: 0.5,
    };
    x.lend_spread = 0.005;
    x.exclude_dva_overlap = true;
    let g = gradient(&x, &keys(false, false));
    let fba = find(&g, "fba");
    let sl = scalar(fba, "funding.lend_spread");
    assert!(near(sl, 150.34122754292395, 1e-12));
    assert!(near(scalar(fba, "own.hazard_rate"), -0.5 * sl, 1e-12));
    assert!(near(scalar(fba, "own.recovery"), 0.01 * sl, 1e-12));
    // Below the kink: the floor, every FBA entry exactly zero.
    x.own.hazard_rate = 0.02;
    let g = gradient(&x, &keys(false, false));
    for (_, e) in find(&g, "fba") {
        match e {
            Entry::Scalar(v) => assert_eq!(*v, 0.0),
            Entry::Profile(v) => assert!(v.iter().all(|y| *y == 0.0)),
        }
    }
}

#[test]
fn zero_hazard_gives_exact_zero_buckets_at_zero_exposure_points() {
    let mut x = base();
    x.counterparty.hazard_rate = 0.0;
    x.ee = vec![1.0e5, 0.0, 3.5e4, 0.0];
    let g = gradient(&x, &keys(false, false));
    let b = profile(find(&g, "cva"), "counterparty.hazard_buckets");
    assert_eq!(b[1], 0.0);
    assert_eq!(b[3], 0.0);
}

#[test]
fn wrt_rules() {
    let all = keys(true, false);
    assert_eq!(all.len(), 13);
    assert_eq!(keys(false, true)[11..], ["capital", "hurdle_rate"]);
    assert_eq!(check_wrt(None, &all).unwrap(), all);
    let w = vec!["ene".to_string(), "own.recovery".to_string()];
    assert_eq!(
        check_wrt(Some(&w), &all).unwrap(),
        vec!["own.recovery", "ene"]
    );
    for bad in [vec![], vec!["ee", "ee"], vec!["capital"], vec!["x"]] {
        let b: Vec<String> = bad.iter().map(|s| s.to_string()).collect();
        assert_eq!(check_wrt(Some(&b), &all).unwrap_err().code, "E_INPUT");
    }
    let x = base();
    let g = gradient(&x, &["ee"]);
    assert!(g.iter().all(|(_, row)| row.len() == 1 && row[0].0 == "ee"));
}

/// Every scalar and profile entry against a binary64 Richardson bump of `adjustments` on benign
/// inputs (no small profile point, so the bump's own rounding stays near 1e-10; KR-265 explains why
/// this is not the acceptance). Three overlap settings, with im and capital.
#[test]
fn every_entry_against_a_binary64_bump() {
    for (own_h, own_r, lend, excl) in [
        (0.01, 0.4, 0.008, false),
        (0.01, 0.4, 0.008, true),
        (0.02, 0.4, 0.008, true),
    ] {
        let mut x = base();
        x.own = Name {
            hazard_rate: own_h,
            recovery: own_r,
        };
        x.lend_spread = lend;
        x.exclude_dva_overlap = excl;
        x.im = Some((vec![200.0, 210.0, 190.0, 150.0], 0.006));
        x.capital = Some((vec![40.0, 42.0, 38.0, 30.0], 0.1));
        let g = gradient(&x, &keys(true, true));
        let value = |y: &AdjInputs, o: &str| -> f64 {
            let v = adjustments(y).unwrap();
            match o {
                "cva" => v.cva,
                "dva" => v.dva,
                "fca" => v.fca,
                "fba" => v.fba,
                "fva" => v.fva,
                "mva" => v.mva.unwrap(),
                _ => v.kva.unwrap(),
            }
        };
        type Set = fn(&mut AdjInputs, usize, f64);
        let inputs: [(&str, bool, Set, fn(&AdjInputs, usize) -> f64); 13] = [
            (
                "counterparty.hazard_rate",
                true,
                |y, _, v| y.counterparty.hazard_rate = v,
                |y, _| y.counterparty.hazard_rate,
            ),
            (
                "counterparty.recovery",
                true,
                |y, _, v| y.counterparty.recovery = v,
                |y, _| y.counterparty.recovery,
            ),
            (
                "own.hazard_rate",
                true,
                |y, _, v| y.own.hazard_rate = v,
                |y, _| y.own.hazard_rate,
            ),
            (
                "own.recovery",
                true,
                |y, _, v| y.own.recovery = v,
                |y, _| y.own.recovery,
            ),
            (
                "discount_factors",
                false,
                |y, i, v| y.discount_factors[i] = v,
                |y, i| y.discount_factors[i],
            ),
            ("ee", false, |y, i, v| y.ee[i] = v, |y, i| y.ee[i]),
            ("ene", false, |y, i, v| y.ene[i] = v, |y, i| y.ene[i]),
            (
                "funding.borrow_spread",
                true,
                |y, _, v| y.borrow_spread = v,
                |y, _| y.borrow_spread,
            ),
            (
                "funding.lend_spread",
                true,
                |y, _, v| y.lend_spread = v,
                |y, _| y.lend_spread,
            ),
            (
                "im",
                false,
                |y, i, v| y.im.as_mut().unwrap().0[i] = v,
                |y, i| y.im.as_ref().unwrap().0[i],
            ),
            (
                "im_spread",
                true,
                |y, _, v| y.im.as_mut().unwrap().1 = v,
                |y, _| y.im.as_ref().unwrap().1,
            ),
            (
                "capital",
                false,
                |y, i, v| y.capital.as_mut().unwrap().0[i] = v,
                |y, i| y.capital.as_ref().unwrap().0[i],
            ),
            (
                "hurdle_rate",
                true,
                |y, _, v| y.capital.as_mut().unwrap().1 = v,
                |y, _| y.capital.as_ref().unwrap().1,
            ),
        ];
        for (o, row) in &g {
            for (key, scalar, set, get) in inputs {
                let n = if scalar { 1 } else { 4 };
                for i in 0..n {
                    let x0 = get(&x, i);
                    let d = |h: f64| {
                        let (mut up, mut dn) = (x.clone(), x.clone());
                        set(&mut up, i, x0 * (1.0 + h));
                        set(&mut dn, i, x0 * (1.0 - h));
                        (value(&up, o) - value(&dn, o)) / (2.0 * h * x0)
                    };
                    let reference = (4.0 * d(5e-5) - d(1e-4)) / 3.0;
                    let aad = if scalar {
                        scalar(row, key)
                    } else {
                        profile(row, key)[i]
                    };
                    assert!(
                        (aad - reference).abs() <= 1e-7 * 1f64.max(reference.abs()),
                        "{o} {key}[{i}] {aad} {reference} overlap {excl}"
                    );
                }
            }
        }
    }
}
