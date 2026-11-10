//! Mortgage pools: prepayment, cash flows and price (`mbs.md`).

use crate::error::{Result, fail};

#[derive(Debug, Clone, Copy)]
pub enum Prepayment {
    Cpr(f64),
    Psa(f64),
}

#[derive(Debug, Clone, Copy)]
pub struct Pool {
    pub balance: f64,
    pub wac: f64,
    pub net_coupon: f64,
    pub wam: i64,
    pub age: i64,
    pub prepayment: Prepayment,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MbsFlows {
    pub balance: Vec<f64>,
    pub interest: Vec<f64>,
    pub scheduled_principal: Vec<f64>,
    pub prepayment: Vec<f64>,
    pub wal: f64,
}

/// `mbs.cashflows`. Checks as golden `mbs_d-0011` orders them: `wac <= 0` first.
pub fn mbs_cashflows(p: &Pool) -> Result<MbsFlows> {
    crate::error::finite("p", &p)?;
    if p.wac <= 0.0 {
        return fail("E_DOMAIN", "wac must be positive");
    }
    if p.wam < 1 || p.wam > 1200 || p.age < 0 || p.net_coupon > p.wac {
        return fail("E_INPUT", "wam, age or net_coupon out of range");
    }
    let bad = match p.prepayment {
        Prepayment::Cpr(r) => !(0.0..1.0).contains(&r),
        Prepayment::Psa(s) => s < 0.0,
    };
    if p.balance <= 0.0 || bad {
        return fail("E_DOMAIN", "balance or prepayment out of range");
    }
    let r = p.wac / 12.0;
    let n_total = p.wam as usize;
    let mut out = MbsFlows {
        balance: Vec::with_capacity(n_total),
        interest: Vec::with_capacity(n_total),
        scheduled_principal: Vec::with_capacity(n_total),
        prepayment: Vec::with_capacity(n_total),
        wal: 0.0,
    };
    let mut b = p.balance;
    let mut wal = 0.0;
    for k in 1..=p.wam {
        let cpr = match p.prepayment {
            Prepayment::Cpr(x) => x,
            Prepayment::Psa(s) => (((p.age + k) as f64) / 30.0).min(1.0) * 0.06 * s / 100.0,
        };
        let smm = 1.0 - (1.0 - cpr).powf(1.0 / 12.0);
        let n = (p.wam - k + 1) as f64;
        let sched = if k == p.wam {
            b
        } else {
            b * r / (1.0 - (1.0 + r).powf(-n)) - b * r
        };
        let prepay = smm * (b - sched);
        out.balance.push(b);
        out.interest.push(b * p.net_coupon / 12.0);
        out.scheduled_principal.push(sched);
        out.prepayment.push(prepay);
        wal += k as f64 / 12.0 * (sched + prepay);
        b = b - sched - prepay;
    }
    out.wal = wal / p.balance;
    Ok(out)
}

/// `mbs.price`: `(price, modified_duration, wal)`.
pub fn mbs_price(p: &Pool, y: f64, delay_days: i64) -> Result<(f64, f64, f64)> {
    crate::error::finite("p", &p)?;
    crate::error::finite("y", &y)?;
    if delay_days < 0 {
        return fail("E_INPUT", "delay_days must not be negative");
    }
    let f = mbs_cashflows(p)?;
    if 1.0 + y / 12.0 <= 0.0 {
        return fail("E_DOMAIN", "1 + y/12 must be positive");
    }
    let v = 1.0 / (1.0 + y / 12.0);
    let (mut pv, mut dur) = (0.0, 0.0);
    for k in 0..f.balance.len() {
        let cf = f.interest[k] + f.scheduled_principal[k] + f.prepayment[k];
        let t = (k + 1) as f64 + delay_days as f64 / 30.0;
        let x = cf * v.powf(t);
        pv += x;
        dur += t / 12.0 * x * v;
    }
    Ok((100.0 * pv / p.balance, dur / pv, f.wal))
}

impl crate::error::Finite for MbsFlows {
    fn is_all_finite(&self) -> bool {
        self.balance.is_all_finite()
            && self.interest.is_all_finite()
            && self.scheduled_principal.is_all_finite()
            && self.prepayment.is_all_finite()
            && self.wal.is_all_finite()
    }
}

impl crate::error::Finite for Pool {
    fn is_all_finite(&self) -> bool {
        self.balance.is_all_finite()
            && self.wac.is_all_finite()
            && self.net_coupon.is_all_finite()
            && self.prepayment.is_all_finite()
    }
}

impl crate::error::Finite for Prepayment {
    #[allow(clippy::match_same_arms)]
    fn is_all_finite(&self) -> bool {
        match self {
            Self::Cpr(x0) => x0.is_all_finite(),
            Self::Psa(x0) => x0.is_all_finite(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn pool(pre: Prepayment) -> Pool {
        Pool {
            balance: 1e6,
            wac: 0.06,
            net_coupon: 0.055,
            wam: 60,
            age: 0,
            prepayment: pre,
        }
    }

    #[test]
    fn mbs_amortises_and_prices() {
        let f = mbs_cashflows(&pool(Prepayment::Cpr(0.0))).unwrap();
        let paid: f64 = f.scheduled_principal.iter().sum();
        assert!((paid - 1e6).abs() < 1e-6);
        let f = mbs_cashflows(&pool(Prepayment::Psa(150.0))).unwrap();
        let paid: f64 = f.scheduled_principal.iter().chain(&f.prepayment).sum();
        assert!((paid - 1e6).abs() < 1e-6);
        let (p, dur, wal) = mbs_price(&pool(Prepayment::Psa(150.0)), 0.055, 0).unwrap();
        assert!((p - 100.0).abs() < 1e-9, "{p}");
        assert!(dur > 0.0 && wal == f.wal);
        let e = |q: Pool| mbs_cashflows(&q).unwrap_err().code;
        let b = pool(Prepayment::Cpr(0.05));
        assert_eq!(
            e(Pool {
                net_coupon: 0.07,
                ..b
            }),
            "E_INPUT"
        );
        assert_eq!(e(Pool { wam: 0, ..b }), "E_INPUT");
        assert_eq!(e(Pool { wac: 0.0, ..b }), "E_DOMAIN");
        assert_eq!(e(pool(Prepayment::Cpr(1.0))), "E_DOMAIN");
        assert_eq!(e(pool(Prepayment::Psa(-1.0))), "E_DOMAIN");
        assert_eq!(mbs_price(&b, 0.05, -1).unwrap_err().code, "E_INPUT");
    }
}
