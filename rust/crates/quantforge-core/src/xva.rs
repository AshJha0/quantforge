//! Deterministic xVA layer on given paths (`06-risk/xva-framework.md`, rulings G-40 to G-44):
//! collateralised exposure, valuation adjustments, SIMM-style IR delta margin, Hull-White
//! wrong-way risk.
use crate::error::{Result, fail};

/// CSA terms of one netting set (G-40).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Csa {
    /// Threshold below which the bank receives no collateral.
    pub threshold_receive: f64,
    /// Threshold below which the bank posts no collateral.
    pub threshold_post: f64,
    /// Minimum transfer amount.
    pub mta: f64,
    /// Margin period of risk, in grid steps.
    pub mpor_steps: i64,
    /// Independent amount held.
    pub independent_amount: f64,
}

/// Exposure profile of one netting set.
#[derive(Debug, Clone, PartialEq)]
pub struct SetExposure {
    /// Expected exposure per time.
    pub ee: Vec<f64>,
    /// Expected negative exposure per time.
    pub ene: Vec<f64>,
    /// Potential future exposure at the quantile per time.
    pub pfe: Vec<f64>,
    /// Time-averaged EE over the grid.
    pub epe: f64,
    /// Effective EPE over the first year.
    pub effective_epe: f64,
}

/// `xva.exposure.collateralised` for one netting set: `paths[p][i]` the netted value on path
/// `p` at `times[i]`.
pub fn set_exposure(
    times: &[f64],
    paths: &[Vec<f64>],
    csa: Option<&Csa>,
    q: f64,
) -> Result<SetExposure> {
    let n = times.len();
    let np = paths.len();
    let mut e = vec![vec![0.0; np]; n];
    let mut ng = vec![vec![0.0; np]; n];
    for (p, v) in paths.iter().enumerate() {
        let coll: Vec<f64> = match csa {
            None => vec![0.0; n],
            Some(c) => {
                let target = |x: f64| {
                    (x - c.threshold_receive).max(0.0) - (-x - c.threshold_post).max(0.0)
                        + c.independent_amount
                };
                let mut k = vec![target(v[0]); n];
                for j in 1..n {
                    let t = target(v[j]);
                    k[j] = if (t - k[j - 1]).abs() >= c.mta {
                        t
                    } else {
                        k[j - 1]
                    };
                }
                let l = usize::try_from(c.mpor_steps).unwrap_or(0);
                (0..n).map(|i| k[i.saturating_sub(l)]).collect()
            }
        };
        for i in 0..n {
            e[i][p] = (v[i] - coll[i]).max(0.0);
            ng[i][p] = (v[i] - coll[i]).min(0.0);
        }
    }
    #[allow(clippy::cast_precision_loss)]
    let npf = np as f64;
    let ee: Vec<f64> = e.iter().map(|x| x.iter().sum::<f64>() / npf).collect();
    let ene: Vec<f64> = ng.iter().map(|x| x.iter().sum::<f64>() / npf).collect();
    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    let rank = ((q * npf).ceil() as usize).clamp(1, np);
    let pfe: Vec<f64> = e
        .iter()
        .map(|x| {
            let mut s = x.clone();
            s.sort_by(f64::total_cmp);
            s[rank - 1]
        })
        .collect();
    let span = times[n - 1] - times[0];
    let epe = (1..n)
        .map(|i| ee[i] * (times[i] - times[i - 1]))
        .sum::<f64>()
        / span;
    let mut eee = ee[0];
    let (mut acc, mut last) = (0.0, times[0]);
    for i in 1..n {
        if times[i] - times[0] > 1.0 {
            break;
        }
        eee = eee.max(ee[i]);
        acc += eee * (times[i] - times[i - 1]);
        last = times[i];
    }
    let effective_epe = if last > times[0] {
        acc / (last - times[0])
    } else {
        ee[0]
    };
    Ok(SetExposure {
        ee,
        ene,
        pfe,
        epe,
        effective_epe,
    })
}

