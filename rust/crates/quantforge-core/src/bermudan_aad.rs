//! Reverse-mode (adjoint) ladder of the G-18 Bermudan scheme (`06-risk/aad-core.md`, Q3b,
//! rulings G-9, G-35).
//!
//! The adjoint is written by hand, operation by operation, for exactly the arithmetic of the
//! forward pass: the curve's log-linear interpolation, `alpha(t)`, the grid, the implicit
//! tridiagonal steps with their folded boundaries, the exercise values and the `max` taken on
//! its active branch. The forward pass keeps each step's solution so the reverse sweep needs no
//! recomputation; the cost is about two pricings.
use crate::error::Result;
use crate::shortrate::{FdGrid, HwCurve, SwapLeg};

/// Price and ladder per [`bermudan_ladder`].
#[derive(Debug, Clone, PartialEq)]
pub struct Ladder {
    /// Price for the notional.
    pub price: f64,
    /// `dV/dP_k` for each curve pillar, in input order.
    pub d_discount_factors: Vec<f64>,
    /// `dV/da`.
    pub d_mean_reversion: f64,
    /// `dV/dsigma`.
    pub d_sigma: f64,
}

/// Reverse-mode accumulators: `l` over the curve logs (index 0 is the fixed `(0, 1)` node).
struct Bar {
    l: Vec<f64>,
    a: f64,
    s: f64,
    h: f64,
}

/// `f(0, t)` and `ln P(0, t)` with their adjoints into the curve logs.
struct CurveAd<'a> {
    c: &'a HwCurve,
}

impl CurveAd<'_> {
    fn fwd(&self, t: f64) -> f64 {
        self.c.forward(t)
    }
    fn lnd(&self, t: f64) -> f64 {
        self.c.ln_discount(t)
    }
    /// Adds `fbar * df/dl + dbar * dlnD/dl` at `t`.
    fn back(&self, t: f64, fbar: f64, dbar: f64, b: &mut Bar) {
        let (i, t0, t1) = self.c.segment(t);
        let w = t1 - t0;
        // f = -(l_{i+1} - l_i)/w ; lnD = l_i - f (t - t0)
        let u = t - t0;
        b.l[i] += fbar / w + dbar * (1.0 - u / w);
        b.l[i + 1] += -fbar / w + dbar * (u / w);
    }
}

/// `alpha(t) = f(t) + sigma^2/(2a^2) e^2`, `e = 1 - e^{-at}`.
fn alpha(c: &CurveAd, a: f64, s: f64, t: f64) -> f64 {
    let e = -(-a * t).exp_m1();
    c.fwd(t) + s * s / (2.0 * a * a) * e * e
}

fn alpha_back(c: &CurveAd, a: f64, s: f64, t: f64, abar: f64, b: &mut Bar) {
    let e = -(-a * t).exp_m1();
    let de_da = t * (-a * t).exp();
    c.back(t, abar, 0.0, b);
    b.s += abar * s * e * e / (a * a);
    b.a += abar * s * s / 2.0 * (2.0 * e * de_da / (a * a) - 2.0 * e * e / (a * a * a));
}

/// Swap exercise value `phi (1 - P_n - K sum tau_j P_j)` at `t` for each short rate in `r`
/// (`r_i = x_i + alpha`), and its reverse sweep.
struct Exercise<'a> {
    c: &'a CurveAd<'a>,
    a: f64,
    s: f64,
    pay: &'a [f64],
    k: f64,
    phi: f64,
}

