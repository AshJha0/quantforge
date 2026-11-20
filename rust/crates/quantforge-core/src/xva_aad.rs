//! Reverse-mode (adjoint) sensitivities of the G-41 valuation adjustments, written by hand
//! (`06-risk/xva-aad-adjustments.md`, rulings KR-262 to KR-268). Port of
//! `python/quantforge_core/xva_aad.py`: the same backward pass, bucket by bucket from the first.
use crate::error::{Result, fail};
use crate::xva::AdjInputs;

/// Gradient keys in canonical order (KR-263), before the optional im and capital keys.
pub const BASE_KEYS: [&str; 11] = [
    "counterparty.hazard_rate",
    "counterparty.hazard_buckets",
    "counterparty.recovery",
    "own.hazard_rate",
    "own.hazard_buckets",
    "own.recovery",
    "discount_factors",
    "ee",
    "ene",
    "funding.borrow_spread",
    "funding.lend_spread",
];

/// All keys a request may differentiate: the base keys, then im and capital when given.
pub fn keys(has_im: bool, has_capital: bool) -> Vec<&'static str> {
    let mut k = BASE_KEYS.to_vec();
    if has_im {
        k.extend(["im", "im_spread"]);
    }
    if has_capital {
        k.extend(["capital", "hurdle_rate"]);
    }
    k
}