/// Checks the shared inputs of `xva.exposure.collateralised`.
pub fn check_collateral_inputs(times: &[f64], q: f64, csas: &[&Csa]) -> Result<()> {
    crate::error::finite("times", &times)?;
    crate::error::finite("pfe_quantile", &q)?;
    if times.len() < 2 || times.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_INPUT", "times needs at least two increasing values");
    }
    if !(q > 0.0 && q <= 1.0) {
        return fail("E_DOMAIN", "pfe_quantile must be in (0, 1]");
    }
    for c in csas {
        let v = [
            c.threshold_receive,
            c.threshold_post,
            c.mta,
            c.independent_amount,
        ];
        crate::error::finite("csa", &v)?;
        if c.threshold_receive < 0.0 || c.threshold_post < 0.0 || c.mta < 0.0 || c.mpor_steps < 0 {
            return fail(
                "E_DOMAIN",
                "thresholds, MTA and mpor_steps must not be negative",
            );
        }
    }
    Ok(())
}

/// A credit name: hazard rate and recovery.
#[derive(Debug, Clone, Copy)]
pub struct Name {
    /// Flat hazard rate, `>= 0`.
    pub hazard_rate: f64,
    /// Recovery in `[0, 1)`.
    pub recovery: f64,
}

/// Outputs of [`adjustments`]; `mva` and `kva` only when their inputs are given.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Adjustments {
    /// CVA.
    pub cva: f64,
    /// DVA.
    pub dva: f64,
    /// Funding cost adjustment.
    pub fca: f64,
    /// Funding benefit adjustment.
    pub fba: f64,
    /// `fca - fba`.
    pub fva: f64,
    /// Margin valuation adjustment.
    pub mva: Option<f64>,
    /// Capital valuation adjustment.
    pub kva: Option<f64>,
}

/// Inputs of [`adjustments`].
#[derive(Debug, Clone)]
pub struct AdjInputs {
    /// Bucket ends `t_1 < ... < t_n` (buckets start at 0).
    pub times: Vec<f64>,
    /// `D_i`.
    pub discount_factors: Vec<f64>,
    /// EE at bucket ends, `>= 0`.
    pub ee: Vec<f64>,
    /// ENE at bucket ends, `<= 0`.
    pub ene: Vec<f64>,
    /// Counterparty.
    pub counterparty: Name,
    /// The bank itself.
    pub own: Name,
    /// Borrowing spread.
    pub borrow_spread: f64,
    /// Lending spread.
    pub lend_spread: f64,
    /// Remove the own-credit part of the lending spread (G-41).
    pub exclude_dva_overlap: bool,
    /// Initial margin profile and its funding spread.
    pub im: Option<(Vec<f64>, f64)>,
    /// Capital profile and hurdle rate.
    pub capital: Option<(Vec<f64>, f64)>,
}

