//! Credit and correlation hedges (`08-hedging/credit-and-correlation-hedges.md`, stage I wave 2).
//!
//! Both stack per-unit risks of the hedge instruments into a square matrix and solve for the
//! quantities that cancel the book's targeted risks, as `hedge.greeks.neutralise` does.

use crate::credit::{self, CdsTrade, Hazard};
use crate::curve::Curve;
use crate::dates::Date;
use crate::error::{Result, fail, finite};
use crate::hedge_solvers::{GreekInstrument, GreekMarket, unit_greeks};
use crate::linalg::{Matrix, singular_values, solve};
use crate::stats::{normal_cdf, normal_pdf};

/// Ruling I-3.
const THRESHOLD: f64 = 1e-12;

/// `E_SINGULAR` unless the smallest singular value is above the threshold times the largest.
fn check_regular(g: &Matrix, what: &str) -> Result<()> {
    let sv = singular_values(g);
    let largest = sv.iter().fold(0.0f64, |m, v| m.max(*v));
    if sv.iter().any(|v| *v <= THRESHOLD * largest) {
        return fail(
            "E_SINGULAR",
            format!("the hedges cannot offset the targets ({what})"),
        );
    }
    Ok(())
}

fn repeated<T: PartialEq>(v: &[T]) -> bool {
    (1..v.len()).any(|i| v[..i].contains(&v[i]))
}

/// A target of `hedge.credit.cds`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CreditTarget {
    Cs01,
    Jtd,
    /// Hazard section `k`, 1-based.
    Bucket(usize),
}

impl CreditTarget {
    /// `CS01`, `JTD` or `BUCKET_k` with `1 <= k <= sections`; anything else is `E_INPUT`.
    ///
    /// # Errors
    /// `E_INPUT` for an unknown name or a bucket outside `1..=sections`.
    pub fn parse(name: &str, sections: usize) -> Result<CreditTarget> {
        let bucket = name
            .strip_prefix("BUCKET_")
            .filter(|k| !k.is_empty() && k.bytes().all(|b| b.is_ascii_digit()))
            .and_then(|k| k.parse::<usize>().ok());
        match (name, bucket) {
            ("CS01", _) => Ok(CreditTarget::Cs01),
            ("JTD", _) => Ok(CreditTarget::Jtd),
            (_, Some(k)) if (1..=sections).contains(&k) => Ok(CreditTarget::Bucket(k)),
            _ => fail("E_INPUT", format!("unknown target {name}")),
        }
    }
}

/// Risks per position: `pv`, `cs01`, `jtd` and one CS01 per hazard section.
#[derive(Debug, Clone, PartialEq)]
pub struct CreditRisk {
    pub pv: f64,
    pub cs01: f64,
    pub jtd: f64,
    pub buckets: Vec<f64>,
}

impl CreditRisk {
    fn get(&self, t: CreditTarget) -> f64 {
        match t {
            CreditTarget::Cs01 => self.cs01,
            CreditTarget::Jtd => self.jtd,
            CreditTarget::Bucket(k) => self.buckets[k - 1],
        }
    }

    fn add_scaled(&mut self, other: &CreditRisk, w: f64) {
        self.pv += w * other.pv;
        self.cs01 += w * other.cs01;
        self.jtd += w * other.jtd;
        for (a, b) in self.buckets.iter_mut().zip(&other.buckets) {
            *a += w * b;
        }
    }
}

/// The market of `hedge.credit.cds`: curves already built, as `credit.cds.price` takes them.
#[derive(Debug, Clone)]
pub struct CreditMarket<'a> {
    pub trade_date: Date,
    pub discount: &'a Curve,
    pub discount_pillars: &'a [Date],
    pub hazard: &'a Hazard,
    pub recovery: f64,
}

/// Outputs of `hedge.credit.cds`. `after.pv` is the book plus hedges.
#[derive(Debug, Clone, PartialEq)]
pub struct CreditHedge {
    pub notionals: Vec<f64>,
    pub book: CreditRisk,
    pub after: CreditRisk,
    pub hedge_upfront: f64,
}

/// `(pv, upfront)` of unit bought protection.
fn unit_price(
    m: &CreditMarket,
    hazard: &Hazard,
    maturity: Date,
    coupon: f64,
) -> Result<(f64, f64)> {
    let trade = CdsTrade {
        maturity,
        coupon,
        notional: 1.0,
        buy: true,
    };
    let p = credit::price(
        m.trade_date,
        m.discount,
        m.discount_pillars,
        hazard,
        m.recovery,
        &trade,
        false,
    )?;
    Ok((p.pv, p.upfront))
}