impl Exercise<'_> {
    fn legs(&self, t: f64) -> Vec<(f64, f64, f64)> {
        // (T_j, tau_j, B_j) for payments after t
        let mut prev = t;
        let mut v = Vec::new();
        for tj in self.pay.iter().filter(|tj| **tj > t) {
            let b = -(-self.a * (tj - t)).exp_m1() / self.a;
            v.push((*tj, tj - prev, b));
            prev = *tj;
        }
        v
    }

    fn cfac(&self, t: f64) -> f64 {
        self.s * self.s / (4.0 * self.a) * (-2.0 * self.a * t).exp_m1()
    }

    fn values(&self, t: f64, r: &[f64]) -> Vec<f64> {
        let legs = self.legs(t);
        let (lt, ft, cf) = (self.c.lnd(t), self.c.fwd(t), self.cfac(t));
        let lna: Vec<f64> = legs
            .iter()
            .map(|(tj, _, bj)| self.c.lnd(*tj) - lt + bj * ft + cf * bj * bj)
            .collect();
        let n = legs.len();
        r.iter()
            .map(|ri| {
                let mut fixed = 0.0;
                let mut last = 1.0;
                for (j, (_, tau, bj)) in legs.iter().enumerate() {
                    let p = (lna[j] - bj * ri).exp();
                    fixed += tau * p;
                    if j + 1 == n {
                        last = p;
                    }
                }
                self.phi * (1.0 - last - self.k * fixed)
            })
            .collect()
    }

    /// Given `ebar[i]` (adjoint of each node's value), adds into `rbar[i]` and `b`.
    fn back(&self, t: f64, r: &[f64], ebar: &[f64], rbar: &mut [f64], b: &mut Bar) {
        let legs = self.legs(t);
        let (lt, ft, cf) = (self.c.lnd(t), self.c.fwd(t), self.cfac(t));
        let n = legs.len();
        let mut lnabar = vec![0.0; n];
        let mut bbar = vec![0.0; n];
        for (i, ri) in r.iter().enumerate() {
            if ebar[i] == 0.0 {
                continue;
            }
            for (j, (tj, tau, bj)) in legs.iter().enumerate() {
                let lna = self.c.lnd(*tj) - lt + bj * ft + cf * bj * bj;
                let p = (lna - bj * ri).exp();
                let mut pbar = -self.phi * ebar[i] * self.k * tau;
                if j + 1 == n {
                    pbar -= self.phi * ebar[i];
                }
                let q = pbar * p; // adjoint of the exponent
                lnabar[j] += q;
                bbar[j] -= q * ri;
                rbar[i] -= q * bj;
            }
        }
        let (a, s) = (self.a, self.s);
        let mut fbar_t = 0.0;
        let mut lbar_t = 0.0;
        let mut cbar = 0.0;
        for (j, (tj, _, bj)) in legs.iter().enumerate() {
            let q = lnabar[j];
            self.c.back(*tj, 0.0, q, b);
            lbar_t -= q;
            fbar_t += q * bj;
            cbar += q * bj * bj;
            let bb = bbar[j] + q * (ft + 2.0 * cf * bj);
            let u = tj - t;
            b.a += bb * (u * (-a * u).exp() - bj) / a;
        }
        self.c.back(t, fbar_t, lbar_t, b);
        let g = (-2.0 * a * t).exp_m1();
        b.s += cbar * 2.0 * cf / s;
        b.a += cbar * s * s / 4.0 * ((-2.0 * t * (-2.0 * a * t).exp()) * a - g) / (a * a);
    }
}

/// One recorded implicit step: its time, size, solution and LU factors.
struct Step {
    t: f64,
    dt: f64,
    u: Vec<f64>,
    cp: Vec<f64>,
    m: Vec<f64>,
}

/// One exercise knot: the continuation value before the `max` and the exercise values.
struct Knot {
    t: f64,
    before: Vec<f64>,
    exv: Vec<f64>,
}

