//! Vol surface on a grid: query, node checks, bucket vega (`smile-and-surface.md`, `vol-greeks.md`).
use crate::black::black;

use crate::error::{Result, fail};

const TOL: f64 = 1e-12;

#[derive(Debug, Clone, PartialEq)]
pub struct Surface {
    pub t: Vec<f64>,
    pub k: Vec<f64>,
    pub vols: Vec<Vec<f64>>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Check {
    pub calendar: Vec<(usize, usize)>,
    pub butterfly: Vec<(usize, usize, &'static str)>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Position {
    pub call: bool,
    pub forward: f64,
    pub strike: f64,
    pub discount: f64,
    pub t: f64,
    pub quantity: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SurfaceVega {
    pub pv: f64,
    pub bucket: Vec<Vec<f64>>,
    pub parallel: f64,
    pub bucket_sum: f64,
}

impl Surface {
    pub fn validate(&self) -> Result<()> {
        crate::error::finite("self", self)?;
        let rising = |v: &[f64]| v.windows(2).all(|w| w[1] > w[0]);
        if self.t.is_empty()
            || self.k.is_empty()
            || !rising(&self.t)
            || !rising(&self.k)
            || self.vols.len() != self.t.len()
            || self.vols.iter().any(|r| r.len() != self.k.len())
        {
            return fail("E_INPUT", "grids must increase and match the vols");
        }
        if self.t.iter().any(|&t| t <= 0.0) || self.vols.iter().flatten().any(|&v| v <= 0.0) {
            return fail("E_DOMAIN", "a grid time or vol is not positive");
        }
        Ok(())
    }

    /// `w` on slice `j`, linear in `k`, with `k` clamped to the grid.
    fn slice_w(&self, j: usize, k: f64) -> f64 {
        let (g, t) = (&self.k, self.t[j]);
        let w = |i: usize| self.vols[j][i] * self.vols[j][i] * t;
        if k <= g[0] {
            return w(0);
        }
        let n = g.len() - 1;
        if k >= g[n] {
            return w(n);
        }
        let i = g.partition_point(|&x| x <= k) - 1;
        let x = (k - g[i]) / (g[i + 1] - g[i]);
        w(i) + x * (w(i + 1) - w(i))
    }

    /// Total variance at a point, for `t` above 0.
    /// Unchecked kernel (E1): inputs are not validated, and NaN or infinity in gives NaN out.
    pub fn w(&self, t: f64, k: f64) -> f64 {
        let g = &self.t;
        let n = g.len() - 1;
        if t <= g[0] {
            return self.slice_w(0, k) * t / g[0];
        }
        if t >= g[n] {
            return self.slice_w(n, k) * t / g[n];
        }
        let j = g.partition_point(|&x| x <= t) - 1;
        let (a, b) = (self.slice_w(j, k), self.slice_w(j + 1, k));
        a + (t - g[j]) / (g[j + 1] - g[j]) * (b - a)
    }

    pub fn query(&self, points: &[(f64, f64)]) -> Result<Vec<(f64, f64)>> {
        crate::error::finite("self", self)?;
        crate::error::finite("points", &points)?;
        self.validate()?;
        if points.iter().any(|p| p.0 <= 0.0) {
            return fail("E_DOMAIN", "expiry_years must be above 0");
        }
        Ok(points
            .iter()
            .map(|&(t, k)| {
                let w = self.w(t, k);
                (w, (w / t).sqrt())
            })
            .collect())
    }

    pub fn check(&self) -> Result<Check> {
        crate::error::finite("self", self)?;
        self.validate()?;
        let w = |j: usize, i: usize| self.vols[j][i] * self.vols[j][i] * self.t[j];
        let mut calendar = Vec::new();
        for j in 1..self.t.len() {
            for i in 0..self.k.len() {
                if w(j, i) < w(j - 1, i) - TOL {
                    calendar.push((j, i));
                }
            }
        }
        let mut butterfly = Vec::new();
        let strikes: Vec<f64> = self.k.iter().map(|k| k.exp()).collect();
        for j in 0..self.t.len() {
            let c: Vec<f64> = strikes
                .iter()
                .zip(&self.vols[j])
                .map(|(&k, &v)| black(true, 1.0, k, v, self.t[j], 1.0))
                .collect();
            let s: Vec<f64> = (0..c.len().saturating_sub(1))
                .map(|i| (c[i + 1] - c[i]) / (strikes[i + 1] - strikes[i]))
                .collect();
            for (i, &v) in s.iter().enumerate() {
                if v < -1.0 - TOL || v > TOL {
                    butterfly.push((j, i, "SLOPE"));
                }
            }
            for i in 0..s.len().saturating_sub(1) {
                if s[i + 1] < s[i] - TOL {
                    butterfly.push((j, i + 1, "CONVEXITY"));
                }
            }
        }
        Ok(Check {
            calendar,
            butterfly,
        })
    }

    fn pv(&self, p: &[Position]) -> f64 {
        let mut sum = 0.0;
        for x in p {
            let v = (self.w(x.t, (x.strike / x.forward).ln()) / x.t).sqrt();
            sum += x.quantity * black(x.call, x.forward, x.strike, v, x.t, x.discount);
        }
        sum
    }

    pub fn vega(&self, p: &[Position]) -> Result<SurfaceVega> {
        const H: f64 = 1e-4;
        crate::error::finite("self", self)?;
        crate::error::finite("p", &p)?;
        self.validate()?;
        if p.iter()
            .any(|x| x.t <= 0.0 || x.forward <= 0.0 || x.strike <= 0.0 || x.discount <= 0.0)
        {
            return fail("E_DOMAIN", "a position is out of domain");
        }
        if self.vols.iter().flatten().any(|&v| v - H <= 0.0) {
            return fail("E_DOMAIN", "a node vol is too low to bump");
        }
        let mut s = self.clone();
        let mut bucket = vec![vec![0.0; self.k.len()]; self.t.len()];
        let mut bucket_sum = 0.0;
        for j in 0..self.t.len() {
            for i in 0..self.k.len() {
                let v = self.vols[j][i];
                s.vols[j][i] = v + H;
                let up = s.pv(p);
                s.vols[j][i] = v - H;
                let down = s.pv(p);
                s.vols[j][i] = v;
                bucket[j][i] = (up - down) / 2e-4;
                bucket_sum += bucket[j][i];
            }
        }
        let shifted = |h: f64| {
            let mut m = self.clone();
            m.vols.iter_mut().flatten().for_each(|v| *v += h);
            m.pv(p)
        };
        Ok(SurfaceVega {
            pv: self.pv(p),
            parallel: (shifted(H) - shifted(-H)) / 2e-4,
            bucket,
            bucket_sum,
        })
    }
}

impl crate::error::Finite for Position {
    fn is_all_finite(&self) -> bool {
        self.forward.is_all_finite()
            && self.strike.is_all_finite()
            && self.discount.is_all_finite()
            && self.t.is_all_finite()
            && self.quantity.is_all_finite()
    }
}

impl crate::error::Finite for Surface {
    fn is_all_finite(&self) -> bool {
        self.t.is_all_finite() && self.k.is_all_finite() && self.vols.is_all_finite()
    }
}

impl crate::error::Finite for SurfaceVega {
    fn is_all_finite(&self) -> bool {
        self.pv.is_all_finite()
            && self.bucket.is_all_finite()
            && self.parallel.is_all_finite()
            && self.bucket_sum.is_all_finite()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn flat() -> Surface {
        Surface {
            t: vec![1.0, 2.0],
            k: vec![-0.2, 0.2],
            vols: vec![vec![0.2; 2]; 2],
        }
    }

    #[test]
    fn flat_vol_in_both_directions() {
        let r = flat()
            .query(&[(0.5, -1.0), (3.0, 1.0), (1.5, 0.0)])
            .unwrap();
        assert!(r.iter().all(|x| (x.1 - 0.2).abs() < 1e-14));
    }

    #[test]
    fn calendar_violation_is_found() {
        let mut s = flat();
        s.vols[1][0] = 0.1;
        assert_eq!(s.check().unwrap().calendar, vec![(1, 0)]);
    }
}
