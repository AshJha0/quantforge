//! Bonds, repo and bond futures (`04-pricing/bonds.md`).
use crate::curve::{Curve, Discount, curve_time};
use crate::dates::{Date, days_in_month};

use crate::error::{Result, err, fail};
use crate::linalg::solve;
use crate::schedule::add_months;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Bond {
    pub maturity: Date,
    pub coupon: f64,
    pub frequency: i64,
}

fn eom(d: Date) -> bool {
    d.d == days_in_month(d.y, d.m)
}

/// `d` stepped back `k` periods of `months`, unadjusted; month ends stay month ends.
fn step_back(maturity: Date, months: i64, k: i64) -> Date {
    let d = add_months(maturity, -months * k);
    if eom(maturity) {
        Date::new(d.y, d.m, days_in_month(d.y, d.m))
    } else {
        d
    }
}

fn days(a: Date, b: Date) -> f64 {
    (b.serial() - a.serial()) as f64
}

/// Dated cash flows after `settlement`, with the period around it.
#[derive(Debug, Clone)]
pub struct Flows {
    pub prev: Date,
    pub next: Date,
    pub flows: Vec<(Date, f64)>,
    pub accrued: f64,
    pub w: f64,
}

/// Dates stepping back from `maturity`, the period holding `settlement`, and later dates.
fn periods(maturity: Date, months: i64, settlement: Date) -> Result<(Date, Vec<Date>)> {
    if settlement >= maturity {
        return fail("E_DATE_ORDER", "settlement is not before maturity");
    }
    let mut dates = Vec::new();
    let mut k = 0;
    loop {
        let d = step_back(maturity, months, k);
        if d <= settlement {
            dates.reverse();
            return Ok((d, dates));
        }
        dates.push(d);
        k += 1;
    }
}

impl Bond {
    /// Unchecked kernel (E1): inputs are not validated, and NaN or infinity in gives NaN out.
    pub fn new(maturity: Date, coupon: f64, frequency: i64) -> Bond {
        Bond {
            maturity,
            coupon,
            frequency,
        }
    }

    pub fn amount(&self) -> f64 {
        100.0 * self.coupon / self.frequency as f64
    }

    fn months(&self) -> i64 {
        12 / self.frequency
    }

    pub fn flows(&self, settlement: Date) -> Result<Flows> {
        crate::error::finite("self", self)?;
        let (prev, dates) = periods(self.maturity, self.months(), settlement)?;
        let next = dates[0];
        let c = self.amount();
        let mut flows: Vec<(Date, f64)> = dates.iter().map(|d| (*d, c)).collect();
        flows.last_mut().expect("one flow").1 += 100.0;
        Ok(Flows {
            prev,
            next,
            flows,
            accrued: c * days(prev, settlement) / days(prev, next),
            w: days(settlement, next) / days(prev, next),
        })
    }

    pub fn accrued(&self, settlement: Date) -> Result<f64> {
        crate::error::finite("self", self)?;
        Ok(self.flows(settlement)?.accrued)
    }

