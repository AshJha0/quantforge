//! Venue analytics: markouts, fill rates, toxicity (`specifications/10-execution/venue-analytics.md`,
//! stage H H-16; rulings HR-72, HR-75 as amended (HR-66)). A port of the Python build's
//! `venue_analytics.py` and the Java `VenueAnalytics`. Each input number is read as the decimal it
//! prints as (shortest round trip, Python's `repr`), every sum and the sign test of the toxicity
//! indicator are exact on those decimals, and each output is rounded once to binary64 (the spec's
//! "Exact sums" paragraph). The exact arithmetic is the small unbounded integer below rather than
//! [`crate::decimal::Dec`], whose HR-57 range (36 digits) a product of two 17-digit inputs times 1e4
//! can leave; Python's `Fraction` and Java's `BigDecimal` have no such bound.
use crate::error::Result;
use crate::micro_est::{fail, finite};
use std::cmp::Ordering;

/// A non-negative integer, little-endian base 2^32 limbs, no high zero limbs (zero is empty).
#[derive(Debug, Clone, PartialEq, Eq)]
struct Mag(Vec<u32>);

impl Mag {
    fn trim(mut self) -> Mag {
        while self.0.last() == Some(&0) {
            self.0.pop();
        }
        self
    }

    fn is_zero(&self) -> bool {
        self.0.is_empty()
    }

    fn cmp(&self, o: &Mag) -> Ordering {
        self.0
            .len()
            .cmp(&o.0.len())
            .then_with(|| self.0.iter().rev().cmp(o.0.iter().rev()))
    }

    fn add(&self, o: &Mag) -> Mag {
        let mut out = Vec::with_capacity(self.0.len().max(o.0.len()) + 1);
        let mut carry = 0u64;
        for i in 0..self.0.len().max(o.0.len()) {
            let s = u64::from(*self.0.get(i).unwrap_or(&0))
                + u64::from(*o.0.get(i).unwrap_or(&0))
                + carry;
            out.push(s as u32);
            carry = s >> 32;
        }
        out.push(carry as u32);
        Mag(out).trim()
    }

    /// `self - o` for `self >= o`.
    fn sub(&self, o: &Mag) -> Mag {
        let mut out = Vec::with_capacity(self.0.len());
        let mut borrow = 0i64;
        for i in 0..self.0.len() {
            let mut d = i64::from(self.0[i]) - i64::from(*o.0.get(i).unwrap_or(&0)) - borrow;
            borrow = i64::from(d < 0);
            if d < 0 {
                d += 1 << 32;
            }
            out.push(d as u32);
        }
        Mag(out).trim()
    }

    fn mul(&self, o: &Mag) -> Mag {
        let mut out = vec![0u32; self.0.len() + o.0.len()];
        for (i, &a) in self.0.iter().enumerate() {
            let mut carry = 0u64;
            for (j, &b) in o.0.iter().enumerate() {
                let t = u64::from(a) * u64::from(b) + u64::from(out[i + j]) + carry;
                out[i + j] = t as u32;
                carry = t >> 32;
            }
            out[i + o.0.len()] = carry as u32;
        }
        Mag(out).trim()
    }

    fn mul_small(&self, m: u32, add: u32) -> Mag {
        let mut out = Vec::with_capacity(self.0.len() + 1);
        let mut carry = u64::from(add);
        for &a in &self.0 {
            let t = u64::from(a) * u64::from(m) + carry;
            out.push(t as u32);
            carry = t >> 32;
        }
        out.push(carry as u32);
        Mag(out).trim()
    }

    fn mul_pow10(&self, mut n: u32) -> Mag {
        let mut r = self.clone();
        while n >= 9 {
            r = r.mul_small(1_000_000_000, 0);
            n -= 9;
        }
        r.mul_small(10u32.pow(n), 0)
    }

    fn bit_len(&self) -> u64 {
        self.0.last().map_or(0, |&h| {
            32 * (self.0.len() as u64 - 1) + u64::from(32 - h.leading_zeros())
        })
    }