/// KR-267 step 4: the reported keys, in canonical order; `E_INPUT` for an empty, repeating or
/// unknown `wrt`.
pub fn check_wrt(wrt: Option<&[String]>, allowed: &[&'static str]) -> Result<Vec<&'static str>> {
    let Some(w) = wrt else {
        return Ok(allowed.to_vec());
    };
    if w.is_empty() {
        return fail("E_INPUT", "wrt is empty");
    }
    for (i, k) in w.iter().enumerate() {
        if w[..i].contains(k) {
            return fail("E_INPUT", "wrt names a key twice");
        }
        if !allowed.contains(&k.as_str()) {
            return fail("E_INPUT", "wrt names a key that is not differentiated");
        }
    }
    Ok(allowed
        .iter()
        .copied()
        .filter(|a| w.iter().any(|k| k == a))
        .collect())
}

/// One gradient entry: a number or one value per bucket.
#[derive(Debug, Clone, PartialEq)]
pub enum Entry {
    /// A scalar input.
    Scalar(f64),
    /// A profile input or a bucket hazard.
    Profile(Vec<f64>),
}

/// The gradient of one output: (key, entry) in canonical order.
pub type Gradient = Vec<(&'static str, Entry)>;

struct Bar {
    sc: Vec<f64>,
    sb: Vec<f64>,
    pc: Vec<f64>,
    pb: Vec<f64>,
    df: Vec<f64>,
    ee: Vec<f64>,
    ene: Vec<f64>,
    prof: Vec<f64>,
    hb_direct: Vec<f64>,
    rc: f64,
    rb: f64,
    spread: f64,
}

impl Bar {
    fn new(n: usize) -> Bar {
        let z = vec![0.0; n];
        Bar {
            sc: vec![0.0; n + 1],
            sb: vec![0.0; n + 1],
            pc: z.clone(),
            pb: z.clone(),
            df: z.clone(),
            ee: z.clone(),
            ene: z.clone(),
            prof: z.clone(),
            hb_direct: z,
            rc: 0.0,
            rb: 0.0,
            spread: 0.0,
        }
    }
}

struct Tape {
    n: usize,
    t: Vec<f64>,
    dt: Vec<f64>,
    df: Vec<f64>,
    sc: Vec<f64>,
    sb: Vec<f64>,
    bc: Vec<f64>,
    bb: Vec<f64>,
    w: Vec<f64>,
}

impl Tape {
    fn new(x: &AdjInputs) -> Tape {
        let n = x.times.len();
        let mut t = vec![0.0];
        t.extend_from_slice(&x.times);
        let sc: Vec<f64> = t
            .iter()
            .map(|v| (-x.counterparty.hazard_rate * v).exp())
            .collect();
        let sb: Vec<f64> = t.iter().map(|v| (-x.own.hazard_rate * v).exp()).collect();
        let dt: Vec<f64> = (0..n).map(|i| x.times[i] - t[i]).collect();
        let bc = (0..n).map(|i| sc[i] - sc[i + 1]).collect();
        let bb = (0..n).map(|i| sb[i] - sb[i + 1]).collect();
        let df = x.discount_factors.clone();
        let w = (0..n).map(|i| df[i] * sc[i] * sb[i] * dt[i]).collect();
        Tape {
            n,
            t,
            dt,
            df,
            sc,
            sb,
            bc,
            bb,
            w,
        }
    }

    fn through_w(&self, bar: &mut Bar, i: usize, gw: f64) {
        bar.df[i] += gw * self.sc[i] * self.sb[i] * self.dt[i];
        bar.sc[i] += gw * self.df[i] * self.sb[i] * self.dt[i];
        bar.sb[i] += gw * self.df[i] * self.sc[i] * self.dt[i];
    }
}

fn cva_bar(tp: &Tape, x: &AdjInputs) -> Bar {
    let mut bar = Bar::new(tp.n);
    let lc = 1.0 - x.counterparty.recovery;
    for i in 0..tp.n {
        let (b, e) = (tp.bc[i], x.ee[i]);
        bar.rc -= tp.df[i] * e * b * tp.sb[i];
        bar.df[i] += lc * e * b * tp.sb[i];
        bar.ee[i] += lc * tp.df[i] * b * tp.sb[i];
        bar.pc[i] += lc * tp.df[i] * e * tp.sb[i];
        bar.sb[i] += lc * tp.df[i] * e * b;
    }
    bar
}

fn dva_bar(tp: &Tape, x: &AdjInputs) -> Bar {
    let mut bar = Bar::new(tp.n);
    let lb = 1.0 - x.own.recovery;
    for i in 0..tp.n {
        let (v, b) = (-x.ene[i], tp.bb[i]);
        bar.rb -= tp.df[i] * v * b * tp.sc[i];
        bar.df[i] += lb * v * b * tp.sc[i];
        bar.ene[i] -= lb * tp.df[i] * b * tp.sc[i];
        bar.pb[i] += lb * tp.df[i] * v * tp.sc[i];
        bar.sc[i] += lb * tp.df[i] * v * b;
    }
    bar
}

/// FCA (`to_ee`), MVA and KVA: `coef sum W_i x_i`.
fn funding_bar(tp: &Tape, coef: f64, prof: &[f64], to_ee: bool) -> Bar {
    let mut bar = Bar::new(tp.n);
    for i in 0..tp.n {
        if to_ee {
            bar.ee[i] += coef * tp.w[i];
        } else {
            bar.prof[i] += coef * tp.w[i];
        }
        bar.spread += tp.w[i] * prof[i];
        tp.through_w(&mut bar, i, coef * prof[i]);
    }
    bar
}

/// FBA; `branch` None: no overlap rule, Some(true): linear branch, Some(false): the floor (KR-264).
fn fba_bar(tp: &Tape, x: &AdjInputs, branch: Option<bool>) -> Bar {
    let mut bar = Bar::new(tp.n);
    let (hb, lb) = (x.own.hazard_rate, 1.0 - x.own.recovery);
    let coef = match branch {
        None => x.lend_spread,
        Some(true) => x.lend_spread - hb * lb,
        Some(false) => 0.0,
    };
    for i in 0..tp.n {
        let v = -x.ene[i];
        bar.ene[i] -= coef * tp.w[i];
        let g = tp.w[i] * v;
        if branch != Some(false) {
            bar.spread += g;
        }
        if branch == Some(true) {
            bar.rb += g * hb;
            bar.hb_direct[i] -= g * lb;
        }
        tp.through_w(&mut bar, i, coef * v);
    }
    bar
}

/// Survival adjoints to hazard adjoints: (flat, buckets). `gs[k]`: adjoint of `S(t_k)` used alone;
/// `gp[i]`: adjoint of the bucket difference `b_i`, kept whole so that a zero difference gives an
/// exact zero (spec, backward pass).
fn hazards(s: &[f64], gs: &[f64], b: &[f64], gp: &[f64], t: &[f64], dt: &[f64]) -> (f64, Vec<f64>) {
    let n = dt.len();
    let mut single = 0.0;
    for k in 0..=n {
        single += gs[k] * t[k] * s[k];
    }
    let mut pairs = 0.0;
    for i in 0..n {
        pairs += gp[i] * (t[i] * s[i] - t[i + 1] * s[i + 1]);
    }
    let mut buckets = vec![0.0; n];
    let mut tail = 0.0;
    for j in (0..n).rev() {
        tail += gs[j + 1] * s[j + 1];
        buckets[j] = -dt[j] * (tail - gp[j] * s[j + 1]);
        tail += gp[j] * b[j];
    }
    (-single - pairs, buckets)
}

fn gradient_of(tp: &Tape, bar: Bar, spread_key: Option<&str>, prof_key: Option<&str>) -> Gradient {
    let (hc, hc_b) = hazards(&tp.sc, &bar.sc, &tp.bc, &bar.pc, &tp.t, &tp.dt);
    let (hb, mut hb_b) = hazards(&tp.sb, &bar.sb, &tp.bb, &bar.pb, &tp.t, &tp.dt);
    let mut direct = 0.0;
    for (h, d) in hb_b.iter_mut().zip(&bar.hb_direct) {
        direct += d;
        *h += d;
    }
    let spread = |k: &str| Entry::Scalar(if spread_key == Some(k) { bar.spread } else { 0.0 });
    let prof = |k: &str| {
        Entry::Profile(if prof_key == Some(k) {
            bar.prof.clone()
        } else {
            vec![0.0; tp.n]
        })
    };
    vec![
        ("counterparty.hazard_rate", Entry::Scalar(hc)),
        ("counterparty.hazard_buckets", Entry::Profile(hc_b)),
        ("counterparty.recovery", Entry::Scalar(bar.rc)),
        ("own.hazard_rate", Entry::Scalar(hb + direct)),
        ("own.hazard_buckets", Entry::Profile(hb_b)),
        ("own.recovery", Entry::Scalar(bar.rb)),
        ("discount_factors", Entry::Profile(bar.df.clone())),
        ("ee", Entry::Profile(bar.ee.clone())),
        ("ene", Entry::Profile(bar.ene.clone())),
        ("funding.borrow_spread", spread("funding.borrow_spread")),
        ("funding.lend_spread", spread("funding.lend_spread")),
        ("im", prof("im")),
        ("im_spread", spread("im_spread")),
        ("capital", prof("capital")),
        ("hurdle_rate", spread("hurdle_rate")),
    ]
}

fn minus(a: &Gradient, b: &Gradient) -> Gradient {
    a.iter()
        .zip(b)
        .map(|((k, x), (_, y))| {
            let e = match (x, y) {
                (Entry::Scalar(p), Entry::Scalar(q)) => Entry::Scalar(p - q),
                (Entry::Profile(p), Entry::Profile(q)) => {
                    Entry::Profile(p.iter().zip(q).map(|(u, v)| u - v).collect())
                }
                _ => unreachable!("the gradients share their shapes"),
            };
            (*k, e)
        })
        .collect()
}

/// The gradient of every output of a validated request (call after [`crate::xva::adjustments`]
/// succeeded on it), restricted to `names`: (output name, gradient) in output order.
pub fn gradient(x: &AdjInputs, names: &[&'static str]) -> Vec<(&'static str, Gradient)> {
    let tp = Tape::new(x);
    let branch = x
        .exclude_dva_overlap
        .then(|| x.lend_spread - x.own.hazard_rate * (1.0 - x.own.recovery) >= 0.0);
    let fca = gradient_of(
        &tp,
        funding_bar(&tp, x.borrow_spread, &x.ee, true),
        Some("funding.borrow_spread"),
        None,
    );
    let fba = gradient_of(&tp, fba_bar(&tp, x, branch), Some("funding.lend_spread"), None);
    let fva = minus(&fca, &fba);
    let mut raw = vec![
        ("cva", gradient_of(&tp, cva_bar(&tp, x), None, None)),
        ("dva", gradient_of(&tp, dva_bar(&tp, x), None, None)),
        ("fca", fca),
        ("fba", fba),
        ("fva", fva),
    ];
    if let Some((im, s)) = &x.im {
        let g = gradient_of(&tp, funding_bar(&tp, *s, im, false), Some("im_spread"), Some("im"));
        raw.push(("mva", g));
    }
    if let Some((cap, h)) = &x.capital {
        let g = gradient_of(
            &tp,
            funding_bar(&tp, *h, cap, false),
            Some("hurdle_rate"),
            Some("capital"),
        );
        raw.push(("kva", g));
    }
    raw.into_iter()
        .map(|(o, g)| {
            let kept = g.into_iter().filter(|(k, _)| names.contains(k)).collect();
            (o, kept)
        })
        .collect()
}

#[cfg(test)]
#[path = "aad_adjust_tests.rs"]
mod tests;
