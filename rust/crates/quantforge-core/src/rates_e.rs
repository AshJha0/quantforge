//! Stage E4: SABR swaption cube, caplet stripping, bond futures options, inflation caps
//! (`05-volatility/rates-vol-cube.md`, rulings E-B8 to E-B13).
use crate::black::black;
use crate::curve::Curve;
use crate::daycount::{DayCountInputs, year_fraction};
use crate::error::{Result, fail};
use crate::sabr::Sabr;
use crate::stage_d3::{forward_start, option, periods, swap_forward, years};

/// SABR parameters at each (expiry, tenor) node; matrices are rows by expiry.
pub struct Cube {
    pub expiries_months: Vec<i64>,
    pub tenors_months: Vec<i64>,
    pub alpha: Vec<Vec<f64>>,
    pub beta: Vec<Vec<f64>>,
    pub rho: Vec<Vec<f64>>,
    pub nu: Vec<Vec<f64>>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SabrParams {
    pub alpha: f64,
    pub beta: f64,
    pub rho: f64,
    pub nu: f64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CubePrice {
    pub price: f64,
    pub forward_rate: f64,
    pub annuity: f64,
    pub vol: f64,
    pub sabr: SabrParams,
}

pub struct CubeTrade {
    pub payer: bool,
    pub expiry_months: i64,
    pub tenor_months: i64,
    pub strike: f64,
    pub notional: f64,
}

fn increasing<T: PartialOrd>(v: &[T]) -> bool {
    !v.is_empty() && v.windows(2).all(|w| w[0] < w[1])
}

/// The cell `(i, weight)` holding `x` on `nodes`, or `None` outside. One node needs `x` on it.
fn locate(nodes: &[f64], x: f64) -> Option<(usize, f64)> {
    let n = nodes.len();
    if x < nodes[0] || x > nodes[n - 1] {
        return None;
    }
    if n == 1 {
        return Some((0, 0.0));
    }
    let i = nodes.partition_point(|&v| v <= x).clamp(1, n - 1) - 1;
    Some((i, (x - nodes[i]) / (nodes[i + 1] - nodes[i])))
}

fn bilinear(m: &[Vec<f64>], (i, u): (usize, f64), (j, v): (usize, f64)) -> f64 {
    let at = |a: usize, b: usize| m[a.min(m.len() - 1)][b.min(m[0].len() - 1)];
    (1.0 - u) * (1.0 - v) * at(i, j)
        + u * (1.0 - v) * at(i + 1, j)
        + (1.0 - u) * v * at(i, j + 1)
        + u * v * at(i + 1, j + 1)
}

/// Parameters, not vols, are bilinear in (ACT/365F expiry time, tenor years) (ruling E-B8).
pub fn price_cube(
    discount: &Curve,
    projection: &Curve,
    c: &Cube,
    t: &CubeTrade,
) -> Result<CubePrice> {
    let (ne, nt) = (c.expiries_months.len(), c.tenors_months.len());
    let shaped = |m: &Vec<Vec<f64>>| m.len() == ne && m.iter().all(|r| r.len() == nt);
    if ![&c.alpha, &c.beta, &c.rho, &c.nu].into_iter().all(shaped)
        || !increasing(&c.expiries_months)
        || !increasing(&c.tenors_months)
    {
        return fail(
            "E_INPUT",
            "cube matrices must be expiries x tenors on increasing nodes",
        );
    }
    if t.expiry_months < 1 {
        return fail("E_INPUT", "expiry_months must be at least 1");
    }
    let as_of = discount.as_of;
    let node_t = c
        .expiries_months
        .iter()
        .map(|&m| Ok(years(as_of, forward_start(as_of, m)?)))
        .collect::<Result<Vec<_>>>()?;
    let node_l: Vec<f64> = c.tenors_months.iter().map(|&m| m as f64 / 12.0).collect();
    let start = forward_start(as_of, t.expiry_months)?;
    let (te, tl) = (years(as_of, start), t.tenor_months as f64 / 12.0);
    let (Some(ce), Some(cl)) = (locate(&node_t, te), locate(&node_l, tl)) else {
        return fail("E_INPUT", "the swaption lies outside the cube grid");
    };
    let all = |m: &Vec<Vec<f64>>, ok: &dyn Fn(f64) -> bool| m.iter().flatten().all(|&v| ok(v));
    if !(all(&c.alpha, &|v| v > 0.0)
        && all(&c.beta, &|v| (0.0..=1.0).contains(&v))
        && all(&c.rho, &|v| v.abs() < 1.0)
        && all(&c.nu, &|v| v >= 0.0))
    {
        return fail("E_DOMAIN", "a cube SABR parameter is out of domain");
    }
    let sabr = SabrParams {
        alpha: bilinear(&c.alpha, ce, cl),
        beta: bilinear(&c.beta, ce, cl),
        rho: bilinear(&c.rho, ce, cl),
        nu: bilinear(&c.nu, ce, cl),
    };
    let (_, f, a) = swap_forward(discount, projection, t.expiry_months, t.tenor_months)?;
    if t.strike.is_nan() || t.strike <= 0.0 || f <= 0.0 {
        return fail("E_DOMAIN", "strike and forward must be positive");
    }
    let model = Sabr {
        t: te,
        alpha: sabr.alpha,
        beta: sabr.beta,
        rho: sabr.rho,
        nu: sabr.nu,
        forward: f,
        shift: 0.0,
    };
    let vol = model.hagan(&[t.strike])?[0];
    Ok(CubePrice {
        price: t.notional * a * black(t.payer, f, t.strike, vol, te, 1.0),
        forward_rate: f,
        annuity: a,
        vol,
        sabr,
    })
}

pub struct Strip<'a> {
    pub normal: bool,
    pub start_months: i64,
    pub strike: f64,
    pub cap_tenors_months: &'a [i64],
    pub flat_vols: &'a [f64],
    pub notional: f64,
}

/// `(caplet_vols, cap_prices)`: piecewise-constant caplet vols per segment (rulings E-B9, E-B10).
pub fn strip_caplets(
    discount: &Curve,
    projection: &Curve,
    x: &Strip,
) -> Result<(Vec<f64>, Vec<f64>)> {
    let tenors = x.cap_tenors_months;
    if !increasing(tenors) || tenors.iter().any(|m| m % 3 != 0 || *m <= 0) {
        return fail("E_INPUT", "cap tenors must be increasing multiples of 3");
    }
    if x.flat_vols.len() != tenors.len() {
        return fail("E_INPUT", "one flat vol per cap tenor");
    }
    if x.flat_vols.iter().any(|v| v.is_nan() || *v <= 0.0) {
        return fail("E_DOMAIN", "flat vols must be above 0");
    }
    if x.start_months < 1 {
        return fail("E_INPUT", "start_months must be at least 1");
    }
    let as_of = discount.as_of;
    let longest = tenors[tenors.len() - 1];
    let ps = periods(forward_start(as_of, x.start_months)?, longest, 3)?;
    let none = DayCountInputs::default();
    // (scale, forward, time) per caplet: caplet = scale * option(forward, K, v, time).
    let caplets = ps
        .iter()
        .map(|p| {
            let alpha = year_fraction("ACT_360", p.start, p.end, &none)?;
            let f = (projection.discount(p.start)? / projection.discount(p.end)? - 1.0) / alpha;
            Ok((
                x.notional * alpha * discount.discount(p.end)?,
                f,
                years(as_of, p.start),
            ))
        })
        .collect::<Result<Vec<_>>>()?;
    let value = |c: &(f64, f64, f64), v: f64| -> Result<f64> {
        Ok(c.0 * option(x.normal, true, c.1, x.strike, v, c.2)?)
    };
    let floor = if x.normal { 1e-7 } else { 1e-6 };
    let (mut vols, mut targets, mut known) = (Vec::new(), Vec::new(), 0.0);
    let mut done = 0usize;
    for (&m, &flat) in tenors.iter().zip(x.flat_vols) {
        let n = usize::try_from(m / 3).unwrap_or(0).min(caplets.len());
        let target = caplets[..n]
            .iter()
            .map(|c| value(c, flat))
            .sum::<Result<f64>>()?;
        let fresh = &caplets[done..n];
        let gap = |v: f64| -> Result<f64> {
            Ok(known + fresh.iter().map(|c| value(c, v)).sum::<Result<f64>>()? - target)
        };
        if gap(floor)? >= 0.0 {
            return fail(
                "E_ARBITRAGE",
                "a segment needs a caplet vol at or below zero",
            );
        }
        let (mut lo, mut hi) = (floor, flat.max(floor) * 2.0);
        while gap(hi)? < 0.0 {
            lo = hi;
            hi *= 2.0;
            if hi > 1e6 {
                return fail("E_NO_CONVERGENCE", "no caplet vol reaches the cap price");
            }
        }
        for _ in 0..2000 {
            let mid = 0.5 * (lo + hi);
            if mid <= lo || mid >= hi {
                break;
            }
            if gap(mid)? < 0.0 {
                lo = mid;
            } else {
                hi = mid;
            }
        }
        let v = 0.5 * (lo + hi);
        known += fresh.iter().map(|c| value(c, v)).sum::<Result<f64>>()?;
        vols.extend(std::iter::repeat_n(v, fresh.len()));
        targets.push(target);
        done = n;
    }
    Ok((vols, targets))
}

/// Black-76 on a bond futures price, premium paid at the given discount date (ruling E-B11).
pub struct FuturesOption {
    pub call: bool,
    pub futures_price: f64,
    pub strike: f64,
    pub expiry_years: f64,
    pub discount_factor: f64,
}

impl FuturesOption {
    fn check(&self) -> Result<()> {
        let pos = [
            self.expiry_years,
            self.futures_price,
            self.strike,
            self.discount_factor,
        ];
        if pos.iter().all(|v| *v > 0.0) {
            Ok(())
        } else {
            fail(
                "E_DOMAIN",
                "expiry, futures price, strike and discount factor must be above 0",
            )
        }
    }

