//! Stage E1: arbitrage checks on SVI surfaces, SSVI to SVI, local vol, forward vol, smile
//! dynamics and vol of vol (`arb-free-surfaces.md`, `local-and-forward-vol.md`, rulings E-A1 to
//! E-A8).
use crate::black::black;
use crate::error::{Result, fail};
use crate::stats::{normal_cdf, normal_pdf};
use crate::svi::{self, Svi};

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Slice {
    pub expiry_years: f64,
    pub svi: Svi,
}

/// The `slices` checks in spec order: empty or not increasing, then expiry, then SVI domain.
pub fn check_slices(slices: &[Slice]) -> Result<()> {
    if slices.is_empty()
        || slices
            .windows(2)
            .any(|w| w[1].expiry_years <= w[0].expiry_years)
    {
        return fail(
            "E_INPUT",
            "slices must be non-empty with strictly increasing expiries",
        );
    }
    if slices
        .iter()
        .any(|s| s.expiry_years.is_nan() || s.expiry_years <= 0.0)
    {
        return fail("E_DOMAIN", "expiry_years must be above 0");
    }
    slices.iter().try_for_each(|s| s.svi.check())
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Side {
    Left,
    Right,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WingKind {
    Lee,
    Calendar,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Check {
    pub butterfly: Vec<(usize, usize)>,
    pub calendar: Vec<(usize, usize)>,
    pub wings: Vec<(usize, Side, WingKind)>,
}

impl Check {
    pub fn arbitrage_free(&self) -> bool {
        self.butterfly.is_empty() && self.calendar.is_empty() && self.wings.is_empty()
    }
}

/// `(slope, constant)` of each wing asymptote, in binary64 as written (ruling E-A2).
fn wings(p: &Svi) -> [(f64, f64); 2] {
    [
        (p.b * (1.0 - p.rho), p.a + p.b * (1.0 - p.rho) * p.m),
        (p.b * (1.0 + p.rho), p.a - p.b * (1.0 + p.rho) * p.m),
    ]
}

/// Strict comparisons with no tolerance (ruling E-A1). `slices` must already be checked.
pub fn surface_check(slices: &[Slice], k: &[f64]) -> Result<Check> {
    if k.is_empty() || k.windows(2).any(|w| w[1] <= w[0]) {
        return fail(
            "E_INPUT",
            "log_moneyness must be non-empty and strictly increasing",
        );
    }
    let mut c = Check::default();
    for (j, s) in slices.iter().enumerate() {
        for (i, &x) in k.iter().enumerate() {
            if s.svi.g(x) < 0.0 {
                c.butterfly.push((j, i));
            }
        }
    }
    for j in 1..slices.len() {
        for (i, &x) in k.iter().enumerate() {
            if slices[j].svi.w(x) < slices[j - 1].svi.w(x) {
                c.calendar.push((j, i));
            }
        }
    }
    for (j, s) in slices.iter().enumerate() {
        let now = wings(&s.svi);
        for (side, (slope, _)) in [Side::Left, Side::Right].into_iter().zip(now) {
            // `>= 2`: at slope 2, d+ no longer tends to -inf (ruling E-A15).
            if slope >= 2.0 {
                c.wings.push((j, side, WingKind::Lee));
            }
        }
        if j >= 1 {
            let before = wings(&slices[j - 1].svi);
            for (side, ((s1, c1), (s0, c0))) in [Side::Left, Side::Right]
                .into_iter()
                .zip(now.into_iter().zip(before))
            {
                if s1 < s0 || (s1 == s0 && c1 < c0) {
                    c.wings.push((j, side, WingKind::Calendar));
                }
            }
        }
    }
    Ok(c)
}

/// One SSVI slice as raw SVI ([GJ14] section 3).
pub fn ssvi_to_svi(rho: f64, eta: f64, gamma: f64, theta: f64) -> Result<Svi> {
    let bad = |x: f64| x.is_nan();
    if bad(rho)
        || rho.abs() >= 1.0
        || bad(eta)
        || eta <= 0.0
        || bad(gamma)
        || gamma <= 0.0
        || gamma > 1.0
        || bad(theta)
        || theta <= 0.0
    {
        return fail("E_DOMAIN", "ssvi parameters are out of domain");
    }
    let phi = svi::ssvi_phi(theta, eta, gamma);
    Ok(Svi {
        a: theta * (1.0 - rho * rho) / 2.0,
        b: theta * phi / 2.0,
        rho,
        m: -rho / phi,
        sigma: (1.0 - rho * rho).sqrt() / phi,
    })
}

#[derive(Debug, Clone, PartialEq)]
pub struct SurfaceFit {
    pub slices: Vec<Slice>,
    pub rmse: Vec<f64>,
    pub check: Check,
}

/// Each row fitted alone by the stage C rule, then checked; the fit does not repair arbitrage
/// (ruling E-A3).
pub fn fit_surface(expiries: &[f64], k: &[f64], w: &[Vec<f64>]) -> Result<SurfaceFit> {
    if expiries.is_empty() || expiries.windows(2).any(|p| p[1] <= p[0]) {
        return fail("E_INPUT", "expiry_years must strictly increase");
    }
    if w.len() != expiries.len() {
        return fail("E_INPUT", "one total_variance row per expiry");
    }
    let mut slices = Vec::with_capacity(w.len());
    let mut rmse = Vec::with_capacity(w.len());
    for (&t, row) in expiries.iter().zip(w) {
        let f = svi::calibrate(k, row, None)?;
        slices.push(Slice {
            expiry_years: t,
            svi: f.svi,
        });
        rmse.push(f.rmse);
    }
    check_slices(&slices)?;
    let check = surface_check(&slices, k)?;
    Ok(SurfaceFit {
        slices,
        rmse,
        check,
    })
}

/// `(w, w_k, w_kk, w_T)` at `(t, k)` by ruling E-A4.
pub fn surface_at(slices: &[Slice], t: f64, k: f64) -> (f64, f64, f64, f64) {
    let n = slices.len();
    let at = |j: usize| {
        let p = &slices[j].svi;
        (p.w(k), p.w1(k), p.w2(k))
    };
    if n == 1 || t < slices[0].expiry_years || t >= slices[n - 1].expiry_years {
        let j = if t < slices[0].expiry_years { 0 } else { n - 1 };
        let (w, w1, w2) = at(j);
        let tj = slices[j].expiry_years;
        return (w * t / tj, w1 * t / tj, w2 * t / tj, w / tj);
    }
    let j = slices.partition_point(|s| s.expiry_years <= t) - 1;
    let (t0, t1) = (slices[j].expiry_years, slices[j + 1].expiry_years);
    let l = (t - t0) / (t1 - t0);
    let (a, b) = (at(j), at(j + 1));
    let mix = |x: f64, y: f64| (1.0 - l) * x + l * y;
    (
        mix(a.0, b.0),
        mix(a.1, b.1),
        mix(a.2, b.2),
        (b.0 - a.0) / (t1 - t0),
    )
}

/// Gatheral's `g` for a general total variance and its `k` derivatives.
pub fn density(k: f64, w: f64, wk: f64, wkk: f64) -> f64 {
    let u = 1.0 - k * wk / (2.0 * w);
    u * u - (wk * wk / 4.0) * (1.0 / w + 0.25) + wkk / 2.0
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct LocalVol {
    pub total_variance: Vec<f64>,
    pub implied_vol: Vec<f64>,
    pub local_vol: Vec<f64>,
}

/// Dupire in total-variance form; any point with `w_T <= 0` or `g <= 0` is `E_ARBITRAGE`.
pub fn dupire(slices: &[Slice], points: &[(f64, f64)]) -> Result<LocalVol> {
    check_slices(slices)?;
    if points.is_empty() {
        return fail("E_INPUT", "at least 1 point is required");
    }
    if points.iter().any(|p| p.0.is_nan() || p.0 <= 0.0) {
        return fail("E_DOMAIN", "expiry_years must be above 0");
    }
    let mut out = LocalVol::default();
    for &(t, k) in points {
        let (w, _, _, _) = surface_at(slices, t, k);
        let lv = local_variance(slices, t, k)?;
        out.total_variance.push(w);
        out.implied_vol.push((w / t).sqrt());
        out.local_vol.push(lv.sqrt());
    }
    Ok(out)
}

/// Dupire local variance `w_T / g` at `(t, k)`; `w_T <= 0` or `g <= 0` is `E_ARBITRAGE`.
/// `slices` must already be checked.
pub fn local_variance(slices: &[Slice], t: f64, k: f64) -> Result<f64> {
    let (w, wk, wkk, wt) = surface_at(slices, t, k);
    let g = density(k, w, wk, wkk);
    if wt.is_nan() || wt <= 0.0 {
        return fail(
            "E_ARBITRAGE",
            "total variance does not increase in time (calendar)",
        );
    }
    if g.is_nan() || g <= 0.0 {
        return fail("E_ARBITRAGE", "negative density (butterfly)");
    }
    Ok(wt / g)
}

/// Forward vols between consecutive expiries; a zero forward variance gives 0 (ruling E-A5).
pub fn forward_vols(t: &[f64], v: &[f64]) -> Result<Vec<f64>> {
    if t.is_empty() || t.len() != v.len() || t.windows(2).any(|p| p[1] <= p[0]) {
        return fail(
            "E_INPUT",
            "expiry_years must strictly increase, with one vol each",
        );
    }
    if t[0].is_nan() || t[0] <= 0.0 || v.iter().any(|x| x.is_nan() || *x <= 0.0) {
        // A first expiry at or below 0 is E_DOMAIN (ruling E-A36).
        return fail("E_DOMAIN", "expiries and vols must be above 0");
    }
    let mut out = vec![v[0]];
    for i in 1..t.len() {
        let x = (v[i] * v[i] * t[i] - v[i - 1] * v[i - 1] * t[i - 1]) / (t[i] - t[i - 1]);
        if x < 0.0 {
            return fail("E_ARBITRAGE", "total variance falls between expiries");
        }
        out.push(x.sqrt());
    }
    Ok(out)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Rule {
    StickyStrike,
    StickyDelta,
}

pub struct Dynamics<'a> {
    pub svi: Svi,
    pub expiry_years: f64,
    pub spot: f64,
    pub spot_shifted: f64,
    pub rate: f64,
    pub dividend_yield: f64,
    pub strikes: &'a [f64],
    pub rule: Rule,
    pub call: bool,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct DynamicsOut {
    pub vols_base: Vec<f64>,
    pub vols_shifted: Vec<f64>,
    pub prices_base: Vec<f64>,
    pub prices_shifted: Vec<f64>,
    pub deltas: Vec<f64>,
}

pub fn smile_dynamics(x: &Dynamics) -> Result<DynamicsOut> {
    if x.strikes.is_empty() {
        return fail("E_INPUT", "at least 1 strike is required");
    }
    x.svi.check()?;
    let pos = |v: f64| v > 0.0;
    let scalars = [x.expiry_years, x.spot, x.spot_shifted];
    if !scalars.iter().chain(x.strikes).all(|&v| pos(v)) {
        return fail("E_DOMAIN", "expiry, spots and strikes must be above 0");
    }
    let t = x.expiry_years;
    let (d, qd) = ((-x.rate * t).exp(), (-x.dividend_yield * t).exp());
    let growth = ((x.rate - x.dividend_yield) * t).exp();
    let (f0, f1) = (x.spot * growth, x.spot_shifted * growth);
    let vol = |k: f64| (x.svi.w(k) / t).sqrt();
    let mut o = DynamicsOut::default();
    for &strike in x.strikes {
        let k0 = (strike / f0).ln();
        let v0 = vol(k0);
        let v1 = match x.rule {
            Rule::StickyStrike => v0,
            Rule::StickyDelta => vol((strike / f1).ln()),
        };
        let s = v0 * t.sqrt();
        let d1 = (f0 / strike).ln() / s + s / 2.0;
        let delta_bs = if x.call {
            qd * normal_cdf(d1)
        } else {
            -qd * normal_cdf(-d1)
        };
        let vega = x.spot * qd * normal_pdf(d1) * t.sqrt();
        let dvds = match x.rule {
            Rule::StickyStrike => 0.0,
            Rule::StickyDelta => -(x.svi.w1(k0) / (2.0 * v0 * t)) / x.spot,
        };
        o.vols_base.push(v0);
        o.vols_shifted.push(v1);
        o.prices_base.push(black(x.call, f0, strike, v0, t, d));
        o.prices_shifted.push(black(x.call, f1, strike, v1, t, d));
        o.deltas.push(delta_bs + vega * dvds);
    }
    Ok(o)
}

/// `(vol_of_vol, mean_change)`: sample standard deviation (divisor `n - 1`) of changes,
/// annualised (ruling E-A7).
pub fn vol_of_vol(vols: &[f64], periods_per_year: f64, log: bool) -> Result<(f64, f64)> {
    if vols.len() < 3 {
        return fail("E_INPUT", "at least 3 observations are required");
    }
    if vols.iter().any(|v| v.is_nan() || *v <= 0.0)
        || periods_per_year.is_nan()
        || periods_per_year <= 0.0
    {
        return fail("E_DOMAIN", "vols and periods_per_year must be above 0");
    }
    let x: Vec<f64> = vols
        .windows(2)
        .map(|p| if log { (p[1] / p[0]).ln() } else { p[1] - p[0] })
        .collect();
    let n = x.len() as f64;
    let mean = x.iter().sum::<f64>() / n;
    let ss: f64 = x.iter().map(|v| (v - mean) * (v - mean)).sum();
    Ok(((ss / (n - 1.0)).sqrt() * periods_per_year.sqrt(), mean))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sv(a: f64, b: f64, rho: f64, m: f64, sigma: f64) -> Svi {
        Svi {
            a,
            b,
            rho,
            m,
            sigma,
        }
    }

    fn surface() -> Vec<Slice> {
        vec![
            Slice {
                expiry_years: 0.25,
                svi: sv(0.02, 0.1, -0.4, 0.02, 0.2),
            },
            Slice {
                expiry_years: 1.0,
                svi: sv(0.035, 0.11, -0.35, 0.03, 0.25),
            },
            Slice {
                expiry_years: 2.0,
                svi: sv(0.06, 0.12, -0.3, 0.04, 0.3),
            },
        ]
    }

    #[test]
    fn slice_checks_in_order() {
        let mut s = surface();
        assert!(check_slices(&s).is_ok());
        assert_eq!(check_slices(&[]).unwrap_err().code, "E_INPUT");
        s[1].expiry_years = 0.25;
        assert_eq!(check_slices(&s).unwrap_err().code, "E_INPUT");
        let mut s = surface();
        s[0].expiry_years = -0.25;
        assert_eq!(check_slices(&s).unwrap_err().code, "E_DOMAIN");
        let mut s = surface();
        s[2].svi.rho = 1.0;
        assert_eq!(check_slices(&s).unwrap_err().code, "E_DOMAIN");
    }

    #[test]
    fn clean_surface_and_violations() {
        let k: Vec<f64> = (-10..=10).map(|i| f64::from(i) * 0.05).collect();
        let c = surface_check(&surface(), &k).unwrap();
        assert!(c.arbitrage_free());
        // Swapping the slices makes every point a calendar violation, and both wings too.
        let mut s = surface();
        s.swap(0, 2);
        let c = surface_check(&s, &k).unwrap();
        assert!(!c.calendar.is_empty() && !c.arbitrage_free());
        let steep = vec![Slice {
            expiry_years: 1.0,
            svi: sv(0.01, 1.5, 0.5, 0.0, 0.1),
        }];
        let c = surface_check(&steep, &k).unwrap();
        assert_eq!(c.wings, vec![(0, Side::Right, WingKind::Lee)]);
        let edge = vec![Slice {
            expiry_years: 1.0,
            svi: sv(0.01, 2.0, 0.0, 0.0, 0.1),
        }];
        let c = surface_check(&edge, &k).unwrap();
        assert_eq!(
            c.wings,
            vec![
                (0, Side::Left, WingKind::Lee),
                (0, Side::Right, WingKind::Lee)
            ]
        );
        assert_eq!(surface_check(&steep, &[]).unwrap_err().code, "E_INPUT");
        assert_eq!(
            surface_check(&steep, &[0.1, 0.0]).unwrap_err().code,
            "E_INPUT"
        );
    }

    #[test]
    fn equal_slopes_compare_constants() {
        let a = sv(0.04, 0.125, 0.0, 0.0, 0.25);
        let mut b = a;
        b.a = 0.03125;
        let s = [
            Slice {
                expiry_years: 1.0,
                svi: a,
            },
            Slice {
                expiry_years: 2.0,
                svi: b,
            },
        ];
        let c = surface_check(&s, &[0.0]).unwrap();
        assert!(c.wings.contains(&(1, Side::Left, WingKind::Calendar)));
        assert!(c.wings.contains(&(1, Side::Right, WingKind::Calendar)));
    }

    #[test]
    fn vogt_has_butterfly_arbitrage() {
        let v = sv(-0.0410, 0.1331, 0.3060, 0.3586, 0.4153);
        let s = [Slice {
            expiry_years: 1.0,
            svi: v,
        }];
        let k: Vec<f64> = (-15..=15).map(|i| f64::from(i) * 0.1).collect();
        assert_ne!(surface_check(&s, &k).unwrap().butterfly, vec![]);
        assert_eq!(dupire(&s, &[(1.0, 0.7)]).unwrap_err().code, "E_ARBITRAGE");
    }

    #[test]
    fn ssvi_slice_matches_ssvi() {
        let p = ssvi_to_svi(-0.7, 1.2, 0.4, 0.04).unwrap();
        for k in [-0.5, -0.1, 0.0, 0.2, 0.6] {
            assert!((p.w(k) - svi::ssvi_w(k, 0.04, -0.7, 1.2, 0.4)).abs() < 1e-15);
        }
        for bad in [
            (1.0, 1.0, 0.5, 0.1),
            (0.0, 0.0, 0.5, 0.1),
            (0.0, 1.0, 1.5, 0.1),
            (0.0, 1.0, 0.5, 0.0),
        ] {
            assert_eq!(
                ssvi_to_svi(bad.0, bad.1, bad.2, bad.3).unwrap_err().code,
                "E_DOMAIN"
            );
        }
    }

    #[test]
    fn fit_recovers_exact_quotes() {
        let k = [-0.5, -0.3, -0.15, -0.05, 0.0, 0.05, 0.15, 0.3, 0.5];
        let truth = surface();
        let w: Vec<Vec<f64>> = truth
            .iter()
            .map(|s| k.iter().map(|&x| s.svi.w(x)).collect())
            .collect();
        let f = fit_surface(&[0.25, 1.0, 2.0], &k, &w).unwrap();
        for (a, b) in f.slices.iter().zip(&truth) {
            assert!((a.svi.a - b.svi.a).abs() < 1e-6 && (a.svi.rho - b.svi.rho).abs() < 1e-6);
        }
        assert!(f.rmse.iter().all(|r| *r < 1e-8) && f.check.arbitrage_free());
        assert_eq!(
            fit_surface(&[1.0, 0.5], &k, &w[..2]).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(fit_surface(&[1.0], &k, &w).unwrap_err().code, "E_INPUT");
        assert_eq!(
            fit_surface(&[1.0], &k[..4], &[w[0][..4].to_vec()])
                .unwrap_err()
                .code,
            "E_INPUT"
        );
    }

    #[test]
    fn surface_interpolation_rules() {
        let s = surface();
        let k = 0.1;
        let (w, _, _, wt) = surface_at(&s, 0.1, k);
        assert!(
            (w - s[0].svi.w(k) * 0.4).abs() < 1e-15 && (wt - s[0].svi.w(k) / 0.25).abs() < 1e-14
        );
        let (_, _, _, wt) = surface_at(&s, 1.0, k);
        assert!((wt - (s[2].svi.w(k) - s[1].svi.w(k))).abs() < 1e-15);
        let (w, _, _, _) = surface_at(&s, 3.0, k);
        assert!((w - s[2].svi.w(k) * 1.5).abs() < 1e-15);
        let (w, wk, _, _) = surface_at(&s, 0.625, k);
        assert!((w - 0.5 * (s[0].svi.w(k) + s[1].svi.w(k))).abs() < 1e-15);
        assert!((wk - 0.5 * (s[0].svi.w1(k) + s[1].svi.w1(k))).abs() < 1e-15);
        assert!(
            (density(k, s[1].svi.w(k), s[1].svi.w1(k), s[1].svi.w2(k)) - s[1].svi.g(k)).abs()
                < 1e-15
        );
    }

    #[test]
    fn dupire_values_and_checks() {
        let s = surface();
        let r = dupire(&s, &[(0.5, 0.0), (1.5, -0.2)]).unwrap();
        assert_eq!(r.local_vol.len(), 2);
        assert!(r.local_vol.iter().all(|v| *v > 0.05 && *v < 1.0));
        let flat = [Slice {
            expiry_years: 1.0,
            svi: sv(0.04, 0.0, 0.0, 0.0, 0.1),
        }];
        let r = dupire(&flat, &[(0.5, 0.3)]).unwrap();
        assert!((r.local_vol[0] - 0.2).abs() < 1e-15 && (r.implied_vol[0] - 0.2).abs() < 1e-15);
        assert_eq!(dupire(&s, &[]).unwrap_err().code, "E_INPUT");
        assert_eq!(dupire(&s, &[(0.0, 0.0)]).unwrap_err().code, "E_DOMAIN");
        let mut down = surface();
        down[1].svi.a = 0.001;
        assert_eq!(
            dupire(&down, &[(0.5, 0.0)]).unwrap_err().code,
            "E_ARBITRAGE"
        );
    }

    #[test]
    fn forward_vol_rules() {
        let f = forward_vols(&[1.0, 2.0], &[0.2, 0.2]).unwrap();
        assert!((f[1] - 0.2).abs() < 1e-15);
        let z = forward_vols(&[1.0, 4.0], &[0.2, 0.1]).unwrap();
        assert_eq!(z[1], 0.0);
        assert_eq!(
            forward_vols(&[1.0, 2.0], &[0.3, 0.2]).unwrap_err().code,
            "E_ARBITRAGE"
        );
        assert_eq!(forward_vols(&[], &[]).unwrap_err().code, "E_INPUT");
        assert_eq!(
            forward_vols(&[1.0], &[0.2, 0.2]).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(
            forward_vols(&[2.0, 1.0], &[0.2, 0.2]).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(forward_vols(&[1.0], &[0.0]).unwrap_err().code, "E_DOMAIN");
        assert_eq!(
            forward_vols(&[0.0, 1.0], &[0.2, 0.2]).unwrap_err().code,
            "E_DOMAIN"
        );
    }

    fn dyn_case(rule: Rule, call: bool, strikes: &[f64]) -> Dynamics<'_> {
        Dynamics {
            svi: sv(0.02, 0.1, -0.4, 0.02, 0.2),
            expiry_years: 0.5,
            spot: 100.0,
            spot_shifted: 103.0,
            rate: 0.03,
            dividend_yield: 0.01,
            strikes,
            rule,
            call,
        }
    }

    #[test]
    fn smile_dynamics_deltas_match_bumps() {
        let k = [85.0, 100.0, 115.0];
        for rule in [Rule::StickyStrike, Rule::StickyDelta] {
            for call in [true, false] {
                let o = smile_dynamics(&dyn_case(rule, call, &k)).unwrap();
                let h = 1e-4;
                let mut up = dyn_case(rule, call, &k);
                up.spot_shifted = 100.0 + h;
                let mut dn = dyn_case(rule, call, &k);
                dn.spot_shifted = 100.0 - h;
                let (pu, pd) = (smile_dynamics(&up).unwrap(), smile_dynamics(&dn).unwrap());
                for i in 0..k.len() {
                    let bump = (pu.prices_shifted[i] - pd.prices_shifted[i]) / (2.0 * h);
                    assert!((bump - o.deltas[i]).abs() < 1e-6, "{rule:?} {call} {i}");
                }
                if rule == Rule::StickyStrike {
                    assert_eq!(o.vols_base, o.vols_shifted);
                }
            }
        }
        assert_eq!(
            smile_dynamics(&dyn_case(Rule::StickyStrike, true, &[]))
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        assert_eq!(
            smile_dynamics(&dyn_case(Rule::StickyStrike, true, &[0.0]))
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        let mut x = dyn_case(Rule::StickyStrike, true, &k);
        x.spot = 0.0;
        assert_eq!(smile_dynamics(&x).unwrap_err().code, "E_DOMAIN");
    }

    #[test]
    fn vol_of_vol_rules() {
        let (v, m) = vol_of_vol(&[0.2, 0.22, 0.2], 252.0, false).unwrap();
        assert!(m.abs() < 1e-15);
        assert!((v - (0.0008f64 / 1.0).sqrt() * 252f64.sqrt()).abs() < 1e-12);
        let (_, m) = vol_of_vol(&[0.2, 0.4, 0.8], 1.0, true).unwrap();
        assert!((m - 2f64.ln()).abs() < 1e-15);
        assert_eq!(
            vol_of_vol(&[0.2, 0.2], 1.0, true).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(
            vol_of_vol(&[0.2, 0.0, 0.2], 1.0, true).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            vol_of_vol(&[0.2, 0.1, 0.2], 0.0, true).unwrap_err().code,
            "E_DOMAIN"
        );
    }
}
