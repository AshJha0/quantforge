//! Cross-asset hedge, equity and rates (`08-hedging/cross-asset-hedge.md`, stage I wave 3).
//!
//! Risks are half-differences of repriced values (ruling I-21): `EQ01` for a 1% equity move and
//! `KR01_k` for a 1bp move of pillar `k`'s zero rate. The hedge is the wave 1 `hedge.qp.solve`.

use crate::error::{Result, fail, finite};
use crate::hedge_solvers::{Costs, QpProblem, Singular, qp_solve};
use crate::linalg::Matrix;
use crate::stats::normal_cdf;

/// The instrument kinds of `hedge.crossasset.solve`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum XaKind {
    Call,
    Put,
    Forward,
    Zcb,
    Underlying,
}

impl XaKind {
    /// The keys this kind takes besides `instrument` (and `quantity` in the book).
    #[must_use]
    pub const fn keys(self) -> &'static [&'static str] {
        match self {
            XaKind::Call | XaKind::Put | XaKind::Forward => &["strike", "expiry_years"],
            XaKind::Zcb => &["expiry_years", "notional"],
            XaKind::Underlying => &[],
        }
    }
}

/// An instrument as given: its kind and every other numeric key it carries, by name.
#[derive(Debug, Clone, PartialEq)]
pub struct XaLeg {
    pub kind: XaKind,
    pub fields: Vec<(String, f64)>,
}

impl XaLeg {
    fn value(&self, k: &str) -> f64 {
        self.fields
            .iter()
            .find(|f| f.0 == k)
            .map_or(f64::NAN, |f| f.1)
    }

    fn keys_match(&self) -> bool {
        let want = self.kind.keys();
        self.fields.len() == want.len()
            && want.iter().all(|k| self.fields.iter().any(|f| f.0 == *k))
    }
}

/// The zero curve of ruling I-20: linear in time between pillars, flat before the first, not
/// defined after the last.
#[derive(Debug, Clone, PartialEq)]
pub struct ZeroCurve {
    pub times: Vec<f64>,
    pub zero_rates: Vec<f64>,
}

impl ZeroCurve {
    /// `z(T)` for `T` at most the last pillar (checked by the caller).
    fn zero(&self, t: f64) -> f64 {
        let (ts, zs) = (&self.times, &self.zero_rates);
        if t <= ts[0] {
            return zs[0];
        }
        let i = ts.partition_point(|x| *x < t).min(ts.len() - 1);
        let (t0, t1) = (ts[i - 1], ts[i]);
        zs[i - 1] + (zs[i] - zs[i - 1]) * (t - t0) / (t1 - t0)
    }

    fn discount(&self, t: f64) -> f64 {
        (-self.zero(t) * t).exp()
    }

    fn bumped(&self, k: usize, dz: f64) -> ZeroCurve {
        let mut c = self.clone();
        c.zero_rates[k] += dz;
        c
    }
}

/// The market of `hedge.crossasset.solve`.
#[derive(Debug, Clone, PartialEq)]
pub struct XaMarket {
    pub spot: f64,
    pub dividend_yield: f64,
    pub volatility: f64,
    pub curve: ZeroCurve,
}

/// Outputs of `hedge.crossasset.solve`.
#[derive(Debug, Clone, PartialEq)]
pub struct XaHedge {
    pub positions: Vec<f64>,
    pub book_risk: Vec<f64>,
    pub residual_risk: Vec<f64>,
    pub objective: f64,
}

/// Value of one unit of a checked leg at spot `s` on `curve`.
fn value(leg: &XaLeg, s: f64, q: f64, vol: f64, curve: &ZeroCurve) -> f64 {
    match leg.kind {
        XaKind::Underlying => s,
        XaKind::Zcb => {
            let t = leg.value("expiry_years");
            leg.value("notional") * curve.discount(t)
        }
        XaKind::Forward => {
            let t = leg.value("expiry_years");
            s * (-q * t).exp() - leg.value("strike") * curve.discount(t)
        }
        XaKind::Call | XaKind::Put => {
            let (k, t) = (leg.value("strike"), leg.value("expiry_years"));
            let (fwd, df) = (s * (-q * t).exp(), curve.discount(t));
            let vs = vol * t.sqrt();
            let d1 = ((s / k).ln() + (curve.zero(t) - q + vol * vol / 2.0) * t) / vs;
            let d2 = d1 - vs;
            if leg.kind == XaKind::Call {
                fwd * normal_cdf(d1) - k * df * normal_cdf(d2)
            } else {
                k * df * normal_cdf(-d2) - fwd * normal_cdf(-d1)
            }
        }
    }
}