/// `xva.adjustments.value` (G-41): bucketed CVA, DVA, FVA (with the DVA overlap rule), MVA and
/// KVA with first-to-default weights at the bucket start.
pub fn adjustments(x: &AdjInputs) -> Result<Adjustments> {
    let n = x.times.len();
    let lens = [x.discount_factors.len(), x.ee.len(), x.ene.len()];
    let extra = [
        x.im.as_ref().map(|v| v.0.len()),
        x.capital.as_ref().map(|v| v.0.len()),
    ];
    if n == 0 || lens.iter().any(|l| *l != n) || extra.iter().flatten().any(|l| *l != n) {
        return fail(
            "E_INPUT",
            "times, discount_factors, ee, ene (and profiles) need one length",
        );
    }
    for v in [&x.times, &x.discount_factors, &x.ee, &x.ene] {
        crate::error::finite("inputs", &v.as_slice())?;
    }
    if x.times[0] <= 0.0 || x.times.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_INPUT", "times must be positive and increasing");
    }
    for nm in [x.counterparty, x.own] {
        crate::error::finite("name", &[nm.hazard_rate, nm.recovery])?;
        if nm.hazard_rate < 0.0 || !(0.0..1.0).contains(&nm.recovery) {
            return fail("E_DOMAIN", "hazard_rate >= 0 and recovery in [0, 1)");
        }
    }
    if x.ee.iter().any(|e| *e < 0.0) || x.ene.iter().any(|e| *e > 0.0) {
        return fail("E_DOMAIN", "ee must be >= 0 and ene <= 0");
    }
    let (hc, rc, hb, rb) = (
        x.counterparty.hazard_rate,
        x.counterparty.recovery,
        x.own.hazard_rate,
        x.own.recovery,
    );
    let sc = |t: f64| (-hc * t).exp();
    let sb = |t: f64| (-hb * t).exp();
    let sl = if x.exclude_dva_overlap {
        (x.lend_spread - hb * (1.0 - rb)).max(0.0)
    } else {
        x.lend_spread
    };
    let mut o = Adjustments {
        cva: 0.0,
        dva: 0.0,
        fca: 0.0,
        fba: 0.0,
        fva: 0.0,
        mva: x.im.as_ref().map(|_| 0.0),
        kva: x.capital.as_ref().map(|_| 0.0),
    };
    let mut prev = 0.0;
    for i in 0..n {
        let (t, d) = (x.times[i], x.discount_factors[i]);
        let dt = t - prev;
        let alive = sc(prev) * sb(prev);
        o.cva += d * x.ee[i] * (sc(prev) - sc(t)) * sb(prev);
        o.dva += d * x.ene[i].abs() * (sb(prev) - sb(t)) * sc(prev);
        o.fca += d * x.ee[i] * alive * dt;
        o.fba += d * x.ene[i].abs() * alive * dt;
        if let (Some(m), Some((im, _))) = (o.mva.as_mut(), x.im.as_ref()) {
            *m += d * im[i] * alive * dt;
        }
        if let (Some(k), Some((cap, _))) = (o.kva.as_mut(), x.capital.as_ref()) {
            *k += d * cap[i] * alive * dt;
        }
        prev = t;
    }
    o.cva *= 1.0 - rc;
    o.dva *= 1.0 - rb;
    o.fca *= x.borrow_spread;
    o.fba *= sl;
    o.fva = o.fca - o.fba;
    if let (Some(m), Some((_, s))) = (o.mva.as_mut(), x.im.as_ref()) {
        *m *= s;
    }
    if let (Some(k), Some((_, h))) = (o.kva.as_mut(), x.capital.as_ref()) {
        *k *= h;
    }
    Ok(o)
}

/// `xva.simm.ir_delta` (G-43): `(weighted sensitivities, concentration factor, margin)`.
pub fn simm_ir_delta(
    s: &[f64],
    rw: &[f64],
    rho: &[Vec<f64>],
    threshold: f64,
) -> Result<(Vec<f64>, f64, f64)> {
    let n = s.len();
    if n == 0 || rw.len() != n || rho.len() != n || rho.iter().any(|r| r.len() != n) {
        return fail(
            "E_INPUT",
            "sensitivities, risk_weights and correlations need one size",
        );
    }
    crate::error::finite("sensitivities", &s)?;
    crate::error::finite("risk_weights", &rw)?;
    crate::error::finite("concentration_threshold", &threshold)?;
    for r in rho {
        crate::error::finite("correlations", &r.as_slice())?;
    }
    if threshold <= 0.0 {
        return fail("E_DOMAIN", "concentration_threshold must be positive");
    }
    if rw.iter().any(|w| *w < 0.0) {
        return fail("E_DOMAIN", "risk weights must not be negative");
    }
    if rho.iter().flatten().any(|r| !(-1.0..=1.0).contains(r)) {
        return fail("E_DOMAIN", "correlations must be in [-1, 1]");
    }
    let cr = (s.iter().sum::<f64>().abs() / threshold).sqrt().max(1.0);
    let ws: Vec<f64> = (0..n).map(|k| rw[k] * s[k] * cr).collect();
    let mut sum = 0.0;
    for k in 0..n {
        for l in 0..n {
            let r = if k == l { 1.0 } else { rho[k][l] };
            sum += r * ws[k] * ws[l];
        }
    }
    Ok((ws, cr, sum.max(0.0).sqrt()))
}