    /// Coupon dates in `(a, b]`.
    fn coupons_between(&self, a: Date, b: Date) -> Result<Vec<Date>> {
        Ok(self
            .flows(a)?
            .flows
            .iter()
            .map(|f| f.0)
            .filter(|d| *d <= b)
            .collect())
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct YieldPrice {
    pub dirty: f64,
    pub accrued: f64,
    pub clean: f64,
    pub modified_duration: f64,
    pub macaulay_duration: f64,
    pub convexity: f64,
}

pub fn price_from_yield(b: &Bond, settlement: Date, y: f64) -> Result<YieldPrice> {
    crate::error::finite("b", &b)?;
    crate::error::finite("y", &y)?;
    let fl = b.flows(settlement)?;
    let f = b.frequency as f64;
    if 1.0 + y / f <= 0.0 {
        return fail("E_DOMAIN", "1 + y/f must be positive");
    }
    let v = 1.0 / (1.0 + y / f);
    let (mut dirty, mut mac, mut conv) = (0.0, 0.0, 0.0);
    for (k, (_, cf)) in fl.flows.iter().enumerate() {
        let e = k as f64 + fl.w;
        let pv = cf * v.powf(e);
        dirty += pv;
        mac += e / f * pv;
        conv += e * (e + 1.0) / (f * f) * pv * v * v;
    }
    let macaulay_duration = mac / dirty;
    Ok(YieldPrice {
        dirty,
        accrued: fl.accrued,
        clean: dirty - fl.accrued,
        modified_duration: macaulay_duration * v,
        macaulay_duration,
        convexity: conv / dirty,
    })
}

/// `(yield, dirty, accrued)`.
pub fn yield_from_price(b: &Bond, settlement: Date, clean: f64) -> Result<(f64, f64, f64)> {
    crate::error::finite("b", &b)?;
    crate::error::finite("clean", &clean)?;
    let accrued = b.accrued(settlement)?;
    let target = clean + accrued;
    if clean <= 0.0 || target <= 0.0 {
        return fail("E_DOMAIN", "price must be positive");
    }
    let f = b.frequency as f64;
    let mut y = b.coupon;
    for _ in 0..200 {
        let p = price_from_yield(b, settlement, y)?;
        let e = p.dirty - target;
        let slope = -p.modified_duration * p.dirty;
        let mut next = y - e / slope;
        while 1.0 + next / f <= 0.0 {
            next = (next + y) / 2.0 - f * 1e-3;
            next = next.max(-f * 0.999_999);
        }
        if (next - y).abs() <= 1e-16 * (1.0 + y.abs()) {
            y = next;
            break;
        }
        y = next;
    }
    let p = price_from_yield(b, settlement, y)?;
    if !p.dirty.is_finite() || (p.dirty - target).abs() > 1e-9 * target {
        return Err(err("E_NO_CONVERGENCE", "the yield solve failed"));
    }
    Ok((y, p.dirty, accrued))
}

/// Dirty price on the curve with a continuous spread `z`, and its derivative in `z`.
fn curve_dirty(b: &Bond, settlement: Date, c: &Curve, z: f64) -> Result<(f64, f64, f64)> {
    dirty_on(b, settlement, c.as_of, c, z)
}

/// `(dirty, d dirty / d z, accrued)` on any discount function whose time origin is `as_of`.
pub fn dirty_on<C: Discount + ?Sized>(
    b: &Bond,
    settlement: Date,
    as_of: Date,
    c: &C,
    z: f64,
) -> Result<(f64, f64, f64)> {
    crate::error::finite("b", &b)?;
    crate::error::finite("z", &z)?;
    if settlement < as_of {
        return fail("E_OUT_OF_RANGE", "settlement is before the curve's as_of");
    }
    let fl = b.flows(settlement)?;
    let ts = curve_time(as_of, settlement);
    let ds = c.discount(settlement)? * (-z * ts).exp();
    let (mut sum, mut dsum) = (0.0, 0.0);
    for (d, cf) in &fl.flows {
        let t = curve_time(as_of, *d);
        let pv = cf * c.discount(*d)? * (-z * t).exp();
        sum += pv;
        dsum -= (t - ts) * pv;
    }
    Ok((sum / ds, dsum / ds, fl.accrued))
}

/// `(dirty, accrued)` on the curve.
pub fn price_from_curve(b: &Bond, settlement: Date, c: &Curve) -> Result<(f64, f64)> {
    crate::error::finite("b", &b)?;
    let (d, _, a) = curve_dirty(b, settlement, c, 0.0)?;
    Ok((d, a))
}

pub fn z_spread(b: &Bond, settlement: Date, c: &Curve, clean: f64) -> Result<f64> {
    crate::error::finite("b", &b)?;
    crate::error::finite("clean", &clean)?;
    let (_, _, accrued) = curve_dirty(b, settlement, c, 0.0)?;
    let target = clean + accrued;
    let mut z = 0.0;
    for _ in 0..200 {
        let (p, dp, _) = curve_dirty(b, settlement, c, z)?;
        let step = (p - target) / dp;
        if !step.is_finite() {
            break;
        }
        z -= step;
        if step.abs() <= 1e-17 {
            break;
        }
    }
    let (p, _, _) = curve_dirty(b, settlement, c, z)?;
    if !p.is_finite() || (p - target).abs() > 1e-9 * target.abs().max(1.0) {
        return Err(err("E_NO_CONVERGENCE", "the Z-spread solve failed"));
    }
    Ok(z)
}

/// Quarterly dates stepping back from `maturity`, plain month arithmetic with no month-end rule.
fn floating_dates(maturity: Date, settlement: Date) -> Result<(Date, Vec<Date>)> {
    let mut dates = Vec::new();
    let mut k = 0;
    loop {
        let d = add_months(maturity, -3 * k);
        if d <= settlement {
            dates.reverse();
            return Ok((d, dates));
        }
        dates.push(d);
        k += 1;
    }
}

/// `(spread, annuity)`: par-par asset swap on quarterly floating dates.
pub fn asset_swap(b: &Bond, settlement: Date, c: &Curve, dirty: f64) -> Result<(f64, f64)> {
    crate::error::finite("b", &b)?;
    crate::error::finite("dirty", &dirty)?;
    let (p, _) = price_from_curve(b, settlement, c)?;
    let (_, dates) = floating_dates(b.maturity, settlement)?;
    let ds = c.discount(settlement)?;
    let mut annuity = 0.0;
    let mut s = settlement;
    for e in dates {
        annuity += days(s, e) / 360.0 * c.discount(e)? / ds;
        s = e;
    }
    Ok(((p - dirty) / (100.0 * annuity), annuity))
}

#[derive(Debug, Clone, Copy)]
pub struct Frn {
    pub settlement: Date,
    pub maturity: Date,
    pub frequency: i64,
    pub current_rate: f64,
    pub margin: f64,
    pub discount_margin: f64,
}

/// `(dirty, accrued)`.
pub fn frn_price(n: &Frn, discount: &Curve, projection: &Curve) -> Result<(f64, f64)> {
    crate::error::finite("n", &n)?;
    let (prev, dates) = periods(n.maturity, 12 / n.frequency, n.settlement)?;
    let dm = |d: Date| -> Result<f64> {
        Ok(discount.discount(d)? * (-n.discount_margin * curve_time(discount.as_of, d)).exp())
    };
    let mut sum = 0.0;
    let mut s = prev;
    for (i, e) in dates.iter().enumerate() {
        let alpha = days(s, *e) / 360.0;
        let r = if i == 0 {
            n.current_rate
        } else {
            (projection.discount(s)? / projection.discount(*e)? - 1.0) / alpha
        };
        sum += 100.0 * (r + n.margin) * alpha * dm(*e)?;
        s = *e;
    }
    sum += 100.0 * dm(n.maturity)?;
    let dirty = sum / dm(n.settlement)?;
    let accrued = 100.0 * (n.current_rate + n.margin) * days(prev, n.settlement) / 360.0;
    Ok((dirty, accrued))
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RepoForward {
    pub dirty: f64,
    pub forward_dirty: f64,
    pub forward_clean: f64,
    pub interest: f64,
    pub special_spread: Option<f64>,
    pub specialness_value: Option<f64>,
}

fn repo_checks(b: &Bond, start: Date, end: Date) -> Result<()> {
    if end <= start {
        return fail("E_DATE_ORDER", "end is not after start");
    }
    if end >= b.maturity {
        return fail("E_INPUT", "end is on or after maturity");
    }
    Ok(())
}

/// `(dirty at start, sum c, sum c (end - d)/360)` over coupons in `(start, end]`.
fn repo_parts(b: &Bond, start: Date, end: Date, clean: f64) -> Result<(f64, f64, f64)> {
    let dirty = clean + b.accrued(start)?;
    let c = b.amount();
    let mut sum = 0.0;
    let mut weighted = 0.0;
    for d in b.coupons_between(start, end)? {
        sum += c;
        weighted += c * days(d, end) / 360.0;
    }
    Ok((dirty, sum, weighted))
}

pub fn repo_forward(
    b: &Bond,
    start: Date,
    end: Date,
    clean: f64,
    r: f64,
    gc: Option<f64>,
) -> Result<RepoForward> {
    crate::error::finite("b", &b)?;
    crate::error::finite("clean", &clean)?;
    crate::error::finite("r", &r)?;
    crate::error::finite("gc", &gc)?;
    repo_checks(b, start, end)?;
    let (dirty, sum, weighted) = repo_parts(b, start, end, clean)?;
    let tau = days(start, end) / 360.0;
    let forward_dirty = dirty * (1.0 + r * tau) - (sum + r * weighted);
    Ok(RepoForward {
        dirty,
        forward_dirty,
        forward_clean: forward_dirty - b.accrued(end)?,
        interest: dirty * r * tau,
        special_spread: gc.map(|g| g - r),
        specialness_value: gc.map(|g| dirty * (g - r) * tau),
    })
}

pub fn repo_implied_rate(
    b: &Bond,
    start: Date,
    end: Date,
    clean: f64,
    forward_clean: f64,
) -> Result<f64> {
    crate::error::finite("b", &b)?;
    crate::error::finite("clean", &clean)?;
    crate::error::finite("forward_clean", &forward_clean)?;
    repo_checks(b, start, end)?;
    let (dirty, sum, weighted) = repo_parts(b, start, end, clean)?;
    let tau = days(start, end) / 360.0;
    let forward_dirty = forward_clean + b.accrued(end)?;
    Ok((forward_dirty - dirty + sum) / (dirty * tau - weighted))
}

/// CBOT conversion factor; `delivery` is the first day of the delivery month. `whole_months` is
/// true for the 2, 3 and 5 year contracts, which do not round `z` down to a quarter (ruling R1-3).
pub fn conversion_factor(
    b: &Bond,
    delivery: Date,
    notional: f64,
    whole_months: bool,
) -> Result<f64> {
    crate::error::finite("b", &b)?;
    crate::error::finite("notional", &notional)?;
    if notional != 0.06 || b.frequency != 2 {
        return fail("E_INPUT", "6% notional and semi-annual bonds only");
    }
    let mut months = (i64::from(b.maturity.y) - i64::from(delivery.y)) * 12
        + i64::from(b.maturity.m)
        - i64::from(delivery.m);
    if b.maturity.d < delivery.d {
        months -= 1;
    }
    if months < 0 {
        return fail("E_DATE_ORDER", "maturity is before delivery");
    }
    let n = months / 12;
    let z = if whole_months {
        months % 12
    } else {
        (months % 12) / 3 * 3
    };
    let v = if z < 7 { z } else { z - 6 } as f64;
    let c = (b.coupon * 800.0 + 0.5).floor() / 800.0;
    let a = 1.03f64.powf(-v / 6.0);
    let bb = c / 2.0 * (6.0 - v) / 6.0;
    let big_c = if z < 7 {
        1.03f64.powi(-2 * n as i32)
    } else {
        1.03f64.powi(-2 * n as i32 - 1)
    };
    let cf = a * (c / 2.0 + c / 0.06 * (1.0 - big_c) + big_c) - bb;
    Ok((cf * 1e4).round_ties_even() / 1e4)
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Basis {
    pub invoice: f64,
    pub gross_basis: f64,
    pub net_basis: f64,
    pub implied_repo: f64,
}

pub fn futures_basis(
    f: f64,
    settlement: Date,
    delivery: Date,
    r: f64,
    bonds: &[(Bond, f64, f64)],
) -> Result<(Vec<Basis>, usize)> {
    crate::error::finite("f", &f)?;
    crate::error::finite("r", &r)?;
    crate::error::finite("bonds", &bonds)?;
    if bonds.is_empty() {
        return fail("E_INPUT", "no bonds");
    }
    let t = days(settlement, delivery) / 360.0;
    let mut out = Vec::new();
    for (b, clean, cf) in bonds {
        let fwd = repo_forward(b, settlement, delivery, *clean, r, None)?;
        let invoice = f * cf + b.accrued(delivery)?;
        let (dirty, sum, weighted) = repo_parts(b, settlement, delivery, *clean)?;
        out.push(Basis {
            invoice,
            gross_basis: clean - f * cf,
            net_basis: fwd.forward_dirty - invoice,
            implied_repo: (invoice + sum - dirty) / (dirty * t - weighted),
        });
    }
    let mut ctd = 0;
    for (i, x) in out.iter().enumerate() {
        if x.implied_repo > out[ctd].implied_repo {
            ctd = i;
        }
    }
    Ok((out, ctd))
}

fn ns_row(t: f64, tau: f64) -> [f64; 3] {
    let x = t / tau;
    let e = -(-x).exp_m1() / x;
    [1.0, e, e - (-x).exp()]
}

/// `bond.fit.nelson_siegel`: `(betas, residuals)`, by damped Gauss-Newton.
pub fn fit_nelson_siegel(
    settlement: Date,
    tau: f64,
    bonds: &[(Bond, f64)],
    weights: Option<&[f64]>,
) -> Result<([f64; 3], Vec<f64>)> {
    crate::error::finite("tau", &tau)?;
    crate::error::finite("bonds", &bonds)?;
    crate::error::finite("weights", &weights)?;
    if tau <= 0.0 {
        return fail("E_DOMAIN", "tau must be positive");
    }
    let n = bonds.len();
    if weights.is_some_and(|w| w.len() != n) {
        return fail("E_INPUT", "weights and bonds differ in length");
    }
    if weights.is_some_and(|w| w.iter().any(|x| *x < 0.0) || w.iter().sum::<f64>() <= 0.0) {
        return fail("E_DOMAIN", "a weight is negative, or the weights sum to 0");
    }
    let w = |j: usize| weights.map_or(1.0, |w| w[j]);
    if (0..n).filter(|j| w(*j) > 0.0).count() < 3 {
        return fail("E_INPUT", "fewer than 3 positive weights");
    }
    let flows: Vec<Vec<(f64, f64, [f64; 3])>> = bonds
        .iter()
        .map(|(b, _)| {
            Ok(b.flows(settlement)?
                .flows
                .iter()
                .map(|(d, cf)| {
                    let t = days(settlement, *d) / 365.0;
                    (t, *cf, ns_row(t, tau))
                })
                .collect())
        })
        .collect::<Result<_>>()?;
    let model = |beta: &[f64; 3]| -> (Vec<f64>, Vec<[f64; 3]>) {
        let mut p = Vec::new();
        let mut jac = Vec::new();
        for f in &flows {
            let (mut v, mut g) = (0.0, [0.0; 3]);
            for (t, cf, row) in f {
                let z = row[0] * beta[0] + row[1] * beta[1] + row[2] * beta[2];
                let pv = cf * (-z * t).exp();
                v += pv;
                for k in 0..3 {
                    g[k] -= pv * t * row[k];
                }
            }
            p.push(v);
            jac.push(g);
        }
        (p, jac)
    };
    let objective = |p: &[f64]| -> f64 { (0..n).map(|j| w(j) * (p[j] - bonds[j].1).powi(2)).sum() };
    let mut beta = [0.04, 0.0, 0.0];
    let (mut p, mut jac) = model(&beta);
    let mut obj = objective(&p);
    let mut mu = 0.0;
    for _ in 0..500 {
        let mut a = vec![vec![0.0; 3]; 3];
        let mut g = vec![0.0; 3];
        for j in 0..n {
            let r = p[j] - bonds[j].1;
            for x in 0..3 {
                g[x] += w(j) * jac[j][x] * r;
                for y in 0..3 {
                    a[x][y] += w(j) * jac[j][x] * jac[j][y];
                }
            }
        }
        let mut accepted = false;
        for _ in 0..40 {
            let mut m = a.clone();
            for (x, row) in m.iter_mut().enumerate() {
                row[x] *= 1.0 + mu;
            }
            let step = solve(&m, &g)?;
            let trial = [beta[0] - step[0], beta[1] - step[1], beta[2] - step[2]];
            let (tp, tj) = model(&trial);
            let to = objective(&tp);
            if to.is_finite() && to <= obj {
                let small = step.iter().all(|s| s.abs() <= 1e-15);
                (beta, p, jac, obj) = (trial, tp, tj, to);
                mu *= 0.1;
                accepted = !small;
                break;
            }
            mu = if mu == 0.0 { 1e-6 } else { mu * 10.0 };
        }
        if !accepted {
            break;
        }
    }
    let residuals = (0..n).map(|j| p[j] - bonds[j].1).collect();
    Ok((beta, residuals))
}

impl crate::error::Finite for Basis {
    fn is_all_finite(&self) -> bool {
        self.invoice.is_all_finite()
            && self.gross_basis.is_all_finite()
            && self.net_basis.is_all_finite()
            && self.implied_repo.is_all_finite()
    }
}

impl crate::error::Finite for Bond {
    fn is_all_finite(&self) -> bool {
        self.coupon.is_all_finite()
    }
}

impl crate::error::Finite for Flows {
    fn is_all_finite(&self) -> bool {
        self.flows.is_all_finite() && self.accrued.is_all_finite() && self.w.is_all_finite()
    }
}

impl crate::error::Finite for Frn {
    fn is_all_finite(&self) -> bool {
        self.current_rate.is_all_finite()
            && self.margin.is_all_finite()
            && self.discount_margin.is_all_finite()
    }
}

impl crate::error::Finite for RepoForward {
    fn is_all_finite(&self) -> bool {
        self.dirty.is_all_finite()
            && self.forward_dirty.is_all_finite()
            && self.forward_clean.is_all_finite()
            && self.interest.is_all_finite()
            && self.special_spread.is_all_finite()
            && self.specialness_value.is_all_finite()
    }
}

impl crate::error::Finite for YieldPrice {
    fn is_all_finite(&self) -> bool {
        self.dirty.is_all_finite()
            && self.accrued.is_all_finite()
            && self.clean.is_all_finite()
            && self.modified_duration.is_all_finite()
            && self.macaulay_duration.is_all_finite()
            && self.convexity.is_all_finite()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn d(s: &str) -> Date {
        Date::parse(s).unwrap()
    }

    fn bond() -> Bond {
        Bond::new(d("2029-11-15"), 0.0425, 2)
    }

    #[test]
    fn schedule_and_accrued() {
        let f = bond().flows(d("2026-11-09")).unwrap();
        assert_eq!(f.prev, d("2026-05-15"));
        assert_eq!(f.next, d("2026-11-15"));
        assert_eq!(f.flows.len(), 7);
        assert_eq!(f.flows[6].1, 102.125);
        let eom = Bond::new(d("2031-02-28"), 0.04, 2)
            .flows(d("2026-11-09"))
            .unwrap();
        assert_eq!(eom.next, d("2027-02-28"));
        assert_eq!(eom.prev, d("2026-08-31"));
        assert_eq!(
            bond().flows(d("2029-11-15")).unwrap_err().code,
            "E_DATE_ORDER"
        );
    }

    #[test]
    fn yield_round_trip_and_domain() {
        let p = price_from_yield(&bond(), d("2026-11-09"), 0.041).unwrap();
        let (y, dirty, _) = yield_from_price(&bond(), d("2026-11-09"), p.clean).unwrap();
        assert!((y - 0.041).abs() < 1e-14);
        assert!((dirty - p.dirty).abs() < 1e-12);
        let par = price_from_yield(&bond(), d("2026-11-15"), 0.0425).unwrap();
        assert!((par.clean - 100.0).abs() < 1e-12);
        let e = price_from_yield(&bond(), d("2026-11-09"), -2.5).unwrap_err();
        assert_eq!(e.code, "E_DOMAIN");
        let e = yield_from_price(&bond(), d("2026-11-09"), -10.0).unwrap_err();
        assert_eq!(e.code, "E_DOMAIN");
    }

    fn flat() -> Curve {
        let as_of = d("2026-11-06");
        let p = d("2046-11-06");
        let i = crate::curve::Interpolation::LogLinearDf;
        Curve::from_logs(as_of, i, &[p], &[-0.04 * curve_time(as_of, p)])
    }

    #[test]
    fn curve_z_spread_and_asset_swap() {
        let c = flat();
        let s = d("2026-11-09");
        let (dirty, acc) = price_from_curve(&bond(), s, &c).unwrap();
        let z = z_spread(&bond(), s, &c, dirty - acc - 1.0).unwrap();
        assert!(z > 0.0);
        let z0 = z_spread(&bond(), s, &c, dirty - acc).unwrap();
        assert!(z0.abs() < 1e-14);
        let (spread, annuity) = asset_swap(&bond(), s, &c, dirty).unwrap();
        assert!(spread.abs() < 1e-15 && annuity > 2.5);
        let e = z_spread(&bond(), d("2026-11-05"), &c, 100.0).unwrap_err();
        assert_eq!(e.code, "E_OUT_OF_RANGE");
    }

    #[test]
    fn frn_par_on_a_coupon_date() {
        let c = flat();
        let s = d("2026-11-16");
        let next = d("2027-02-16");
        let fwd = (c.discount(s).unwrap() / c.discount(next).unwrap() - 1.0) / (92.0 / 360.0);
        let n = Frn {
            settlement: s,
            maturity: d("2029-11-16"),
            frequency: 4,
            current_rate: fwd,
            margin: 0.0,
            discount_margin: 0.0,
        };
        let (dirty, accrued) = frn_price(&n, &c, &c).unwrap();
        assert!((dirty - 100.0).abs() < 1e-11);
        assert_eq!(accrued, 0.0);
    }

    #[test]
    fn repo_round_trip_and_checks() {
        let (s, e) = (d("2026-11-09"), d("2026-12-09"));
        let f = repo_forward(&bond(), s, e, 100.0, 0.0385, Some(0.04)).unwrap();
        let r = repo_implied_rate(&bond(), s, e, 100.0, f.forward_clean).unwrap();
        assert!((r - 0.0385).abs() < 1e-13);
        assert!((f.special_spread.unwrap() - 0.0015).abs() < 1e-16);
        let g = repo_forward(&bond(), s, e, 100.0, 0.0385, None).unwrap();
        assert_eq!(g.special_spread, None);
        assert_eq!(
            repo_forward(&bond(), s, s, 99.0, 0.04, None)
                .unwrap_err()
                .code,
            "E_DATE_ORDER"
        );
        let late = repo_forward(&bond(), s, d("2030-01-01"), 99.0, 0.04, None).unwrap_err();
        assert_eq!(late.code, "E_INPUT");
    }

    #[test]
    fn conversion_factor_cases() {
        let b = Bond::new(d("2033-11-15"), 0.0425, 2);
        assert_eq!(
            conversion_factor(&b, d("2026-12-01"), 0.06, false).unwrap(),
            0.904
        );
        let six = Bond::new(d("2036-12-15"), 0.06, 2);
        assert_eq!(
            conversion_factor(&six, d("2026-12-01"), 0.06, false).unwrap(),
            1.0
        );
        assert_eq!(
            conversion_factor(&b, d("2026-12-01"), 0.05, false)
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        let early = conversion_factor(&b, d("2034-01-01"), 0.06, false).unwrap_err();
        assert_eq!(early.code, "E_DATE_ORDER");
        // 20 months: n = 1, z = 8 (v = 2) in whole months, z = 6 when rounded to a quarter.
        let short = Bond::new(d("2028-08-15"), 0.0425, 2);
        let dl = d("2026-12-01");
        assert_eq!(conversion_factor(&short, dl, 0.06, true).unwrap(), 0.9726);
        assert_eq!(conversion_factor(&short, dl, 0.06, false).unwrap(), 0.9752);
        // The coupon is rounded to 1/8 % first, ties up: 4.1875 % becomes 4.25 %.
        let tie = Bond::new(d("2028-08-15"), 0.041875, 2);
        assert_eq!(conversion_factor(&tie, dl, 0.06, true).unwrap(), 0.9726);
        let annual = Bond::new(d("2033-11-15"), 0.0425, 1);
        assert_eq!(
            conversion_factor(&annual, d("2026-12-01"), 0.06, false)
                .unwrap_err()
                .code,
            "E_INPUT"
        );
    }

    #[test]
    fn basis_picks_highest_implied_repo() {
        let a = (Bond::new(d("2033-11-15"), 0.0425, 2), 100.0, 0.904);
        let b = (Bond::new(d("2034-02-15"), 0.04, 2), 90.0, 0.887);
        let (out, ctd) =
            futures_basis(110.0, d("2026-11-09"), d("2026-12-01"), 0.04, &[a, b]).unwrap();
        assert_eq!(ctd, 1);
        assert!(out[1].implied_repo > out[0].implied_repo);
        assert!(futures_basis(110.0, d("2026-11-09"), d("2026-12-01"), 0.04, &[]).is_err());
    }

    #[test]
    fn fit_recovers_known_betas() {
        let s = d("2026-11-09");
        let truth = [0.042, -0.006, 0.004];
        let specs = [
            ("2029-11-15", 0.0425),
            ("2031-02-28", 0.0375),
            ("2036-08-15", 0.045),
            ("2055-05-15", 0.0475),
        ];
        let bonds: Vec<(Bond, f64)> = specs
            .iter()
            .map(|(m, c)| {
                let b = Bond::new(d(m), *c, 2);
                let p = b
                    .flows(s)
                    .unwrap()
                    .flows
                    .iter()
                    .map(|(x, cf)| {
                        let t = days(s, *x) / 365.0;
                        let r = ns_row(t, 2.5);
                        cf * (-(r[0] * truth[0] + r[1] * truth[1] + r[2] * truth[2]) * t).exp()
                    })
                    .sum();
                (b, p)
            })
            .collect();
        let (beta, res) = fit_nelson_siegel(s, 2.5, &bonds, None).unwrap();
        for k in 0..3 {
            assert!((beta[k] - truth[k]).abs() < 1e-10);
        }
        assert!(res.iter().all(|r| r.abs() < 1e-9));
        assert_eq!(
            fit_nelson_siegel(s, 0.0, &bonds, None).unwrap_err().code,
            "E_DOMAIN"
        );
        let w = [1.0, 1.0, 0.0, 0.0];
        assert_eq!(
            fit_nelson_siegel(s, 2.5, &bonds, Some(&w))
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        let zero = [0.0; 4];
        assert_eq!(
            fit_nelson_siegel(s, 2.5, &bonds, Some(&zero))
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        let neg = [1.0, 1.0, 1.0, -1.0];
        assert_eq!(
            fit_nelson_siegel(s, 2.5, &bonds, Some(&neg))
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
    }
}
