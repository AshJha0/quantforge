//! Garman-Kohlhagen vanillas, FX delta conventions and smile quotes (`05-volatility/fx-smile.md`,
//! rulings E-A9 to E-A11).

use crate::error::{Result, fail};
use crate::rng::ppnd16;
use crate::stats::{normal_cdf, normal_pdf};

/// Spot `S` (domestic per foreign), flat continuous rates, expiry in years.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Market {
    pub spot: f64,
    pub expiry_years: f64,
    pub domestic_rate: f64,
    pub foreign_rate: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DeltaType {
    Spot,
    Forward,
    SpotPa,
    ForwardPa,
}

impl DeltaType {
    pub const ALL: [DeltaType; 4] = [Self::Spot, Self::Forward, Self::SpotPa, Self::ForwardPa];

    pub fn name(self) -> &'static str {
        match self {
            Self::Spot => "SPOT",
            Self::Forward => "FORWARD",
            Self::SpotPa => "SPOT_PA",
            Self::ForwardPa => "FORWARD_PA",
        }
    }

    pub fn parse(s: &str) -> Option<DeltaType> {
        Self::ALL.into_iter().find(|d| d.name() == s)
    }

    fn is_pa(self) -> bool {
        matches!(self, Self::SpotPa | Self::ForwardPa)
    }

    fn is_spot(self) -> bool {
        matches!(self, Self::Spot | Self::SpotPa)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AtmType {
    Spot,
    Forward,
    Dns,
}

fn positive(v: f64) -> bool {
    v > 0.0
}

impl Market {
    fn check(&self, vol: f64) -> Result<()> {
        if [self.spot, self.expiry_years, vol]
            .into_iter()
            .all(positive)
        {
            Ok(())
        } else {
            fail("E_DOMAIN", "spot, expiry_years and vol must be above 0")
        }
    }

    pub fn forward(&self) -> f64 {
        self.spot * ((self.domestic_rate - self.foreign_rate) * self.expiry_years).exp()
    }

    fn df(&self) -> f64 {
        (-self.foreign_rate * self.expiry_years).exp()
    }

    fn dd(&self) -> f64 {
        (-self.domestic_rate * self.expiry_years).exp()
    }

    fn d1_d2(&self, k: f64, vol: f64) -> (f64, f64) {
        let s = vol * self.expiry_years.sqrt();
        let d1 = (self.forward() / k).ln() / s + s / 2.0;
        (d1, d1 - s)
    }

    fn delta_unchecked(&self, k: f64, vol: f64, call: bool, t: DeltaType) -> f64 {
        let p = if call { 1.0 } else { -1.0 };
        let (d1, d2) = self.d1_d2(k, vol);
        let disc = if t.is_spot() { self.df() } else { 1.0 };
        if t.is_pa() {
            p * disc * (k / self.forward()) * normal_cdf(p * d2)
        } else {
            p * disc * normal_cdf(p * d1)
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Price {
    pub price: f64,
    pub premium_pct_foreign: f64,
    pub forward: f64,
    pub delta: f64,
    pub gamma: f64,
    pub vega: f64,
}

pub fn price(m: &Market, strike: f64, vol: f64, call: bool, notional: f64) -> Result<Price> {
    crate::error::finite("m", &m)?;
    crate::error::finite("strike", &strike)?;
    crate::error::finite("vol", &vol)?;
    crate::error::finite("notional", &notional)?;
    m.check(vol)?;
    if !positive(strike) || !positive(notional) {
        return fail("E_DOMAIN", "strike and notional must be above 0");
    }
    let p = if call { 1.0 } else { -1.0 };
    let (f, t) = (m.forward(), m.expiry_years);
    let (d1, d2) = m.d1_d2(strike, vol);
    let unit = p * m.dd() * (f * normal_cdf(p * d1) - strike * normal_cdf(p * d2));
    Ok(Price {
        price: notional * unit,
        premium_pct_foreign: unit / m.spot,
        forward: f,
        delta: notional * p * m.df() * normal_cdf(p * d1),
        gamma: notional * m.df() * normal_pdf(d1) / (m.spot * vol * t.sqrt()),
        vega: notional * m.spot * m.df() * normal_pdf(d1) * t.sqrt(),
    })
}

/// The four deltas in `DeltaType::ALL` order.
pub fn deltas(m: &Market, strike: f64, vol: f64, call: bool) -> Result<[f64; 4]> {
    crate::error::finite("m", &m)?;
    crate::error::finite("strike", &strike)?;
    crate::error::finite("vol", &vol)?;
    m.check(vol)?;
    if !positive(strike) {
        return fail("E_DOMAIN", "strike must be above 0");
    }
    Ok(DeltaType::ALL.map(|t| m.delta_unchecked(strike, vol, call, t)))
}

/// Bisection on `x` in `[lo, hi]` to the last representable midpoint, `f(lo)` and `f(hi)` of
/// opposite sign.
fn bisect(f: &dyn Fn(f64) -> f64, mut lo: f64, mut hi: f64) -> f64 {
    let low_sign = f(lo) < 0.0;
    for _ in 0..2000 {
        let mid = 0.5 * (lo + hi);
        if mid <= lo || mid >= hi {
            break;
        }
        if (f(mid) < 0.0) == low_sign {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    0.5 * (lo + hi)
}

/// `d2*` with `v sqrt T N(d2) = n(d2)`: the strike of maximum PA call delta (ruling E-A10).
fn pa_peak_d2(s: f64) -> f64 {
    // h(d) = s N(d) - n(d) increases from -0 at -inf to s at +inf; its root lies below s.
    let h = |d: f64| s * normal_cdf(d) - normal_pdf(d);
    let mut lo = -1.0;
    while h(lo) > 0.0 {
        lo *= 2.0;
    }
    bisect(&h, lo, s.max(1.0) + 10.0)
}

/// The strike with the given delta. Non-PA in closed form; PA by bisection on `ln(K/F)`.
pub fn strike_from_delta(
    m: &Market,
    vol: f64,
    call: bool,
    delta: f64,
    t: DeltaType,
) -> Result<f64> {
    crate::error::finite("m", &m)?;
    crate::error::finite("vol", &vol)?;
    crate::error::finite("delta", &delta)?;
    m.check(vol)?;
    let disc = if t.is_spot() { m.df() } else { 1.0 };
    let (f, s) = (m.forward(), vol * m.expiry_years.sqrt());
    let sign_ok = if call { delta > 0.0 } else { delta < 0.0 };
    if !sign_ok {
        return fail(
            "E_DOMAIN",
            "a call delta must be above 0 and a put delta below 0",
        );
    }
    if !t.is_pa() {
        if delta.abs() >= disc {
            return fail("E_DOMAIN", "delta is out of reach");
        }
        let p = if call { 1.0 } else { -1.0 };
        let d1 = p * ppnd16(delta.abs() / disc);
        return Ok(f * (-s * d1 + s * s / 2.0).exp());
    }
    let at = |x: f64| m.delta_unchecked(f * x.exp(), vol, call, t) - delta;
    if call {
        let d2 = pa_peak_d2(s);
        let x_peak = -s * d2 - s * s / 2.0;
        if at(x_peak) <= 0.0 {
            return fail(
                "E_DOMAIN",
                "premium-adjusted call delta at or above its maximum",
            );
        }
        let mut hi = x_peak + s.max(0.1);
        while at(hi) > 0.0 {
            hi += 2.0 * s.max(0.1);
        }
        return Ok(f * bisect(&at, x_peak, hi).exp());
    }
    // PA put delta falls from 0 towards -inf as K grows.
    let (mut lo, mut hi) = (-s.max(0.1), s.max(0.1));
    while at(lo) < 0.0 {
        lo *= 2.0;
    }
    while at(hi) > 0.0 {
        hi *= 2.0;
    }
    Ok(f * bisect(&at, lo, hi).exp())
}

pub fn atm_strike(m: &Market, vol: f64, atm: AtmType, t: DeltaType) -> Result<f64> {
    crate::error::finite("m", &m)?;
    crate::error::finite("vol", &vol)?;
    m.check(vol)?;
    let half = vol * vol * m.expiry_years / 2.0;
    Ok(match atm {
        AtmType::Spot => m.spot,
        AtmType::Forward => m.forward(),
        AtmType::Dns if t.is_pa() => m.forward() * (-half).exp(),
        AtmType::Dns => m.forward() * half.exp(),
    })
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Smile {
    pub atm_strike: f64,
    pub call_vol: f64,
    pub put_vol: f64,
    pub call_strike: f64,
    pub put_strike: f64,
}

/// Smile strangle quotes (ruling E-A11): `call_vol + put_vol = 2(atm + bf)`.
pub struct Quotes {
    pub atm_vol: f64,
    pub rr: f64,
    pub bf: f64,
    pub delta: f64,
}

pub fn smile(m: &Market, q: &Quotes, t: DeltaType, atm: AtmType) -> Result<Smile> {
    crate::error::finite("m", &m)?;
    crate::error::finite("q", &q)?;
    m.check(q.atm_vol)?;
    if !(q.delta > 0.0 && q.delta < 0.5) {
        return fail("E_DOMAIN", "delta must lie in (0, 0.5)");
    }
    let call_vol = q.atm_vol + q.bf + q.rr / 2.0;
    let put_vol = q.atm_vol + q.bf - q.rr / 2.0;
    if !positive(call_vol) || !positive(put_vol) {
        return fail("E_DOMAIN", "a wing vol is not above 0");
    }
    Ok(Smile {
        atm_strike: atm_strike(m, q.atm_vol, atm, t)?,
        call_vol,
        put_vol,
        call_strike: strike_from_delta(m, call_vol, true, q.delta, t)?,
        put_strike: strike_from_delta(m, put_vol, false, -q.delta, t)?,
    })
}

impl crate::error::Finite for Market {
    fn is_all_finite(&self) -> bool {
        self.spot.is_all_finite()
            && self.expiry_years.is_all_finite()
            && self.domestic_rate.is_all_finite()
            && self.foreign_rate.is_all_finite()
    }
}

impl crate::error::Finite for Price {
    fn is_all_finite(&self) -> bool {
        self.price.is_all_finite()
            && self.premium_pct_foreign.is_all_finite()
            && self.forward.is_all_finite()
            && self.delta.is_all_finite()
            && self.gamma.is_all_finite()
            && self.vega.is_all_finite()
    }
}

impl crate::error::Finite for Quotes {
    fn is_all_finite(&self) -> bool {
        self.atm_vol.is_all_finite()
            && self.rr.is_all_finite()
            && self.bf.is_all_finite()
            && self.delta.is_all_finite()
    }
}

impl crate::error::Finite for Smile {
    fn is_all_finite(&self) -> bool {
        self.atm_strike.is_all_finite()
            && self.call_vol.is_all_finite()
            && self.put_vol.is_all_finite()
            && self.call_strike.is_all_finite()
            && self.put_strike.is_all_finite()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const EURUSD: Market = Market {
        spot: 1.085,
        expiry_years: 0.25,
        domestic_rate: 0.043,
        foreign_rate: 0.031,
    };

    const USDMXN: Market = Market {
        spot: 18.4,
        expiry_years: 1.0,
        domestic_rate: 0.105,
        foreign_rate: 0.043,
    };

    #[test]
    fn price_parity_and_greeks() {
        let m = EURUSD;
        let c = price(&m, 1.1, 0.075, true, 1e6).unwrap();
        let p = price(&m, 1.1, 0.075, false, 1e6).unwrap();
        let parity = 1e6 * (m.spot * m.df() - 1.1 * m.dd());
        assert!((c.price - p.price - parity).abs() < 1e-8);
        assert!((c.delta - p.delta - 1e6 * m.df()).abs() < 1e-8);
        assert!((c.gamma - p.gamma).abs() < 1e-9 && (c.vega - p.vega).abs() < 1e-9);
        let h = 1e-6;
        let up = price(
            &Market {
                spot: m.spot + h,
                ..m
            },
            1.1,
            0.075,
            true,
            1e6,
        )
        .unwrap();
        let dn = price(
            &Market {
                spot: m.spot - h,
                ..m
            },
            1.1,
            0.075,
            true,
            1e6,
        )
        .unwrap();
        assert!(((up.price - dn.price) / (2.0 * h) - c.delta).abs() < 1e-3);
        assert!((c.premium_pct_foreign - c.price / 1e6 / m.spot).abs() < 1e-15);
        assert_eq!(
            price(&m, 0.0, 0.075, true, 1.0).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            price(&m, 1.1, 0.075, true, 0.0).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(price(&m, 1.1, 0.0, true, 1.0).unwrap_err().code, "E_DOMAIN");
    }

    #[test]
    fn deltas_round_trip_for_every_type() {
        for m in [EURUSD, USDMXN] {
            for call in [true, false] {
                for k in [0.8, 0.95, 1.0, 1.05, 1.25] {
                    let k = k * m.forward();
                    let d = deltas(&m, k, 0.16, call).unwrap();
                    for (t, dv) in DeltaType::ALL.into_iter().zip(d) {
                        if t.is_pa() && call {
                            continue;
                        }
                        let back = strike_from_delta(&m, 0.16, call, dv, t).unwrap();
                        assert!((back / k - 1.0).abs() < 1e-9, "{t:?} {call} {k}");
                    }
                }
            }
        }
        assert_eq!(
            deltas(&EURUSD, -1.0, 0.1, true).unwrap_err().code,
            "E_DOMAIN"
        );
    }

    #[test]
    fn pa_call_takes_the_upper_root() {
        let m = USDMXN;
        let k = 1.2 * m.forward();
        let d = m.delta_unchecked(k, 0.16, true, DeltaType::ForwardPa);
        let back = strike_from_delta(&m, 0.16, true, d, DeltaType::ForwardPa).unwrap();
        assert!((back / k - 1.0).abs() < 1e-9);
        let e = strike_from_delta(&m, 0.16, true, 0.74, DeltaType::ForwardPa).unwrap_err();
        assert_eq!(e.code, "E_DOMAIN");
        let spa = strike_from_delta(&m, 0.16, true, 0.25, DeltaType::SpotPa).unwrap();
        let got = m.delta_unchecked(spa, 0.16, true, DeltaType::SpotPa);
        assert!((got - 0.25).abs() < 1e-12);
    }

    #[test]
    fn range_checks() {
        let m = USDMXN;
        let code = |c, d, t| strike_from_delta(&m, 0.16, c, d, t).unwrap_err().code;
        assert_eq!(code(true, -0.25, DeltaType::Spot), "E_DOMAIN");
        assert_eq!(code(false, 0.25, DeltaType::Spot), "E_DOMAIN");
        assert_eq!(code(true, 0.97, DeltaType::Spot), "E_DOMAIN");
        assert_eq!(code(false, -1.0, DeltaType::Forward), "E_DOMAIN");
        assert!(strike_from_delta(&m, 0.16, false, -3.0, DeltaType::ForwardPa).is_ok());
    }

    #[test]
    fn atm_types() {
        let m = EURUSD;
        let f = m.forward();
        let half = 0.075f64 * 0.075 * 0.25 / 2.0;
        assert_eq!(
            atm_strike(&m, 0.075, AtmType::Spot, DeltaType::Spot).unwrap(),
            m.spot
        );
        assert_eq!(
            atm_strike(&m, 0.075, AtmType::Forward, DeltaType::SpotPa).unwrap(),
            f
        );
        let dns = atm_strike(&m, 0.075, AtmType::Dns, DeltaType::Forward).unwrap();
        assert!((dns - f * half.exp()).abs() < 1e-15);
        let pa = atm_strike(&m, 0.075, AtmType::Dns, DeltaType::ForwardPa).unwrap();
        assert!((pa - f * (-half).exp()).abs() < 1e-15);
        // DNS: call and put forward deltas cancel.
        let c = m.delta_unchecked(dns, 0.075, true, DeltaType::Forward);
        let p = m.delta_unchecked(dns, 0.075, false, DeltaType::Forward);
        assert!((c + p).abs() < 1e-12);
        assert_eq!(DeltaType::parse("SPOT_PA"), Some(DeltaType::SpotPa));
        assert_eq!(DeltaType::parse("X"), None);
    }

    #[test]
    fn smile_from_quotes() {
        let q = Quotes {
            atm_vol: 0.075,
            rr: -0.0045,
            bf: 0.002,
            delta: 0.25,
        };
        let s = smile(&EURUSD, &q, DeltaType::Spot, AtmType::Dns).unwrap();
        assert!((s.call_vol - 0.07475).abs() < 1e-15 && (s.put_vol - 0.07925).abs() < 1e-15);
        assert!(s.put_strike < s.atm_strike && s.atm_strike < s.call_strike);
        let bad = Quotes { bf: -0.2, ..q };
        assert_eq!(
            smile(&EURUSD, &bad, DeltaType::Spot, AtmType::Dns)
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        let bad = Quotes { delta: 0.5, ..q };
        assert_eq!(
            smile(&EURUSD, &bad, DeltaType::Spot, AtmType::Dns)
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
    }
}