/// `xva.wwr.cva_hw` (G-44): Hull-White wrong-way CVA, hazard `exp(a_i + b V)` per bucket with
/// `a_i` calibrated to `mean_p S_p(t_i) = e^{-h t_i}` (Newton from `ln h`, bisection guard).
/// Returns `(cva, a)`.
pub fn wwr_cva_hw(
    times: &[f64],
    values: &[Vec<f64>],
    dfs: &[f64],
    h: f64,
    recovery: f64,
    b: f64,
) -> Result<(f64, Vec<f64>)> {
    let n = times.len();
    if n == 0 || dfs.len() != n || values.is_empty() || values.iter().any(|v| v.len() != n) {
        return fail(
            "E_INPUT",
            "values paths and discount_factors need the length of times",
        );
    }
    crate::error::finite("times", &times)?;
    crate::error::finite("discount_factors", &dfs)?;
    crate::error::finite("params", &[h, recovery, b])?;
    for v in values {
        crate::error::finite("values", &v.as_slice())?;
    }
    if times[0] <= 0.0 || times.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_INPUT", "times must be positive and increasing");
    }
    if h <= 0.0 || !(0.0..1.0).contains(&recovery) {
        return fail("E_DOMAIN", "hazard_rate > 0 and recovery in [0, 1)");
    }
    #[allow(clippy::cast_precision_loss)]
    let np = values.len() as f64;
    let mut surv = vec![1.0; values.len()];
    let mut a_out = Vec::with_capacity(n);
    let mut cva = 0.0;
    let mut prev = 0.0;
    for i in 0..n {
        let dt = times[i] - prev;
        let target = (-h * times[i]).exp();
        // g(a) = mean S_p(t_i) - target, strictly decreasing in a.
        let g = |a: f64| -> (f64, f64) {
            let (mut m, mut d) = (0.0, 0.0);
            for (p, v) in values.iter().enumerate() {
                let lam = (a + b * v[i]).exp();
                let s = surv[p] * (-lam * dt).exp();
                m += s;
                d -= s * lam * dt;
            }
            (m / np - target, d / np)
        };
        let mut a = h.ln();
        let (mut lo, mut hi) = (f64::NEG_INFINITY, f64::INFINITY);
        for _ in 0..200 {
            let (f, d) = g(a);
            if f > 0.0 {
                lo = a;
            } else {
                hi = a;
            }
            let mut next = a - f / d;
            if !(next > lo && next < hi && next.is_finite()) {
                next = if lo.is_finite() && hi.is_finite() {
                    0.5 * (lo + hi)
                } else if lo.is_finite() {
                    lo + 1.0
                } else {
                    hi - 1.0
                };
            }
            if (next - a).abs() <= 1e-15 * a.abs().max(1.0) {
                a = next;
                break;
            }
            a = next;
        }
        let mut bucket = 0.0;
        for (p, v) in values.iter().enumerate() {
            let s_new = surv[p] * (-(a + b * v[i]).exp() * dt).exp();
            bucket += v[i].max(0.0) * (surv[p] - s_new);
            surv[p] = s_new;
        }
        cva += dfs[i] * bucket / np;
        a_out.push(a);
        prev = times[i];
    }
    Ok(((1.0 - recovery) * cva, a_out))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn collateral_input_checks_each_field() {
        let t = [0.0, 1.0];
        let ok = Csa {
            threshold_receive: 1.0,
            threshold_post: 1.0,
            mta: 0.5,
            mpor_steps: 1,
            independent_amount: -2.0,
        };
        assert!(check_collateral_inputs(&t, 0.95, &[&ok]).is_ok());
        let bad = [
            Csa {
                threshold_receive: -0.1,
                ..ok
            },
            Csa {
                threshold_post: -0.1,
                ..ok
            },
            Csa { mta: -0.1, ..ok },
            Csa {
                mpor_steps: -1,
                ..ok
            },
        ];
        for c in &bad {
            assert_eq!(
                check_collateral_inputs(&t, 0.95, &[&ok, c])
                    .unwrap_err()
                    .code,
                "E_DOMAIN"
            );
        }
        let nan = Csa {
            mta: f64::NAN,
            ..ok
        };
        assert_eq!(
            check_collateral_inputs(&t, 0.95, &[&nan]).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            check_collateral_inputs(&t, 0.0, &[&ok]).unwrap_err().code,
            "E_DOMAIN"
        );
        assert!(check_collateral_inputs(&t, 1.0, &[&ok]).is_ok());
        assert_eq!(
            check_collateral_inputs(&[0.0], 0.5, &[]).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(
            check_collateral_inputs(&[1.0, 1.0], 0.5, &[])
                .unwrap_err()
                .code,
            "E_INPUT"
        );
    }

    #[test]
    fn zero_threshold_no_lag_gives_zero_exposure() {
        let t = [0.0, 0.5, 1.0];
        let paths = vec![vec![0.0, 3.0, -2.0], vec![0.0, -1.0, 4.0]];
        let c = Csa {
            threshold_receive: 0.0,
            threshold_post: 0.0,
            mta: 0.0,
            mpor_steps: 0,
            independent_amount: 0.0,
        };
        let r = set_exposure(&t, &paths, Some(&c), 0.9).unwrap();
        assert!(r.ee.iter().all(|e| *e == 0.0));
        let r = set_exposure(&t, &paths, None, 1.0).unwrap();
        assert_eq!(r.ee, vec![0.0, 1.5, 2.0]);
        assert_eq!(r.pfe, vec![0.0, 3.0, 4.0]);
    }

    #[test]
    fn wwr_b_zero_is_independent_cva() {
        let t = [0.25, 0.5, 0.75, 1.0];
        let v = vec![vec![3.0, 5.0, 2.0, -1.0], vec![1.0, 6.0, 9.0, 4.0]];
        let d = [0.995, 0.99, 0.985, 0.98];
        let (cva, a) = wwr_cva_hw(&t, &v, &d, 0.03, 0.4, 0.0).unwrap();
        assert!(a.iter().all(|x| (x - 0.03_f64.ln()).abs() < 1e-14));
        let mut indep = 0.0;
        let mut prev = 0.0_f64;
        for i in 0..4 {
            let ee = (v[0][i].max(0.0) + v[1][i].max(0.0)) / 2.0;
            indep += d[i] * ee * ((-0.03 * prev).exp() - (-0.03 * t[i]).exp());
            prev = t[i];
        }
        assert!((cva - 0.6 * indep).abs() < 1e-14);
        let (wrong, _) = wwr_cva_hw(&t, &v, &d, 0.03, 0.4, 0.2).unwrap();
        assert!(wrong > cva);
    }

    #[test]
    fn simm_single_factor() {
        let (ws, cr, m) = simm_ir_delta(&[10_000.0], &[90.0], &[vec![1.0]], 1e9).unwrap();
        assert_eq!((ws[0], cr), (900_000.0, 1.0));
        assert!((m - 900_000.0).abs() < 1e-9);
    }
}