/// Risks of unit bought protection (ruling I-15, I-16) and its clean upfront.
fn unit_risk(m: &CreditMarket, maturity: Date, coupon: f64) -> Result<(CreditRisk, f64)> {
    let sections = m.hazard.pillars().len();
    let eps = 1e-4 / (1.0 - m.recovery);
    let (pv, upfront) = unit_price(m, m.hazard, maturity, coupon)?;
    let bumped = |shifts: &[f64]| -> Result<f64> {
        let up = unit_price(m, &m.hazard.with_hazard_shifts(shifts), maturity, coupon)?.0;
        let neg: Vec<f64> = shifts.iter().map(|v| -v).collect();
        let down = unit_price(m, &m.hazard.with_hazard_shifts(&neg), maturity, coupon)?.0;
        Ok((up - down) / 2.0)
    };
    let cs01 = bumped(&vec![eps; sections])?;
    let buckets = (0..sections)
        .map(|k| {
            let mut s = vec![0.0; sections];
            s[k] = eps;
            bumped(&s)
        })
        .collect::<Result<Vec<_>>>()?;
    Ok((
        CreditRisk {
            pv,
            cs01,
            jtd: (1.0 - m.recovery) - pv,
            buckets,
        },
        upfront,
    ))
}

/// `hedge.credit.cds`: CDS notionals that cancel the book's targeted CS01, bucket CS01 and jump
/// to default. `targets` are the names as given; `hedges` are `(maturity, coupon)`. The discount
/// interpolation check (R1-4) belongs to the caller, before this.
///
/// # Errors
/// `E_DOMAIN` for a non-finite input, `E_INPUT` (empty lists, target count, unknown or repeated
/// target, maturity on or before the trade date), `E_DOMAIN` (recovery, notional, coupon),
/// `E_SINGULAR`; and the errors of `credit.cds.price`.
pub fn credit_hedge(
    m: &CreditMarket,
    book: &[CdsTrade],
    hedges: &[(Date, f64)],
    targets: &[&str],
) -> Result<CreditHedge> {
    finite("recovery", &m.recovery)?;
    for t in book {
        finite("book", &[t.coupon, t.notional])?;
    }
    for h in hedges {
        finite("hedges", &h.1)?;
    }
    let sections = m.hazard.pillars().len();
    if book.is_empty() || hedges.is_empty() || targets.len() != hedges.len() {
        return fail("E_INPUT", "need a book, hedges, and one target per hedge");
    }
    let targets: Vec<CreditTarget> = targets
        .iter()
        .map(|t| CreditTarget::parse(t, sections))
        .collect::<Result<_>>()?;
    if repeated(&targets) {
        return fail("E_INPUT", "a target is repeated");
    }
    let maturities = book
        .iter()
        .map(|t| t.maturity)
        .chain(hedges.iter().map(|h| h.0));
    if maturities.into_iter().any(|d| d <= m.trade_date) {
        return fail("E_INPUT", "a maturity is on or before the trade date");
    }
    if !(0.0..1.0).contains(&m.recovery)
        || book.iter().any(|t| t.notional < 0.0 || t.coupon < 0.0)
        || hedges.iter().any(|h| h.1 < 0.0)
    {
        return fail(
            "E_DOMAIN",
            "recovery in [0, 1), notionals and coupons non-negative",
        );
    }
    let mut total = CreditRisk {
        pv: 0.0,
        cs01: 0.0,
        jtd: 0.0,
        buckets: vec![0.0; sections],
    };
    for t in book {
        let (r, _) = unit_risk(m, t.maturity, t.coupon)?;
        let side = if t.buy { 1.0 } else { -1.0 };
        total.add_scaled(&r, side * t.notional);
    }
    let units: Vec<(CreditRisk, f64)> = hedges
        .iter()
        .map(|h| unit_risk(m, h.0, h.1))
        .collect::<Result<_>>()?;
    let g: Matrix = targets
        .iter()
        .map(|t| units.iter().map(|u| u.0.get(*t)).collect())
        .collect();
    check_regular(&g, "credit")?;
    let rhs: Vec<f64> = targets.iter().map(|t| -total.get(*t)).collect();
    let notionals = solve(&g, &rhs)?;
    let mut after = total.clone();
    let mut hedge_upfront = 0.0;
    for ((r, upfront), n) in units.iter().zip(&notionals) {
        after.add_scaled(r, *n);
        hedge_upfront += n * upfront;
    }
    Ok(CreditHedge {
        notionals,
        book: total,
        after,
        hedge_upfront,
    })
}