    fn shl(&self, n: u64) -> Mag {
        let (words, bits) = ((n / 32) as usize, (n % 32) as u32);
        let mut out = vec![0u32; words];
        let mut carry = 0u32;
        for &a in &self.0 {
            if bits == 0 {
                out.push(a);
            } else {
                out.push((a << bits) | carry);
                carry = a >> (32 - bits);
            }
        }
        out.push(carry);
        Mag(out).trim()
    }
}

/// An exact decimal `sign * mag * 10^-scale`.
#[derive(Debug, Clone)]
struct Exact {
    neg: bool,
    mag: Mag,
    scale: u32,
}

impl Exact {
    fn zero() -> Exact {
        Exact {
            neg: false,
            mag: Mag(Vec::new()),
            scale: 0,
        }
    }

    fn int(n: u32, neg: bool) -> Exact {
        Exact {
            neg,
            mag: Mag(vec![n]).trim(),
            scale: 0,
        }
    }

    /// The decimal a double prints as (shortest round trip, as Python's `repr`).
    fn of(x: f64) -> Exact {
        let text = format!("{:e}", x.abs());
        let (mant, exp) = text.split_once('e').unwrap_or((&text, "0"));
        let exp: i64 = exp.parse().unwrap_or(0);
        let (ip, fp) = mant.split_once('.').unwrap_or((mant, ""));
        let mut mag = Mag(Vec::new());
        for b in ip.bytes().chain(fp.bytes()) {
            mag = mag.mul_small(10, u32::from(b - b'0'));
        }
        let scale = fp.len() as i64 - exp;
        let (mag, scale) = if scale < 0 {
            (mag.mul_pow10((-scale) as u32), 0)
        } else {
            (mag, scale as u32)
        };
        Exact {
            neg: x.is_sign_negative() && !mag.is_zero(),
            mag,
            scale,
        }
    }

    fn at(&self, scale: u32) -> Mag {
        self.mag.mul_pow10(scale - self.scale)
    }

    fn signum(&self) -> i32 {
        if self.mag.is_zero() {
            0
        } else if self.neg {
            -1
        } else {
            1
        }
    }

    fn add(&self, o: &Exact) -> Exact {
        let s = self.scale.max(o.scale);
        let (a, b) = (self.at(s), o.at(s));
        let (neg, mag) = if self.neg == o.neg {
            (self.neg, a.add(&b))
        } else if a.cmp(&b) == Ordering::Less {
            (o.neg, b.sub(&a))
        } else {
            (self.neg, a.sub(&b))
        };
        Exact {
            neg: neg && !mag.is_zero(),
            mag,
            scale: s,
        }
    }

    fn neg(&self) -> Exact {
        Exact {
            neg: !self.neg && !self.mag.is_zero(),
            ..self.clone()
        }
    }

    fn sub(&self, o: &Exact) -> Exact {
        self.add(&o.neg())
    }

    fn mul(&self, o: &Exact) -> Exact {
        let mag = self.mag.mul(&o.mag);
        Exact {
            neg: self.neg != o.neg && !mag.is_zero(),
            mag,
            scale: self.scale + o.scale,
        }
    }

    fn cmp(&self, o: &Exact) -> Ordering {
        match (self.signum(), o.signum()) {
            (a, b) if a != b => a.cmp(&b),
            (0, _) => Ordering::Equal,
            (s, _) => {
                let k = self.scale.max(o.scale);
                let c = self.at(k).cmp(&o.at(k));
                if s < 0 { c.reverse() } else { c }
            }
        }
    }
}

/// Java's `Math.scalb`: one multiplication by `2^(n rem 512)`, then steps of `2^±512`.
fn scalb(mut d: f64, n: i64) -> f64 {
    let n = n.clamp(-2099, 2099);
    let first = n % 512;
    d *= 2f64.powi(first as i32);
    let mut rest = n - first;
    let step = if rest < 0 {
        2f64.powi(-512)
    } else {
        2f64.powi(512)
    };
    while rest != 0 {
        d *= step;
        rest -= if rest < 0 { -512 } else { 512 };
    }
    d
}