/// `rates.shortrate.bermudan_ladder`: price and `dV/d(P_k, a, sigma)` of the G-18 scheme.
pub fn bermudan_ladder(
    curve: &HwCurve,
    a: f64,
    sigma: f64,
    swap: &SwapLeg,
    exercise: &[f64],
    grid: FdGrid,
) -> Result<Ladder> {
    crate::shortrate::check_bermudan(curve, a, sigma, swap, exercise, grid)?;
    let c = CurveAd { c: curve };
    let ex = Exercise {
        c: &c,
        a,
        s: sigma,
        pay: swap.pay,
        k: swap.fixed_rate,
        phi: if swap.payer { 1.0 } else { -1.0 },
    };
    let nx = usize::try_from(grid.nx).unwrap_or(5);
    let tm = exercise[exercise.len() - 1];
    let gq = -(-2.0 * a * tm).exp_m1() / (2.0 * a);
    let sx = sigma * gq.sqrt();
    let h = grid.width * sx;
    #[allow(clippy::cast_precision_loss)]
    let delta = 2.0 / (nx - 1) as f64; // dx = h delta
    #[allow(clippy::cast_precision_loss)]
    let xi: Vec<f64> = (0..nx).map(|i| -1.0 + i as f64 * delta).collect();
    let dx = h * delta;
    let x: Vec<f64> = (0..nx).map(|i| -h + (i as f64) * dx).collect();
    let rates = |t: f64| -> Vec<f64> {
        let al = alpha(&c, a, sigma, t);
        x.iter().map(|xi| xi + al).collect()
    };
    // Forward pass. Steps are recorded as (t, dt, solution after the step).
    #[allow(clippy::cast_precision_loss)]
    let spy = grid.steps_per_year as f64;
    let mut knots = vec![0.0];
    knots.extend_from_slice(exercise);
    let ex_m = ex.values(tm, &rates(tm));
    let mut v: Vec<f64> = ex_m.iter().map(|e| e.max(0.0)).collect();
    let diff = sigma * sigma / (2.0 * dx * dx);
    let adv: Vec<f64> = (0..nx).map(|i| a * x[i] / (2.0 * dx)).collect();
    let mut steps: Vec<Step> = Vec::new();
    let mut knot_log: Vec<Knot> = Vec::new();
    let (mut lo, mut di, mut up) = (vec![0.0; nx], vec![0.0; nx], vec![0.0; nx]);
    for k in (1..knots.len()).rev() {
        let (ta, tb) = (knots[k - 1], knots[k]);
        #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
        let n = ((spy * (tb - ta)).ceil() as usize).max(1);
        #[allow(clippy::cast_precision_loss)]
        let dt = (tb - ta) / n as f64;
        for j in 1..=n {
            #[allow(clippy::cast_precision_loss)]
            let t = if j == n { ta } else { tb - j as f64 * dt };
            let al = alpha(&c, a, sigma, t);
            for i in 1..nx - 1 {
                lo[i] = -dt * (diff + adv[i]);
                di[i] = 1.0 + dt * (2.0 * diff + x[i] + al);
                up[i] = -dt * (diff - adv[i]);
            }
            di[1] += 2.0 * lo[1];
            up[1] -= lo[1];
            di[nx - 2] += 2.0 * up[nx - 2];
            lo[nx - 2] -= up[nx - 2];
            let mut cp = vec![0.0; nx];
            let mut dp = vec![0.0; nx];
            let mut mm = vec![0.0; nx];
            mm[1] = di[1];
            cp[1] = up[1] / di[1];
            dp[1] = v[1] / di[1];
            for i in 2..nx - 1 {
                mm[i] = di[i] - lo[i] * cp[i - 1];
                cp[i] = up[i] / mm[i];
                dp[i] = (v[i] - lo[i] * dp[i - 1]) / mm[i];
            }
            v[nx - 2] = dp[nx - 2];
            for i in (1..nx - 2).rev() {
                v[i] = dp[i] - cp[i] * v[i + 1];
            }
            v[0] = 2.0 * v[1] - v[2];
            v[nx - 1] = 2.0 * v[nx - 2] - v[nx - 3];
            steps.push(Step {
                t,
                dt,
                u: v.clone(),
                cp,
                m: mm,
            });
        }
        if k >= 2 {
            let exv = ex.values(ta, &rates(ta));
            let before = v.clone();
            for (vi, e) in v.iter_mut().zip(&exv) {
                *vi = vi.max(*e);
            }
            knot_log.push(Knot { t: ta, before, exv });
        }
    }
    let centre = (nx - 1) / 2;
    let price = swap.notional * v[centre];

    // Reverse sweep.
    let mut b = Bar {
        l: vec![0.0; curve.pillars() + 1],
        a: 0.0,
        s: 0.0,
        h: 0.0,
    };
    let mut vbar = vec![0.0; nx];
    vbar[centre] = swap.notional;
    let mut xbar = vec![0.0; nx];
    let mut diffbar = 0.0;
    let mut advbar = vec![0.0; nx];
    let mut si = steps.len();
    let mut ki = knot_log.len();
    // Walk the knots in the same backward order, but reversed.
    let mut counts = Vec::new();
    for k in (1..knots.len()).rev() {
        let (ta, tb) = (knots[k - 1], knots[k]);
        #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
        let n = ((spy * (tb - ta)).ceil() as usize).max(1);
        counts.push((n, k >= 2));
    }
    for (n, has_knot) in counts.iter().rev() {
        if *has_knot {
            ki -= 1;
            let kn = &knot_log[ki];
            let mut ebar = vec![0.0; nx];
            for i in 0..nx {
                if kn.exv[i] > kn.before[i] {
                    ebar[i] = vbar[i];
                    vbar[i] = 0.0;
                }
            }
            let r = rates(kn.t);
            let mut rbar = vec![0.0; nx];
            ex.back(kn.t, &r, &ebar, &mut rbar, &mut b);
            let albar: f64 = rbar.iter().sum();
            for i in 0..nx {
                xbar[i] += rbar[i];
            }
            alpha_back(&c, a, sigma, kn.t, albar, &mut b);
        }
        for _ in 0..*n {
            si -= 1;
            let st = &steps[si];
            let (t, dt) = (st.t, st.dt);
            // boundaries: v0 = 2 v1 - v2, vN = 2 v(N-1) - v(N-2)
            let mut ubar = vbar.clone();
            ubar[1] += 2.0 * ubar[0];
            ubar[2] -= ubar[0];
            ubar[nx - 2] += 2.0 * ubar[nx - 1];
            ubar[nx - 3] -= ubar[nx - 1];
            // Solve A^T y = ubar on interior rows using the stored LU factors:
            // A = L U with U unit upper (cp) and L lower (m on diagonal, lo below).
            // A^T y = g: U^T z = g (forward), L^T y = z (backward).
            let mut z = vec![0.0; nx];
            z[1] = ubar[1];
            for i in 2..nx - 1 {
                z[i] = ubar[i] - st.cp[i - 1] * z[i - 1];
            }
            let lo_mod = |i: usize| -> f64 {
                let lo_i = -dt * (diff + adv[i]);
                if i == nx - 2 {
                    lo_i - (-dt * (diff - adv[i]))
                } else {
                    lo_i
                }
            };
            let mut y = vec![0.0; nx];
            y[nx - 2] = z[nx - 2] / st.m[nx - 2];
            for i in (1..nx - 2).rev() {
                y[i] = (z[i] - lo_mod(i + 1) * y[i + 1]) / st.m[i];
            }
            // Matrix adjoints: Abar_ij = -y_i u_j on the modified entries.
            let u = &st.u;
            for i in 1..nx - 1 {
                let dbar_m = -y[i] * u[i];
                let lbar_m = if i > 1 { -y[i] * u[i - 1] } else { 0.0 };
                let ubar_m = if i < nx - 2 { -y[i] * u[i + 1] } else { 0.0 };
                // undo the boundary folding
                let (mut lob, dib, mut upb) = (lbar_m, dbar_m, ubar_m);
                if i == 1 {
                    lob += 2.0 * dbar_m - ubar_m;
                }
                if i == nx - 2 {
                    upb += 2.0 * dbar_m - lbar_m;
                }
                diffbar -= dt * lob;
                advbar[i] -= dt * lob;
                diffbar += 2.0 * dt * dib;
                xbar[i] += dt * dib;
                let albar = dt * dib;
                alpha_back(&c, a, sigma, t, albar, &mut b);
                diffbar -= dt * upb;
                advbar[i] += dt * upb;
            }
            vbar = vec![0.0; nx];
            vbar[1..(nx - 1)].copy_from_slice(&y[1..(nx - 1)]);
        }
    }
    // Terminal: v = max(ex, 0).
    let mut ebar = vec![0.0; nx];
    for i in 0..nx {
        if ex_m[i] > 0.0 {
            ebar[i] = vbar[i];
        }
    }
    let r = rates(tm);
    let mut rbar = vec![0.0; nx];
    ex.back(tm, &r, &ebar, &mut rbar, &mut b);
    let albar: f64 = rbar.iter().sum();
    for i in 0..nx {
        xbar[i] += rbar[i];
    }
    alpha_back(&c, a, sigma, tm, albar, &mut b);
    // Grid: x_i = h xi_i, dx = h delta, diff = sigma^2/(2 h^2 delta^2), adv_i = a xi_i/(2 delta).
    for i in 0..nx {
        b.h += xbar[i] * xi[i];
        b.a += advbar[i] * xi[i] / (2.0 * delta);
    }
    b.s += diffbar * sigma / (dx * dx);
    b.h -= diffbar * sigma * sigma / (dx * dx * h);
    // h = width sigma sqrt(G(a)), G = -expm1(-2 a tm)/(2a)
    let sxbar = b.h * grid.width;
    b.s += sxbar * gq.sqrt();
    let dg = (tm * (-2.0 * a * tm).exp() - gq) / a;
    b.a += sxbar * sigma / (2.0 * gq.sqrt()) * dg;
    let d_df: Vec<f64> = (1..b.l.len())
        .map(|k| b.l[k] / curve.pillar_df(k))
        .collect();
    Ok(Ladder {
        price,
        d_discount_factors: d_df,
        d_mean_reversion: b.a,
        d_sigma: b.s,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::shortrate::bermudan_swaption;

    /// AAD against the Q3a Richardson reference, `|AAD - ref| <= 1e-10 + 1e-8 |ref|` per
    /// unit notional (G-9).
    #[test]
    fn ladder_matches_richardson_bumps() {
        let times = [0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0];
        let dfs = [0.98, 0.96, 0.925, 0.89, 0.82, 0.76, 0.68];
        let pay = [2.0, 3.0, 4.0];
        let ex = [1.0, 2.0];
        let swap = SwapLeg {
            start: 1.0,
            pay: &pay,
            fixed_rate: 0.04,
            payer: true,
            notional: 1.0,
        };
        let grid = FdGrid {
            nx: 41,
            steps_per_year: 20,
            width: 6.0,
        };
        let (a, s) = (0.05, 0.01);
        let c = HwCurve::new(&times, &dfs).unwrap();
        let l = bermudan_ladder(&c, a, s, &swap, &ex, grid).unwrap();
        let p0 = bermudan_swaption(&c, a, s, &swap, &ex, grid).unwrap();
        assert!((l.price - p0).abs() < 1e-12);
        let price = |d: &[f64], a: f64, s: f64| {
            let c = HwCurve::new(&times, d).unwrap();
            bermudan_swaption(&c, a, s, &swap, &ex, grid).unwrap()
        };
        let rich = |f: &dyn Fn(f64) -> f64, x: f64| {
            let d = |h: f64| (f(x * (1.0 + h)) - f(x * (1.0 - h))) / (2.0 * h * x);
            (4.0 * d(5e-5) - d(1e-4)) / 3.0
        };
        let close = |aad: f64, r: f64| (aad - r).abs() <= 1e-10 + 1e-8 * r.abs();
        assert!(close(l.d_sigma, rich(&|x| price(&dfs, a, x), s)), "sigma");
        assert!(
            close(l.d_mean_reversion, rich(&|x| price(&dfs, x, s), a)),
            "a"
        );
        for k in 0..dfs.len() {
            let f = |x: f64| {
                let mut d = dfs.to_vec();
                d[k] = x;
                price(&d, a, s)
            };
            let r = rich(&f, dfs[k]);
            assert!(
                close(l.d_discount_factors[k], r),
                "pillar {k}: {} vs {r}",
                l.d_discount_factors[k]
            );
        }
    }

    /// G-9 performance acceptance as a test (R6-16): median of 21 timed runs after 5 warm-ups
    /// of (a) one price and (b) price plus full ladder, same thread, on `aadladder_g-0001`'s
    /// inputs. Prints the measured ratio (CI logs record it) and asserts `<= 5`. The Actions
    /// runner result is the one that counts; a loaded laptop can be slower.
    #[test]
    fn g9_ladder_cost_ratio_at_most_five() {
        use std::hint::black_box;
        use std::time::Instant;
        let median = |f: &dyn Fn()| {
            for _ in 0..5 {
                f();
            }
            let mut t: Vec<f64> = (0..21)
                .map(|_| {
                    let s = Instant::now();
                    f();
                    s.elapsed().as_secs_f64()
                })
                .collect();
            t.sort_by(f64::total_cmp);
            t[10]
        };
        let times = [
            0.498_630_136_986_301_4,
            1.0,
            2.0,
            3.0,
            5.002_739_726_027_397,
            7.005_479_452_054_795,
            10.005_479_452_054_795,
            15.010_958_904_109_59,
            20.013_698_630_136_986,
            30.019_178_082_191_782,
        ];
        let dfs = [
            0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332,
        ];
        let curve = HwCurve::new(&times, &dfs).unwrap();
        let pay = [2.0, 3.0, 4.0, 5.0, 6.0];
        let swap = SwapLeg {
            start: 1.0,
            pay: &pay,
            fixed_rate: 0.039_462,
            payer: true,
            notional: 1e6,
        };
        let ex = [1.0, 2.0, 3.0, 4.0, 5.0];
        let grid = FdGrid {
            nx: 101,
            steps_per_year: 50,
            width: 6.0,
        };
        let a = median(&|| {
            black_box(bermudan_swaption(&curve, 0.05, 0.01, &swap, &ex, grid).unwrap());
        });
        let b = median(&|| {
            black_box(bermudan_ladder(&curve, 0.05, 0.01, &swap, &ex, grid).unwrap());
        });
        let ratio = b / a;
        println!(
            "G-9 ladder cost ratio: {ratio:.3} (price {a:.6e} s, ladder {b:.6e} s; pass <= 5)"
        );
        assert!(ratio <= 5.0, "G-9 ratio {ratio:.3} above 5");
    }
}