/// The instrument kinds of `hedge.correlation.neutralise`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CorrKind {
    Exchange,
    Call1,
    Put1,
    Call2,
    Put2,
    Underlying1,
    Underlying2,
}

impl CorrKind {
    /// The keys this kind takes besides `instrument` (and `quantity` in the book).
    #[must_use]
    pub const fn keys(self) -> &'static [&'static str] {
        match self {
            CorrKind::Exchange => &["quantity1", "quantity2", "expiry_years"],
            CorrKind::Call1 | CorrKind::Put1 | CorrKind::Call2 | CorrKind::Put2 => {
                &["strike", "expiry_years"]
            }
            CorrKind::Underlying1 | CorrKind::Underlying2 => &[],
        }
    }
}

/// An instrument as given: its kind and every other numeric key it carries, by name.
#[derive(Debug, Clone, PartialEq)]
pub struct CorrLeg {
    pub kind: CorrKind,
    pub fields: Vec<(String, f64)>,
}

impl CorrLeg {
    fn value(&self, k: &str) -> f64 {
        self.fields
            .iter()
            .find(|f| f.0 == k)
            .map_or(f64::NAN, |f| f.1)
    }

    /// Check 1: exactly the keys of the kind (I-17 build note).
    fn keys_match(&self) -> bool {
        let want = self.kind.keys();
        self.fields.len() == want.len()
            && want.iter().all(|k| self.fields.iter().any(|f| f.0 == *k))
    }
}

/// The two-asset market of `hedge.correlation.neutralise`.
#[derive(Debug, Clone, Copy)]
pub struct CorrMarket {
    pub spot1: f64,
    pub spot2: f64,
    pub rate: f64,
    pub yield1: f64,
    pub yield2: f64,
    pub vol1: f64,
    pub vol2: f64,
    pub correlation: f64,
}

/// A target of `hedge.correlation.neutralise`, in the order of the Greek arrays.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CorrTarget {
    Delta1,
    Delta2,
    Vega1,
    Vega2,
    Correlation,
}

/// Outputs of `hedge.correlation.neutralise`; Greeks as
/// `[delta_1, delta_2, vega_1, vega_2, correlation01]`.
#[derive(Debug, Clone, PartialEq)]
pub struct CorrHedge {
    pub quantities: Vec<f64>,
    pub before: [f64; 5],
    pub after: [f64; 5],
}

impl CorrMarket {
    fn spread_variance(&self) -> f64 {
        self.vol1 * self.vol1 + self.vol2 * self.vol2
            - 2.0 * self.correlation * self.vol1 * self.vol2
    }

    /// Per-unit Greeks `[delta_1, delta_2, vega_1, vega_2, correlation01]` of a checked leg.
    fn greeks(&self, leg: &CorrLeg) -> [f64; 5] {
        let vanilla = |asset2: bool, call: bool| {
            let m = GreekMarket {
                spot: if asset2 { self.spot2 } else { self.spot1 },
                rate: self.rate,
                dividend_yield: if asset2 { self.yield2 } else { self.yield1 },
                volatility: if asset2 { self.vol2 } else { self.vol1 },
            };
            let g = unit_greeks(
                &m,
                &GreekInstrument::Option {
                    call,
                    strike: leg.value("strike"),
                    expiry: leg.value("expiry_years"),
                },
            );
            if asset2 {
                [0.0, g[0], 0.0, g[2], 0.0]
            } else {
                [g[0], 0.0, g[2], 0.0, 0.0]
            }
        };
        match leg.kind {
            CorrKind::Underlying1 => [1.0, 0.0, 0.0, 0.0, 0.0],
            CorrKind::Underlying2 => [0.0, 1.0, 0.0, 0.0, 0.0],
            CorrKind::Call1 => vanilla(false, true),
            CorrKind::Put1 => vanilla(false, false),
            CorrKind::Call2 => vanilla(true, true),
            CorrKind::Put2 => vanilla(true, false),
            CorrKind::Exchange => {
                let t = leg.value("expiry_years");
                let (q1, q2) = (leg.value("quantity1"), leg.value("quantity2"));
                let c1 = q1 * (-self.yield1 * t).exp();
                let c2 = q2 * (-self.yield2 * t).exp();
                let (f1, f2) = (c1 * self.spot1, c2 * self.spot2);
                let s = self.spread_variance().sqrt();
                let st = s * t.sqrt();
                let d1 = ((f1 / f2).ln() + s * s * t / 2.0) / st;
                let d2 = d1 - st;
                let dvds = f1 * normal_pdf(d1) * t.sqrt();
                let (v1, v2, rho) = (self.vol1, self.vol2, self.correlation);
                [
                    c1 * normal_cdf(d1),
                    -c2 * normal_cdf(d2),
                    dvds * (v1 - rho * v2) / s,
                    dvds * (v2 - rho * v1) / s,
                    dvds * (-v1 * v2 / s) * 0.01,
                ]
            }
        }
    }
}