/// `a / b` correctly rounded to binary64 (`b` non-zero), as Python's `float(Fraction)`.
fn ratio(a: &Exact, b: &Exact) -> f64 {
    if a.mag.is_zero() {
        return 0.0;
    }
    let (p, q) = if b.scale >= a.scale {
        (a.mag.mul_pow10(b.scale - a.scale), b.mag.clone())
    } else {
        (a.mag.clone(), b.mag.mul_pow10(a.scale - b.scale))
    };
    let shift = 55 - (p.bit_len() as i64 - q.bit_len() as i64);
    let (mut n, d) = if shift >= 0 {
        (p.shl(shift as u64), q)
    } else {
        (p, q.shl((-shift) as u64))
    };
    let mut m: u64 = 0;
    for bit in (0..=56u64).rev() {
        let t = d.shl(bit);
        if n.cmp(&t) != Ordering::Less {
            n = n.sub(&t);
            m |= 1 << bit;
        }
    }
    if !n.is_zero() {
        m |= 1; // sticky bit: the one rounding to 53 bits below is then correct
    }
    let v = scalb(m as f64, -shift);
    if a.neg == b.neg { v } else { -v }
}

/// A fill; `buy` false is a sell.
#[derive(Debug, Clone, PartialEq)]
pub struct Fill {
    pub venue: String,
    pub buy: bool,
    pub quantity: f64,
    pub price: f64,
    pub t: f64,
}

/// Child orders sent to a venue and the quantity filled.
#[derive(Debug, Clone, PartialEq)]
pub struct Order {
    pub venue: String,
    pub sent: f64,
    pub filled: f64,
}

/// One row of the markout table.
#[derive(Debug, Clone, PartialEq)]
pub struct Markout {
    pub venue: String,
    pub h: f64,
    pub markout: f64,
    pub markout_bps: f64,
    pub toxicity: f64,
}

/// Fill rates by venue (code-point order) and the markout rows.
#[derive(Debug, Clone, PartialEq)]
pub struct Analytics {
    pub fill_rates: Vec<(String, f64)>,
    pub markouts: Vec<Markout>,
}

/// Distinct names in code-point order (Rust's `str` order on UTF-8 bytes).
fn venues<'a>(names: impl Iterator<Item = &'a str>) -> Vec<&'a str> {
    let mut v: Vec<&str> = names.collect();
    v.sort_unstable();
    v.dedup();
    v
}

/// The last mid stamped at or before u (`bisect_right`).
fn mid_at<'a>(times: &[Exact], values: &'a [Exact], u: &Exact) -> Result<&'a Exact> {
    let lo = times.partition_point(|t| u.cmp(t) != Ordering::Less);
    if lo == 0 {
        return Err(fail(
            "E_INPUT",
            "no mid at or before a fill time plus horizon",
            "fills",
        ));
    }
    Ok(&values[lo - 1])
}

