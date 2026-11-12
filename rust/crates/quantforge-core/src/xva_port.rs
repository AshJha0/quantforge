//! Exposure profiles of a swap netting set under Hull-White in LGM coordinates, by exact
//! one-dimensional Gaussian integration (`06-risk/xva-exposure-portfolio.md`, ruling G-42).
use crate::error::{Result, fail};
use crate::shortrate::{HwCurve, Model, SwapLeg, check_payments, zcb};
use crate::stats::normal_cdf;

/// Output of [`portfolio_hw`].
#[derive(Debug, Clone, PartialEq)]
pub struct PortfolioExposure {
    /// `E[max(f, 0)]` per exposure time.
    pub discounted_ee: Vec<f64>,
    /// `E[min(f, 0)]` per exposure time.
    pub discounted_ene: Vec<f64>,
    /// One profile per requested quantile, in input order.
    pub pfe: Vec<Vec<f64>>,
    /// Time-weighted average of the EE.
    pub epe: f64,
    /// Bucketed CVA (G-16).
    pub cva: f64,
}

/// Half-width of the integration range in standard deviations of `x(t)`.
const ZMAX: f64 = 16.0;
/// Scan of the analytic `f'` used to bracket the critical points of `f` (ruling R6-5.5: at least
/// 6,001 points over +-12 sd; this scan is 8,001 points over +-16 sd, step 0.004 <= 24/6000).
const NGRID: usize = 8000;

/// Deflated value of the netting set at `t` as a function of the standard normal `z`.
/// One trade as `(sign x notional, fixed rate, [(tau, ln P(0,T) - ln P(0,t), H(T))])`.
type Leg = (f64, f64, Vec<(f64, f64, f64)>);

struct Deflated {
    /// Per trade: sign times notional, fixed rate, and per remaining payment the accrual,
    /// `ln P(0,T) - ln P(0,t)` and `H(T)`.
    legs: Vec<Leg>,
    lp0t: f64,
    ht: f64,
    zeta: f64,
    /// `-ZMAX`, the critical points of `value` in between, and `ZMAX` (R6-5.5): `value` is
    /// monotone between consecutive knots.
    knots: Vec<f64>,
}

#[allow(clippy::cast_precision_loss)]
fn zgrid(k: usize) -> f64 {
    -ZMAX + k as f64 * 2.0 * ZMAX / NGRID as f64
}

impl Deflated {
    fn new(curve: &HwCurve, trades: &[SwapLeg], t: f64, a: f64, sigma: f64) -> Deflated {
        let h = |s: f64| -(-a * s).exp_m1() / a;
        let lp0t = curve.ln_discount(t);
        let legs = trades
            .iter()
            .map(|tr| {
                let mut prev = t;
                let mut v = Vec::new();
                for tj in tr.pay.iter().filter(|tj| **tj > t) {
                    v.push((tj - prev, curve.ln_discount(*tj) - lp0t, h(*tj)));
                    prev = *tj;
                }
                let sgn = if tr.payer { 1.0 } else { -1.0 };
                (sgn * tr.notional, tr.fixed_rate, v)
            })
            .collect();
        let zeta = sigma * sigma * (2.0 * a * t).exp_m1() / (2.0 * a);
        let mut d = Deflated {
            legs,
            lp0t,
            ht: h(t),
            zeta,
            knots: Vec::new(),
        };
        if zeta > 0.0 {
            d.knots = d.critical_knots();
        }
        d
    }

    fn value(&self, z: f64) -> f64 {
        let x = self.zeta.sqrt() * z;
        let ht = self.ht;
        let ln_num = ht * x + ht * ht * self.zeta / 2.0 - self.lp0t;
        let mut v = 0.0;
        for (sn, k, pays) in &self.legs {
            let mut fixed = 0.0;
            let mut last = 1.0;
            for (tau, lp, h_end) in pays {
                let p = (lp - (h_end - ht) * x - (h_end * h_end - ht * ht) * self.zeta / 2.0).exp();
                fixed += tau * p;
                last = p;
            }
            v += sn * (1.0 - last - k * fixed);
        }
        v * (-ln_num).exp()
    }