/// `[EQ01, KR01_1 .. KR01_P]` of one unit (ruling I-21).
fn risks(m: &XaMarket, leg: &XaLeg) -> Vec<f64> {
    let (q, v) = (m.dividend_yield, m.volatility);
    let mut out = vec![
        (value(leg, 1.01 * m.spot, q, v, &m.curve) - value(leg, 0.99 * m.spot, q, v, &m.curve))
            / 2.0,
    ];
    for k in 0..m.curve.times.len() {
        let up = value(leg, m.spot, q, v, &m.curve.bumped(k, 1e-4));
        let down = value(leg, m.spot, q, v, &m.curve.bumped(k, -1e-4));
        out.push((up - down) / 2.0);
    }
    out
}

/// `hedge.crossasset.solve`: hedge positions that minimise the weighted equity and key-rate
/// risk left over, by `hedge.qp.solve`.
///
/// # Errors
/// `E_DOMAIN` for a non-finite input; `E_INPUT` (curve, key sets, empty lists, weights length,
/// an expiry beyond the last pillar); `E_DOMAIN` (spot, volatility, weights, ridge, terms);
/// `E_SINGULAR` from the solve.
pub fn crossasset_solve(
    m: &XaMarket,
    book: &[(XaLeg, f64)],
    hedges: &[XaLeg],
    weights: &[f64],
    ridge: f64,
) -> Result<XaHedge> {
    finite("market", &[m.spot, m.dividend_yield, m.volatility, ridge])?;
    finite("curve", &[&m.curve.times, &m.curve.zero_rates])?;
    finite("weights", &weights)?;
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
    let c = &m.curve;
    let p = c.times.len();
    if p == 0
        || c.zero_rates.len() != p
        || c.times[0] <= 0.0
        || c.times.windows(2).any(|w| w[1] <= w[0])
    {
        return fail(
            "E_INPUT",
            "curve times must increase from above 0, one rate each",
        );
    }
    let legs = || book.iter().map(|b| &b.0).chain(hedges);
    if !legs().all(XaLeg::keys_match) {
        return fail(
            "E_INPUT",
            "an instrument has keys other than those of its kind",
        );
    }
    if book.is_empty() || hedges.is_empty() || weights.len() != 1 + p {
        return fail("E_INPUT", "need a book, hedges and 1 + P weights");
    }
    if legs().any(|l| l.kind != XaKind::Underlying && l.value("expiry_years") > c.times[p - 1]) {
        return fail(
            "E_INPUT",
            "an expiry is beyond the last pillar (ruling I-20)",
        );
    }
    if m.spot <= 0.0
        || m.volatility <= 0.0
        || weights.iter().any(|w| *w <= 0.0)
        || ridge < 0.0
        || legs().any(|l| l.fields.iter().any(|f| f.1 <= 0.0))
    {
        return fail(
            "E_DOMAIN",
            "spot, volatility, weights and instrument terms must be positive",
        );
    }
    let mut book_risk = vec![0.0; 1 + p];
    for (leg, q) in book {
        for (b, r) in book_risk.iter_mut().zip(risks(m, leg)) {
            *b += q * r;
        }
    }
    let columns: Vec<Vec<f64>> = hedges.iter().map(|h| risks(m, h)).collect();
    let a: Matrix = (0..=p)
        .map(|f| columns.iter().map(|col| col[f]).collect())
        .collect();
    let s = qp_solve(&QpProblem {
        a: &a,
        b: &book_risk,
        weights,
        ridge,
        eq_matrix: None,
        eq_rhs: None,
        lower: None,
        upper: None,
        singular: Singular::Error,
        costs: Costs::default(),
    })?;
    Ok(XaHedge {
        positions: s.x,
        book_risk,
        residual_risk: s.residual,
        objective: s.objective,
    })
}