/// Output of [`model_reserve`].
#[derive(Debug, Clone, PartialEq)]
pub struct Reserve {
    /// Mean of the model prices.
    pub mean: f64,
    /// `max - min`.
    pub range: f64,
    /// `range / 2`.
    pub half_range: f64,
    /// `max_m |p_m - p_ref|`.
    pub reserve: f64,
    /// The model attaining `reserve` (first in code-point order on a tie).
    pub worst_model: String,
    /// `reserve / |p_ref|`, `None` when `p_ref = 0`.
    pub relative_reserve: Option<f64>,
}

/// `risk.model_reserve.dispersion` (Q9 part 2, ruling G-36).
pub fn model_reserve(prices: &[(String, f64)], reference: &str) -> Result<Reserve> {
    if prices.len() < 2 {
        return fail("E_INPUT", "prices needs at least two models");
    }
    for (_, p) in prices {
        crate::error::finite("prices", p)?;
    }
    let Some(pref) = prices.iter().find(|p| p.0 == reference).map(|p| p.1) else {
        return fail("E_INPUT", "reference_model must be a key of prices");
    };
    let mut sorted: Vec<&(String, f64)> = prices.iter().collect();
    sorted.sort_by(|a, b| a.0.cmp(&b.0));
    #[allow(clippy::cast_precision_loss)]
    let mean = prices.iter().map(|p| p.1).sum::<f64>() / prices.len() as f64;
    let hi = prices.iter().map(|p| p.1).fold(f64::NEG_INFINITY, f64::max);
    let lo = prices.iter().map(|p| p.1).fold(f64::INFINITY, f64::min);
    let mut worst = (sorted[0].0.clone(), -1.0);
    for (name, p) in sorted {
        let d = (p - pref).abs();
        if d > worst.1 {
            worst = (name.clone(), d);
        }
    }
    Ok(Reserve {
        mean,
        range: hi - lo,
        half_range: (hi - lo) / 2.0,
        reserve: worst.1,
        worst_model: worst.0,
        relative_reserve: (pref != 0.0).then(|| worst.1 / pref.abs()),
    })
}