    /// Analytic `d value / dz`.
    fn slope(&self, z: f64) -> f64 {
        let sz = self.zeta.sqrt();
        let x = sz * z;
        let ht = self.ht;
        let ln_num = ht * x + ht * ht * self.zeta / 2.0 - self.lp0t;
        let (mut v, mut dv) = (0.0, 0.0);
        for (sn, k, pays) in &self.legs {
            let (mut fixed, mut dfixed, mut last, mut dlast) = (0.0, 0.0, 1.0, 0.0);
            for (tau, lp, h_end) in pays {
                let p = (lp - (h_end - ht) * x - (h_end * h_end - ht * ht) * self.zeta / 2.0).exp();
                let dp = -(h_end - ht) * p;
                fixed += tau * p;
                dfixed += tau * dp;
                last = p;
                dlast = dp;
            }
            v += sn * (1.0 - last - k * fixed);
            dv += sn * (-dlast - k * dfixed);
        }
        (dv - ht * v) * (-ln_num).exp() * sz
    }

    /// Bisection on `[lo, hi]` for a sign change of `g`, to the binary64 resolution.
    fn bisect(g: &dyn Fn(f64) -> f64, mut lo: f64, mut hi: f64) -> f64 {
        let neg_lo = g(lo) < 0.0;
        for _ in 0..200 {
            let m = 0.5 * (lo + hi);
            if m <= lo || m >= hi {
                break;
            }
            if (g(m) < 0.0) == neg_lo {
                lo = m;
            } else {
                hi = m;
            }
        }
        0.5 * (lo + hi)
    }

    /// R6-5.5: bracket the zeros of the analytic slope on the scan and refine each.
    fn critical_knots(&self) -> Vec<f64> {
        let mut out = vec![-ZMAX];
        let slope = |z: f64| self.slope(z);
        let mut prev = slope(zgrid(0));
        for k in 1..=NGRID {
            let cur = slope(zgrid(k));
            if prev * cur < 0.0 {
                out.push(Self::bisect(&slope, zgrid(k - 1), zgrid(k)));
            } else if cur == 0.0 && k < NGRID {
                out.push(zgrid(k));
            }
            prev = cur;
        }
        out.push(ZMAX);
        out
    }

    /// Points in `[-ZMAX, ZMAX]` where `value - y` changes sign: at most one per monotone
    /// piece between knots, found by bisection.
    fn roots(&self, y: f64) -> Vec<f64> {
        let mut out = Vec::new();
        let g = |z: f64| self.value(z) - y;
        for w in self.knots.windows(2) {
            let (g0, g1) = (g(w[0]), g(w[1]));
            if g0 == 0.0 {
                if w[0] > -ZMAX {
                    out.push(w[0]);
                }
            } else if g0 * g1 < 0.0 {
                out.push(Self::bisect(&g, w[0], w[1]));
            }
        }
        out
    }

    /// `P(value <= y)` under the standard normal.
    fn cdf(&self, y: f64) -> f64 {
        let mut cuts = vec![-ZMAX];
        cuts.extend(self.roots(y));
        cuts.push(ZMAX);
        let mut p = 0.0;
        for w in cuts.windows(2) {
            let m = 0.5 * (w[0] + w[1]);
            if self.value(m) <= y {
                let lo = if w[0] <= -ZMAX { 0.0 } else { normal_cdf(w[0]) };
                let hi = if w[1] >= ZMAX { 1.0 } else { normal_cdf(w[1]) };
                p += hi - lo;
            }
        }
        p
    }