const fn corr_index(t: CorrTarget) -> usize {
    match t {
        CorrTarget::Delta1 => 0,
        CorrTarget::Delta2 => 1,
        CorrTarget::Vega1 => 2,
        CorrTarget::Vega2 => 3,
        CorrTarget::Correlation => 4,
    }
}

/// `hedge.correlation.neutralise`: quantities of the hedges that zero the targeted two-asset
/// Greeks, with Margrabe exchange options (I-17, I-18).
///
/// # Errors
/// `E_DOMAIN` for a non-finite input, `E_INPUT` (key sets, no hedges, target count, repeated
/// target), `E_DOMAIN` (market, instrument terms, zero spread volatility with an exchange
/// option), `E_SINGULAR`.
pub fn correlation_hedge(
    m: &CorrMarket,
    book: &[(CorrLeg, f64)],
    hedges: &[CorrLeg],
    targets: &[CorrTarget],
) -> Result<CorrHedge> {
    finite(
        "market",
        &[
            m.spot1,
            m.spot2,
            m.rate,
            m.yield1,
            m.yield2,
            m.vol1,
            m.vol2,
            m.correlation,
        ],
    )?;
    for (leg, q) in book {
        finite("book", &leg.fields.iter().map(|f| f.1).collect::<Vec<_>>())?;
        finite("quantity", q)?;
    }
    for leg in hedges {
        finite(
            "hedges",
            &leg.fields.iter().map(|f| f.1).collect::<Vec<_>>(),
        )?;
    }
    let legs = || book.iter().map(|b| &b.0).chain(hedges);
    if !legs().all(CorrLeg::keys_match) {
        return fail(
            "E_INPUT",
            "an instrument has keys other than those of its kind",
        );
    }
    if hedges.is_empty() || targets.len() != hedges.len() {
        return fail("E_INPUT", "need as many targets as hedges, at least one");
    }
    if repeated(targets) {
        return fail("E_INPUT", "a target is repeated");
    }
    if m.spot1 <= 0.0
        || m.spot2 <= 0.0
        || m.vol1 <= 0.0
        || m.vol2 <= 0.0
        || !(-1.0..=1.0).contains(&m.correlation)
        || legs().any(|l| l.fields.iter().any(|f| f.1 <= 0.0))
    {
        return fail(
            "E_DOMAIN",
            "spots, vols and instrument terms positive, correlation in [-1, 1]",
        );
    }
    if legs().any(|l| l.kind == CorrKind::Exchange) && m.spread_variance() <= 0.0 {
        return fail("E_DOMAIN", "the spread volatility is zero");
    }
    let mut before = [0.0; 5];
    for (leg, q) in book {
        let g = m.greeks(leg);
        for k in 0..5 {
            before[k] += q * g[k];
        }
    }
    let per_hedge: Vec<[f64; 5]> = hedges.iter().map(|h| m.greeks(h)).collect();
    let g: Matrix = targets
        .iter()
        .map(|t| per_hedge.iter().map(|h| h[corr_index(*t)]).collect())
        .collect();
    check_regular(&g, "correlation")?;
    let rhs: Vec<f64> = targets.iter().map(|t| -before[corr_index(*t)]).collect();
    let quantities = solve(&g, &rhs)?;
    let mut after = before;
    for (h, q) in per_hedge.iter().zip(&quantities) {
        for k in 0..5 {
            after[k] += q * h[k];
        }
    }
    Ok(CorrHedge {
        quantities,
        before,
        after,
    })
}