    fn value(&self, vol: f64) -> f64 {
        black(
            self.call,
            self.futures_price,
            self.strike,
            vol,
            self.expiry_years,
            self.discount_factor,
        )
    }
}

/// `(price per 100 face, contract value)`.
pub fn futures_option_price(o: &FuturesOption, vol: f64, contract_size: f64) -> Result<(f64, f64)> {
    o.check()?;
    if vol.is_nan() || vol < 0.0 {
        return fail("E_DOMAIN", "vol must not be negative");
    }
    let p = o.value(vol);
    Ok((p, p * contract_size / 100.0))
}

/// `(price_vol, yield_vol)` with `yield_vol = price_vol / (Dm y)`.
pub fn futures_implied_vol(
    o: &FuturesOption,
    premium: f64,
    ctd_yield: f64,
    duration: f64,
) -> Result<(f64, f64)> {
    o.check()?;
    let (f, k, d) = (o.futures_price, o.strike, o.discount_factor);
    let intrinsic = d * if o.call {
        (f - k).max(0.0)
    } else {
        (k - f).max(0.0)
    };
    let bound = d * if o.call { f } else { k };
    if premium.is_nan() || premium <= intrinsic || premium >= bound {
        return fail(
            "E_DOMAIN",
            "premium must lie strictly between intrinsic and the bound",
        );
    }
    let (mut lo, mut hi) = (0.0, 1.0);
    while o.value(hi) < premium {
        hi *= 2.0;
        if hi > 1e6 {
            return fail("E_NO_CONVERGENCE", "no vol reaches the premium");
        }
    }
    for _ in 0..2000 {
        let mid = 0.5 * (lo + hi);
        if mid <= lo || mid >= hi {
            break;
        }
        if o.value(mid) < premium {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    let v = 0.5 * (lo + hi);
    Ok((v, v / (duration * ctd_yield)))
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct YoyPeriod {
    pub accrual: f64,
    pub discount_factor: f64,
    pub yoy_forward: f64,
    pub expiry_years: f64,
    pub vol: f64,
}

/// Caplets with option time to the fixing, discounted to payment (ruling E-B12).
pub fn yoy_caplets(
    normal: bool,
    cap: bool,
    strike: f64,
    notional: f64,
    periods: &[YoyPeriod],
) -> Result<Vec<f64>> {
    if periods.is_empty() {
        return fail("E_INPUT", "periods must not be empty");
    }
    if periods
        .iter()
        .any(|p| p.expiry_years.is_nan() || p.expiry_years <= 0.0)
    {
        return fail("E_DOMAIN", "expiry_years must be above 0");
    }
    periods
        .iter()
        .map(|p| {
            let o = option(normal, cap, p.yoy_forward, strike, p.vol, p.expiry_years)?;
            Ok(notional * p.accrual * o * p.discount_factor)
        })
        .collect()
}

pub struct ZeroCoupon {
    pub normal: bool,
    pub cap: bool,
    pub forward_index_ratio: f64,
    pub years: f64,
    pub strike: f64,
    pub discount_factor: f64,
    pub vol: f64,
    pub notional: f64,
}

/// `(price, strike_ratio)` with `strike_ratio = (1 + K)^T` (ruling E-B13).
pub fn zc_cap(z: &ZeroCoupon) -> Result<(f64, f64)> {
    if z.years.is_nan() || z.years <= 0.0 {
        return fail("E_DOMAIN", "years must be above 0");
    }
    let ratio = (1.0 + z.strike).powf(z.years);
    let o = option(
        z.normal,
        z.cap,
        z.forward_index_ratio,
        ratio,
        z.vol,
        z.years,
    )?;
    Ok((z.notional * z.discount_factor * o, ratio))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::curve::{CurveInput, Interpolation};
    use crate::dates::Date;

    fn curve(rate: f64) -> Curve {
        let as_of = Date::new(2026, 11, 6);
        let pillars = [1, 2, 3, 5, 7, 10, 15]
            .iter()
            .map(|y| {
                let d = Date::new(2026 + y, 11, 6);
                (d, (-rate * years(as_of, d)).exp())
            })
            .collect();
        Curve::new(&CurveInput {
            as_of,
            interpolation: Interpolation::LogLinearDf,
            pillars,
            jumps: Vec::new(),
        })
        .unwrap()
    }

    fn cube() -> Cube {
        Cube {
            expiries_months: vec![12, 24],
            tenors_months: vec![24, 60],
            alpha: vec![vec![0.05, 0.048], vec![0.046, 0.044]],
            beta: vec![vec![0.5; 2]; 2],
            rho: vec![vec![-0.2, -0.27], vec![-0.25, -0.29]],
            nu: vec![vec![0.5, 0.44], vec![0.45, 0.39]],
        }
    }

    fn trade(expiry: i64, tenor: i64, strike: f64) -> CubeTrade {
        CubeTrade {
            payer: true,
            expiry_months: expiry,
            tenor_months: tenor,
            strike,
            notional: 1e7,
        }
    }

    #[test]
    fn cube_node_and_between() {
        let (d, p) = (curve(0.035), curve(0.037));
        let at = price_cube(&d, &p, &cube(), &trade(12, 60, 0.037)).unwrap();
        assert_eq!(at.sabr.rho, -0.27);
        let (_, f, a) = swap_forward(&d, &p, 12, 60).unwrap();
        assert_eq!((at.forward_rate, at.annuity), (f, a));
        let mid = price_cube(&d, &p, &cube(), &trade(18, 60, 0.037)).unwrap();
        assert!(mid.sabr.rho < -0.27 && mid.sabr.rho > -0.29);
        let side = price_cube(&d, &p, &cube(), &trade(12, 36, 0.037)).unwrap();
        assert!((side.sabr.rho - (-0.2 - 0.07 / 3.0)).abs() < 1e-12);
        let put = price_cube(
            &d,
            &p,
            &cube(),
            &CubeTrade {
                payer: false,
                ..trade(12, 60, 0.037)
            },
        )
        .unwrap();
        let parity = 1e7 * a * (f - 0.037);
        assert!((at.price - put.price - parity).abs() < 1e-6);
    }

    #[test]
    fn cube_checks() {
        let (d, p) = (curve(0.035), curve(0.037));
        let code = |c: &Cube, t: &CubeTrade| price_cube(&d, &p, c, t).unwrap_err().code;
        let ok = trade(12, 60, 0.037);
        assert_eq!(code(&cube(), &trade(6, 60, 0.037)), "E_INPUT");
        assert_eq!(code(&cube(), &trade(12, 120, 0.037)), "E_INPUT");
        assert_eq!(code(&cube(), &trade(0, 60, 0.037)), "E_INPUT");
        let mut c = cube();
        c.nu.pop();
        assert_eq!(code(&c, &ok), "E_INPUT");
        let mut c = cube();
        c.expiries_months = vec![24, 12];
        assert_eq!(code(&c, &ok), "E_INPUT");
        let mut c = cube();
        c.rho[0][0] = 1.0;
        assert_eq!(code(&c, &ok), "E_DOMAIN");
        assert_eq!(code(&cube(), &trade(12, 60, 0.0)), "E_DOMAIN");
        assert_eq!(locate(&[1.0], 1.0), Some((0, 0.0)));
        assert_eq!(locate(&[1.0], 2.0), None);
    }

    fn strip<'a>(tenors: &'a [i64], vols: &'a [f64], normal: bool) -> Strip<'a> {
        Strip {
            normal,
            start_months: 3,
            strike: 0.037,
            cap_tenors_months: tenors,
            flat_vols: vols,
            notional: 1e7,
        }
    }

    #[test]
    fn strip_reprices_every_cap() {
        let (d, p) = (curve(0.035), curve(0.037));
        let tenors = [12, 24, 36];
        for (vols, normal) in [
            ([0.24, 0.235, 0.228], false),
            ([0.009, 0.0088, 0.0085], true),
        ] {
            let (cv, targets) = strip_caplets(&d, &p, &strip(&tenors, &vols, normal)).unwrap();
            assert_eq!(cv.len(), 12);
            assert!((cv[0] - vols[0]).abs() < 1e-12);
            for (k, &m) in tenors.iter().enumerate() {
                let n = usize::try_from(m / 3).unwrap();
                let trade = crate::stage_d3::CapTrade {
                    cap: true,
                    start_months: 3,
                    tenor_months: m,
                    strike: 0.037,
                    notional: 1e7,
                };
                let c = crate::stage_d3::cap_price(&d, &p, normal, &cv[..n], &trade).unwrap();
                assert!((c.iter().sum::<f64>() - targets[k]).abs() < 1e-6);
            }
        }
    }

    #[test]
    fn strip_checks() {
        let (d, p) = (curve(0.035), curve(0.037));
        let code = |s: &Strip| strip_caplets(&d, &p, s).unwrap_err().code;
        assert_eq!(code(&strip(&[12, 25], &[0.2, 0.2], false)), "E_INPUT");
        assert_eq!(code(&strip(&[24, 12], &[0.2, 0.2], false)), "E_INPUT");
        assert_eq!(code(&strip(&[12, 24], &[0.2], false)), "E_INPUT");
        assert_eq!(code(&strip(&[12, 24], &[0.2, 0.0], false)), "E_DOMAIN");
        assert_eq!(code(&strip(&[12, 24], &[0.4, 0.05], false)), "E_ARBITRAGE");
        let mut s = strip(&[12], &[0.2], false);
        s.start_months = 0;
        assert_eq!(code(&s), "E_INPUT");
    }

    #[test]
    fn bond_futures_round_trip() {
        let o = FuturesOption {
            call: true,
            futures_price: 111.25,
            strike: 112.0,
            expiry_years: 0.1,
            discount_factor: 0.9962,
        };
        let (p, cv) = futures_option_price(&o, 0.055, 100_000.0).unwrap();
        assert!((cv - p * 1000.0).abs() < 1e-9);
        let (v, y) = futures_implied_vol(&o, p, 0.0425, 6.4).unwrap();
        assert!((v - 0.055).abs() < 1e-12);
        assert!((y - 0.055 / (6.4 * 0.0425)).abs() < 1e-10);
        assert_eq!(
            futures_implied_vol(&o, 0.0, 0.04, 6.0).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            futures_implied_vol(&o, 200.0, 0.04, 6.0).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            futures_option_price(&o, -0.1, 1.0).unwrap_err().code,
            "E_DOMAIN"
        );
        let bad = FuturesOption {
            expiry_years: 0.0,
            ..o
        };
        assert_eq!(
            futures_option_price(&bad, 0.05, 1.0).unwrap_err().code,
            "E_DOMAIN"
        );
        let put = FuturesOption { call: false, ..o };
        let (pp, _) = futures_option_price(&put, 0.055, 1.0).unwrap();
        assert!((p - pp - 0.9962 * (111.25 - 112.0)).abs() < 1e-12);
        assert!((futures_implied_vol(&put, pp, 0.04, 6.0).unwrap().0 - 0.055).abs() < 1e-12);
    }

    #[test]
    fn inflation_caps() {
        let per = YoyPeriod {
            accrual: 1.0,
            discount_factor: 0.96,
            yoy_forward: 0.0285,
            expiry_years: 0.75,
            vol: 0.3,
        };
        let c = yoy_caplets(false, true, 0.03, 1e7, &[per, per]).unwrap();
        let want = 1e7 * 0.96 * black(true, 0.0285, 0.03, 0.3, 0.75, 1.0);
        assert!((c[0] - want).abs() < 1e-9 && c[0] == c[1]);
        assert_eq!(
            yoy_caplets(false, true, 0.03, 1.0, &[]).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(
            yoy_caplets(false, true, 0.0, 1.0, &[per]).unwrap_err().code,
            "E_DOMAIN"
        );
        let late = YoyPeriod {
            expiry_years: 0.0,
            ..per
        };
        assert_eq!(
            yoy_caplets(false, true, 0.03, 1.0, &[late])
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        assert!(yoy_caplets(true, false, -0.01, 1.0, &[per]).is_ok());
        let z = ZeroCoupon {
            normal: false,
            cap: true,
            forward_index_ratio: 1.1268,
            years: 5.0,
            strike: 0.025,
            discount_factor: 0.8305,
            vol: 0.028,
            notional: 1e7,
        };
        let (_, r) = zc_cap(&z).unwrap();
        assert!((r - 1.131408212890625).abs() < 1e-15);
        assert_eq!(
            zc_cap(&ZeroCoupon { years: 0.0, ..z }).unwrap_err().code,
            "E_DOMAIN"
        );
    }
}