    /// `(E[max(f, 0)], E[min(f, 0)])` by Gauss-Legendre on pieces split at the zeros of `f`.
    fn moments(&self) -> (f64, f64) {
        let rule = crate::integrate::gauss_legendre_rule(24);
        let mut cuts = vec![-ZMAX];
        cuts.extend(self.roots(0.0));
        cuts.push(ZMAX);
        let (mut pos, mut neg) = (0.0, 0.0);
        for w in cuts.windows(2) {
            #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
            let pieces = (((w[1] - w[0]) / 0.25).ceil() as usize).max(1);
            #[allow(clippy::cast_precision_loss)]
            let hlen = (w[1] - w[0]) / pieces as f64;
            let mut sum = 0.0;
            for k in 0..pieces {
                #[allow(clippy::cast_precision_loss)]
                let lo = w[0] + k as f64 * hlen;
                let (m, r) = (lo + hlen / 2.0, hlen / 2.0);
                for (x, wt) in &rule {
                    let z = m + r * x;
                    sum += wt * r * self.value(z) * crate::stats::normal_pdf(z);
                }
            }
            if sum >= 0.0 {
                pos += sum;
            } else {
                neg += sum;
            }
        }
        (pos, neg)
    }

    /// Smallest `y >= 0` with `P(max(f, 0) <= y) >= q`.
    fn pfe(&self, q: f64) -> f64 {
        if self.cdf(0.0) >= q {
            return 0.0;
        }
        let mut hi = self.knots.iter().map(|z| self.value(*z)).fold(0.0_f64, f64::max);
        let mut lo = 0.0;
        for _ in 0..200 {
            let m = 0.5 * (lo + hi);
            if m <= lo || m >= hi || hi - lo <= 1e-14 * hi {
                break;
            }
            if self.cdf(m) >= q {
                hi = m;
            } else {
                lo = m;
            }
        }
        hi
    }
}