/// `exec.venue.analytics`: per venue and horizon, markout, `markout_bps` and toxicity; per venue
/// `fill_rate`. The mid at u is the last mid stamped at or before u (HR-72). `mids` rows are (t, mid).
pub fn analytics(
    mids: &[(f64, f64)],
    fills: &[Fill],
    orders: &[Order],
    horizons: &[f64],
) -> Result<Analytics> {
    for m in mids {
        finite("mids", &[m.0, m.1])?;
    }
    for f in fills {
        finite("fills", &[f.quantity, f.price, f.t])?;
    }
    for o in orders {
        finite("orders", &[o.sent, o.filled])?;
    }
    finite("horizons", horizons)?;
    // HR-75 as amended (HR-66): structural E_INPUT first, then E_DOMAIN, then the mid lookups
    if orders.iter().any(|o| o.filled > o.sent) {
        return Err(fail("E_INPUT", "filled exceeds sent", "orders"));
    }
    let times: Vec<Exact> = mids.iter().map(|m| Exact::of(m.0)).collect();
    if times
        .windows(2)
        .any(|w| w[1].cmp(&w[0]) != Ordering::Greater)
    {
        return Err(fail(
            "E_INPUT",
            "mid times must be strictly increasing",
            "mids",
        ));
    }
    let checks: [(bool, &str, &str); 6] = [
        (
            mids.iter().any(|m| m.1 <= 0.0),
            "mids must be positive",
            "mids",
        ),
        (
            fills.iter().any(|f| f.price <= 0.0),
            "fill prices must be positive",
            "fills",
        ),
        (
            fills.iter().any(|f| f.quantity <= 0.0),
            "fill quantities must be positive",
            "fills",
        ),
        (
            orders.iter().any(|o| o.sent <= 0.0),
            "sent must be positive",
            "orders",
        ),
        (
            orders.iter().any(|o| o.filled < 0.0),
            "filled must be non-negative",
            "orders",
        ),
        (
            horizons.iter().any(|h| *h < 0.0),
            "horizons must be non-negative",
            "horizons",
        ),
    ];
    if let Some((_, why, field)) = checks.iter().find(|c| c.0) {
        return Err(fail("E_DOMAIN", why, field));
    }
    let values: Vec<Exact> = mids.iter().map(|m| Exact::of(m.1)).collect();
    let hs: Vec<Exact> = horizons.iter().map(|h| Exact::of(*h)).collect();
    let ten_k = Exact::int(10_000, false);
    let mut markouts = Vec::new();
    for venue in venues(fills.iter().map(|f| f.venue.as_str())) {
        let mut mine = Vec::new(); // side, q, p, t
        let (mut sq, mut sqp) = (Exact::zero(), Exact::zero());
        for f in fills.iter().filter(|f| f.venue == venue) {
            let (q, p) = (Exact::of(f.quantity), Exact::of(f.price));
            sq = sq.add(&q);
            sqp = sqp.add(&q.mul(&p));
            mine.push((Exact::int(1, !f.buy), q, p, Exact::of(f.t)));
        }
        for (k, h) in hs.iter().enumerate() {
            let (mut num, mut toxic) = (Exact::zero(), Exact::zero());
            for (s, q, p, t) in &mine {
                let mv = s.mul(&mid_at(&times, &values, &t.add(h))?.sub(p));
                num = num.add(&q.mul(&mv));
                if mv.signum() < 0 {
                    toxic = toxic.add(q);
                }
            }
            markouts.push(Markout {
                venue: venue.to_string(),
                h: horizons[k],
                markout: ratio(&num, &sq),
                markout_bps: ratio(&num.mul(&ten_k), &sqp),
                toxicity: ratio(&toxic, &sq),
            });
        }
    }
    let mut fill_rates = Vec::new();
    for venue in venues(orders.iter().map(|o| o.venue.as_str())) {
        let (mut sent, mut got) = (Exact::zero(), Exact::zero());
        for o in orders.iter().filter(|o| o.venue == venue) {
            sent = sent.add(&Exact::of(o.sent));
            got = got.add(&Exact::of(o.filled));
        }
        fill_rates.push((venue.to_string(), ratio(&got, &sent)));
    }
    Ok(Analytics {
        fill_rates,
        markouts,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exact_reads_shortest_decimal() {
        let a = Exact::of(0.1).add(&Exact::of(0.2));
        assert_eq!(a.cmp(&Exact::of(0.3)), Ordering::Equal);
        assert_eq!(ratio(&Exact::of(1.0), &Exact::of(3.0)), 1.0 / 3.0);
        assert_eq!(ratio(&Exact::of(-7e4), &Exact::of(30007.0)), -7e4 / 30007.0);
        assert_eq!(ratio(&Exact::of(1e300), &Exact::of(1e-300)), f64::INFINITY);
        assert_eq!(ratio(&Exact::of(1.5e-323), &Exact::of(1.0)), 1.5e-323);
        assert_eq!(Exact::of(-0.0).signum(), 0);
        assert_eq!(Exact::of(-2.5).cmp(&Exact::of(-2.4)), Ordering::Less);
        assert_eq!(Exact::of(1e20).sub(&Exact::of(1e20)).signum(), 0);
    }
}