/// `xva.exposure.portfolio_hw`: EE, ENE, PFE profiles, EPE and CVA of a netting set of swaps
/// with common reset dates, at reset dates before the last payment.
#[allow(clippy::too_many_arguments)]
pub fn portfolio_hw(
    curve: &HwCurve,
    a: f64,
    sigma: f64,
    trades: &[SwapLeg],
    exposure: &[f64],
    quantiles: &[f64],
    hazard: f64,
    recovery: f64,
) -> Result<PortfolioExposure> {
    zcb(&Model::HullWhite { a, sigma, curve }, 0.0, 0.0, 1.0)?;
    if trades.is_empty() {
        return fail("E_INPUT", "trades needs at least one swap");
    }
    // The set's reset grid is the union of the trades' reset dates; each trade must reset on
    // every grid date from its start to before its last payment (a common schedule, trades
    // may end at different dates).
    let mut grid: Vec<f64> = Vec::new();
    for tr in trades {
        crate::error::finite("trade", &[tr.start, tr.fixed_rate, tr.notional])?;
        if tr.start < 0.0 {
            return fail("E_DOMAIN", "start_years must not be negative");
        }
        check_payments(tr.start, tr.pay)?;
        grid.push(tr.start);
        grid.extend_from_slice(&tr.pay[..tr.pay.len() - 1]);
    }
    grid.sort_by(f64::total_cmp);
    grid.dedup();
    for tr in trades {
        let mut own = vec![tr.start];
        own.extend_from_slice(&tr.pay[..tr.pay.len() - 1]);
        let last = tr.pay[tr.pay.len() - 1];
        let want: Vec<f64> = grid
            .iter()
            .copied()
            .filter(|g| *g >= tr.start && *g < last)
            .collect();
        if own != want {
            return fail("E_INPUT", "the trades of the set need common reset dates");
        }
    }
    let resets = grid;
    crate::error::finite("exposure_times", &exposure)?;
    if exposure.len() > 10_000 {
        return fail("E_LIMIT", "at most 10,000 exposure times");
    }
    if exposure.is_empty()
        || exposure.windows(2).any(|w| w[1] <= w[0])
        || exposure.iter().any(|e| !resets.contains(e))
    {
        return fail(
            "E_INPUT",
            "exposure_times must be increasing reset dates before the last payment",
        );
    }
    crate::error::finite("pfe_quantiles", &quantiles)?;
    if quantiles.iter().any(|q| !(*q > 0.0 && *q < 1.0)) {
        return fail("E_DOMAIN", "pfe_quantiles must be in (0, 1)");
    }
    crate::error::finite("credit", &[hazard, recovery])?;
    if hazard < 0.0 || !(0.0..1.0).contains(&recovery) {
        return fail("E_DOMAIN", "hazard_rate >= 0 and recovery in [0, 1)");
    }
    let mut out = PortfolioExposure {
        discounted_ee: Vec::new(),
        discounted_ene: Vec::new(),
        pfe: vec![Vec::new(); quantiles.len()],
        epe: 0.0,
        cva: 0.0,
    };
    let mut prev = 0.0;
    for t in exposure {
        let d = Deflated::new(curve, trades, *t, a, sigma);
        let zeta = d.zeta;
        let (ee, ene) = if zeta == 0.0 {
            let v = d.value(0.0);
            (v.max(0.0), v.min(0.0))
        } else {
            d.moments()
        };
        for (k, q) in quantiles.iter().enumerate() {
            let p = if zeta == 0.0 {
                d.value(0.0).max(0.0)
            } else {
                d.pfe(*q)
            };
            out.pfe[k].push(p);
        }
        out.epe += ee * (t - prev);
        out.cva += ee * ((-hazard * prev).exp() - (-hazard * t).exp());
        out.discounted_ee.push(ee);
        out.discounted_ene.push(ene);
        prev = *t;
    }
    out.epe /= exposure[exposure.len() - 1];
    out.cva *= 1.0 - recovery;
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shortrate::swap_ee_hw;

    fn curve() -> HwCurve {
        HwCurve::new(
            &[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
            &[0.985, 0.97, 0.94, 0.85, 0.70, 0.33],
        )
        .unwrap()
    }

    #[test]
    fn single_swap_matches_jamshidian_and_pfe_order() {
        let c = curve();
        let pay = [1.0, 2.0, 3.0, 4.0, 5.0];
        let ex = [1.0, 2.0, 3.0, 4.0];
        let leg = SwapLeg {
            start: 0.0,
            pay: &pay,
            fixed_rate: 0.03,
            payer: true,
            notional: 1e7,
        };
        let r = portfolio_hw(
            &c,
            0.05,
            0.01,
            std::slice::from_ref(&leg),
            &ex,
            &[0.95, 0.99],
            0.02,
            0.4,
        )
        .unwrap();
        let (ee, _) = swap_ee_hw(&c, 0.05, 0.01, &leg, &ex, (None, None)).unwrap();
        for (a, b) in r.discounted_ee.iter().zip(&ee) {
            assert!((a - b).abs() < 1e-9 * b.abs().max(1.0), "{a} {b}");
        }
        for k in 0..ex.len() {
            assert!(r.pfe[1][k] >= r.pfe[0][k] && r.pfe[0][k] >= 0.0);
            assert!(r.discounted_ene[k] <= 0.0);
        }
        // Payer plus receiver at the same rate nets to zero exposure.
        let rec = SwapLeg {
            payer: false,
            ..leg.clone()
        };
        let z = portfolio_hw(&c, 0.05, 0.01, &[leg, rec], &ex, &[0.95], 0.02, 0.4).unwrap();
        assert!(z.discounted_ee.iter().all(|e| e.abs() < 1e-6));
    }

    /// The PFE meets its definition: `P(f <= PFE) = q` (continuous case) and nothing smaller
    /// does, including on the narrow flat top of a long payer (the 20-year swap at 17 years).
    #[test]
    fn pfe_is_the_q_quantile() {
        let c = curve();
        let pay: Vec<f64> = (1..=20).map(f64::from).collect();
        let leg = SwapLeg {
            start: 0.0,
            pay: &pay,
            fixed_rate: 0.039,
            payer: true,
            notional: 1e7,
        };
        for t in [1.0, 10.0, 17.0] {
            let d = Deflated::new(&c, std::slice::from_ref(&leg), t, 0.03, 0.01);
            for q in [0.95, 0.99] {
                let y = d.pfe(q);
                assert!(y > 0.0);
                assert!((d.cdf(y) - q).abs() < 1e-9, "t={t} q={q} cdf={}", d.cdf(y));
                assert!(d.cdf(y * (1.0 - 1e-9)) < q);
            }
        }
    }
}
