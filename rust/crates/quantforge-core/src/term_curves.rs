//! Stage J curves lane (rulings J-C-1 to J-C-9): the financing term structure over the funding
//! curve (`02-curves/financing-term-structure.md`) and the liquidity cost curve
//! (`10-execution/liquidity-curve.md`).
use crate::error::{Result, fail};

fn increasing_positive(ts: &[f64]) -> bool {
    ts.iter().all(|&t| t > 0.0) && ts.windows(2).all(|w| w[1] > w[0])
}

/// Linear in `y` on the knots `(0, 0), (ts[k], ys[k])` for `t` in `(0, ts[-1]]` (J-C-3).
fn lin(ts: &[f64], ys: &[f64], t: f64) -> f64 {
    let (mut x0, mut y0) = (0.0, 0.0);
    for (&x1, &y1) in ts.iter().zip(ys) {
        if t <= x1 {
            return y0 + (t - x0) / (x1 - x0) * (y1 - y0);
        }
        (x0, y0) = (x1, y1);
    }
    f64::NAN
}

/// Knots of cumulative funding `Z(t) t`, financing spread `S(t)` and borrow fee `B(t)`.
#[derive(Debug, Clone)]
pub struct FinancingCurve {
    funding_times: Vec<f64>,
    funding_cum: Vec<f64>,
    quote_times: Vec<f64>,
    spread_cum: Vec<f64>,
    borrow_times: Vec<f64>,
    borrow_cum: Vec<f64>,
}

impl FinancingCurve {
    /// Bootstraps `S(T_i) = ln(1 + R_i T_i) - Z(T_i) T_i` (J-C-2) and `B(T_i) = b_i T_i` (J-C-4).
    pub fn build(
        funding_times: &[f64],
        funding_zero_rates: &[f64],
        quote_times: &[f64],
        repo_rates: &[f64],
        borrow_times: &[f64],
        borrow_fees: &[f64],
    ) -> Result<Self> {
        if funding_times.len() != funding_zero_rates.len()
            || quote_times.len() != repo_rates.len()
            || borrow_times.len() != borrow_fees.len()
            || funding_times.is_empty()
            || quote_times.is_empty()
        {
            return fail(
                "E_INPUT",
                "curve arrays must pair up; funding and quotes non-empty",
            );
        }
        if ![funding_times, quote_times, borrow_times]
            .iter()
            .all(|ts| increasing_positive(ts))
        {
            return fail("E_INPUT", "times must be positive and strictly increasing");
        }
        if repo_rates
            .iter()
            .zip(quote_times)
            .any(|(r, t)| 1.0 + r * t <= 0.0)
        {
            return fail("E_DOMAIN", "1 + R T must be positive");
        }
        if borrow_fees.iter().any(|&b| b < 0.0) {
            return fail("E_DOMAIN", "borrow fees must be non-negative");
        }
        let borrow_cum: Vec<f64> = borrow_fees
            .iter()
            .zip(borrow_times)
            .map(|(b, t)| b * t)
            .collect();
        if borrow_cum.windows(2).any(|w| w[1] < w[0]) {
            return fail("E_DOMAIN", "cumulative borrow fee must not fall");
        }
        if quote_times[quote_times.len() - 1] > funding_times[funding_times.len() - 1] {
            return fail("E_DOMAIN", "a quote lies beyond the funding curve");
        }
        let funding_cum: Vec<f64> = funding_zero_rates
            .iter()
            .zip(funding_times)
            .map(|(z, t)| z * t)
            .collect();
        let spread_cum = repo_rates
            .iter()
            .zip(quote_times)
            .map(|(r, &t)| (r * t).ln_1p() - lin(funding_times, &funding_cum, t))
            .collect();
        Ok(Self {
            funding_times: funding_times.to_vec(),
            funding_cum,
            quote_times: quote_times.to_vec(),
            spread_cum,
            borrow_times: borrow_times.to_vec(),
            borrow_cum,
        })
    }

    /// Last time every input curve covers.
    pub fn cover(&self) -> f64 {
        let c = self.funding_times[self.funding_times.len() - 1]
            .min(self.quote_times[self.quote_times.len() - 1]);
        self.borrow_times.last().map_or(c, |&b| c.min(b))
    }

    fn zt(&self, t: f64) -> f64 {
        lin(&self.funding_times, &self.funding_cum, t)
    }

    fn s(&self, t: f64) -> f64 {
        lin(&self.quote_times, &self.spread_cum, t)
    }

    fn b(&self, t: f64) -> f64 {
        if self.borrow_times.is_empty() {
            0.0
        } else {
            lin(&self.borrow_times, &self.borrow_cum, t)
        }
    }

    /// `P_f(t) = exp(-Z(t) t - S(t))`.
    pub fn financing_df(&self, t: f64) -> f64 {
        (-self.zt(t) - self.s(t)).exp()
    }

    /// True when borrow quotes were given.
    pub fn has_borrow(&self) -> bool {
        !self.borrow_times.is_empty()
    }
}

/// `repo.term.curve` outputs.
#[derive(Debug, Clone)]
pub struct TermCurve {
    pub pillar_spreads: Vec<f64>,
    pub spread: Vec<f64>,
    pub financing_df: Vec<f64>,
    pub financing_rate: Vec<f64>,
    pub forward_financing: Vec<f64>,
    pub borrow_fee: Option<Vec<f64>>,
}

/// `repo.term.curve` (J-C-2, J-C-3).
pub fn term_curve(c: &FinancingCurve, q: &[f64]) -> Result<TermCurve> {
    if q.is_empty() || !increasing_positive(q) {
        return fail(
            "E_INPUT",
            "query_times must be non-empty, positive, increasing",
        );
    }
    if q[q.len() - 1] > c.cover() {
        return fail("E_DOMAIN", "query beyond the coverage of the curve");
    }
    let pf: Vec<f64> = q.iter().map(|&t| c.financing_df(t)).collect();
    let (mut pt, mut pp, mut fwd) = (0.0, 1.0, Vec::with_capacity(q.len()));
    for (&t, &p) in q.iter().zip(&pf) {
        fwd.push((pp / p - 1.0) / (t - pt));
        (pt, pp) = (t, p);
    }
    Ok(TermCurve {
        pillar_spreads: c
            .spread_cum
            .iter()
            .zip(&c.quote_times)
            .map(|(s, t)| s / t)
            .collect(),
        spread: q.iter().map(|&t| c.s(t) / t).collect(),
        financing_rate: pf.iter().zip(q).map(|(p, t)| (1.0 / p - 1.0) / t).collect(),
        financing_df: pf,
        forward_financing: fwd,
        borrow_fee: c
            .has_borrow()
            .then(|| q.iter().map(|&t| c.b(t) / t).collect()),
    })
}

/// `eq.forward.term_financed` outputs.
#[derive(Debug, Clone, Copy)]
pub struct TermForward {
    pub forward: f64,
    pub carry: f64,
    pub carry_factor: f64,
    pub financing_df: f64,
    pub pv_dividends: f64,
}

/// `eq.forward.term_financed`: `F = (S - sum A_i C(t_i)) / C(T)`,
/// `C(t) = exp(-Z(t) t - S(t) + B(t))` (J-C-5).
pub fn forward_term_financed(
    c: &FinancingCurve,
    spot: f64,
    maturity: f64,
    dividend_times: &[f64],
    dividend_amounts: &[f64],
) -> Result<TermForward> {
    if dividend_times.len() != dividend_amounts.len() {
        return fail("E_INPUT", "dividend arrays must pair up");
    }
    if dividend_times.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_INPUT", "dividend_times must be strictly increasing");
    }
    if spot <= 0.0 {
        return fail("E_DOMAIN", "spot must be positive");
    }
    if !(maturity > 0.0 && maturity <= c.cover()) {
        return fail("E_DOMAIN", "maturity must lie in (0, coverage]");
    }
    if dividend_amounts.iter().any(|&a| a < 0.0) {
        return fail("E_DOMAIN", "dividends must be non-negative");
    }
    let carry = |t: f64| (-c.zt(t) - c.s(t) + c.b(t)).exp();
    let mut pv = 0.0;
    for (&t, &a) in dividend_times.iter().zip(dividend_amounts) {
        if t > 0.0 && t <= maturity {
            pv += a * carry(t);
        }
    }
    let cf = carry(maturity);
    let forward = (spot - pv) / cf;
    if forward <= 0.0 {
        return fail("E_DOMAIN", "forward is not positive");
    }
    Ok(TermForward {
        forward,
        carry: forward - spot,
        carry_factor: cf,
        financing_df: c.financing_df(maturity),
        pv_dividends: pv,
    })
}

/// Liquidity curve parameters (J-C-6).
#[derive(Debug, Clone, Copy)]
pub struct LiquidityParams {
    pub half_spread_bps: f64,
    pub daily_volume: f64,
    pub daily_vol: f64,
    pub coefficient: f64,
    pub exponent: f64,
    pub risk_multiplier: f64,
}

/// `liq.curve.cost` outputs.
#[derive(Debug, Clone)]
pub struct LiquidityCurve {
    pub spread_cost: f64,
    pub impact: Vec<Vec<f64>>,
    pub timing_risk: Vec<f64>,
    pub total_cost: Vec<Vec<f64>>,
    pub optimal_horizon: Option<Vec<f64>>,
    pub min_cost: Option<Vec<f64>>,
}

/// `liq.curve.cost` (J-C-6 to J-C-8):
/// `c(Q, h) = s + Y sigma (Q / (V h))^delta + z sigma sqrt(h / 3)`.
pub fn liquidity_cost(
    p: &LiquidityParams,
    sizes: &[f64],
    horizons: &[f64],
) -> Result<LiquidityCurve> {
    if sizes.is_empty() || horizons.is_empty() {
        return fail("E_INPUT", "sizes and horizons_days must be non-empty");
    }
    if p.half_spread_bps < 0.0
        || p.daily_volume <= 0.0
        || p.daily_vol < 0.0
        || p.coefficient < 0.0
        || p.risk_multiplier < 0.0
        || !(p.exponent > 0.0 && p.exponent <= 1.0)
        || sizes.iter().any(|&q| q < 0.0)
        || horizons.iter().any(|&h| h <= 0.0)
    {
        return fail("E_DOMAIN", "liquidity curve input out of domain");
    }
    let sp = p.half_spread_bps / 10000.0;
    let impact: Vec<Vec<f64>> = sizes
        .iter()
        .map(|&q| {
            horizons
                .iter()
                .map(|&h| p.coefficient * p.daily_vol * (q / (p.daily_volume * h)).powf(p.exponent))
                .collect()
        })
        .collect();
    let risk: Vec<f64> = horizons
        .iter()
        .map(|&h| p.risk_multiplier * p.daily_vol * (h / 3.0).sqrt())
        .collect();
    let total = impact
        .iter()
        .map(|r| r.iter().zip(&risk).map(|(i, k)| sp + i + k).collect())
        .collect();
    let b = p.risk_multiplier * p.daily_vol / 3.0_f64.sqrt();
    let (mut hs, mut cs) = (None, None);
    if b > 0.0 && p.coefficient > 0.0 {
        let (mut h_out, mut c_out) = (Vec::new(), Vec::new());
        for &q in sizes {
            let a = p.coefficient * p.daily_vol * (q / p.daily_volume).powf(p.exponent);
            if a == 0.0 {
                h_out.push(0.0);
                c_out.push(sp);
                continue;
            }
            let h = (2.0 * p.exponent * a / b).powf(1.0 / (p.exponent + 0.5));
            h_out.push(h);
            c_out.push(sp + a * h.powf(-p.exponent) + b * h.sqrt());
        }
        (hs, cs) = (Some(h_out), Some(c_out));
    }
    Ok(LiquidityCurve {
        spread_cost: sp,
        impact,
        timing_risk: risk,
        total_cost: total,
        optimal_horizon: hs,
        min_cost: cs,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const FT: [f64; 4] = [0.25, 0.5, 1.0, 2.0];
    const FZ: [f64; 4] = [0.040, 0.041, 0.0415, 0.042];

    #[test]
    fn quotes_round_trip_and_forwards_chain() {
        let qt = [1.0 / 12.0, 0.25, 0.5, 1.0];
        let qr = [0.0425, 0.0430, 0.0435, 0.0440];
        let c = FinancingCurve::build(&FT, &FZ, &qt, &qr, &[], &[]).unwrap();
        let out = term_curve(&c, &qt).unwrap();
        for (r, g) in qr.iter().zip(&out.financing_rate) {
            assert!((r - g).abs() < 1e-13);
        }
        let (mut growth, mut prev) = (1.0, 0.0);
        for k in 0..qt.len() {
            growth *= 1.0 + out.forward_financing[k] * (qt[k] - prev);
            prev = qt[k];
            assert!((growth * out.financing_df[k] - 1.0).abs() < 1e-14);
        }
        assert!(out.borrow_fee.is_none());
    }

    #[test]
    fn flat_inputs_reduce_to_d22() {
        let (r, s, b, t) = (0.03_f64, 0.004_f64, 0.002_f64, 0.75_f64);
        let repo: Vec<f64> = [0.25_f64, 1.0]
            .iter()
            .map(|&x| (((r + s) * x).exp() - 1.0) / x)
            .collect();
        let c = FinancingCurve::build(&[1.0], &[r], &[0.25, 1.0], &repo, &[1.0], &[b]).unwrap();
        let f = forward_term_financed(&c, 100.0, t, &[], &[]).unwrap();
        assert!((f.forward / (100.0 * ((r + s - b) * t).exp()) - 1.0).abs() < 1e-14);
        assert!((term_curve(&c, &[0.5]).unwrap().spread[0] - s).abs() < 1e-15);
    }

    #[test]
    fn borrow_and_dividends_lower_the_forward() {
        let c0 = FinancingCurve::build(&FT, &FZ, &[1.0], &[0.044], &[], &[]).unwrap();
        let c1 = FinancingCurve::build(&FT, &FZ, &[1.0], &[0.044], &[1.0], &[0.01]).unwrap();
        let base = forward_term_financed(&c0, 50.0, 0.75, &[], &[])
            .unwrap()
            .forward;
        assert!(
            forward_term_financed(&c1, 50.0, 0.75, &[], &[])
                .unwrap()
                .forward
                < base
        );
        assert!(
            forward_term_financed(&c0, 50.0, 0.75, &[0.5], &[1.0])
                .unwrap()
                .forward
                < base
        );
    }

    #[test]
    fn errors() {
        let e = |r: Result<FinancingCurve>| r.unwrap_err().code;
        assert_eq!(
            e(FinancingCurve::build(
                &FT,
                &FZ,
                &[0.5, 0.5],
                &[0.04, 0.04],
                &[],
                &[]
            )),
            "E_INPUT"
        );
        assert_eq!(
            e(FinancingCurve::build(
                &FT,
                &FZ,
                &[0.5],
                &[0.04],
                &[0.5, 1.0],
                &[0.02, 0.001]
            )),
            "E_DOMAIN"
        );
        assert_eq!(
            e(FinancingCurve::build(&FT, &FZ, &[3.0], &[0.04], &[], &[])),
            "E_DOMAIN"
        );
        assert_eq!(
            e(FinancingCurve::build(&FT, &FZ, &[1.0], &[-2.0], &[], &[])),
            "E_DOMAIN"
        );
        let c = FinancingCurve::build(&FT, &FZ, &[1.0], &[0.04], &[], &[]).unwrap();
        assert_eq!(term_curve(&c, &[1.5]).unwrap_err().code, "E_DOMAIN");
        assert_eq!(term_curve(&c, &[]).unwrap_err().code, "E_INPUT");
        assert_eq!(
            forward_term_financed(&c, 0.0, 0.5, &[], &[])
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        assert_eq!(
            forward_term_financed(&c, 10.0, 0.5, &[0.1], &[20.0])
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
    }

    fn params(z: f64, d: f64) -> LiquidityParams {
        LiquidityParams {
            half_spread_bps: 2.0,
            daily_volume: 1e7,
            daily_vol: 0.02,
            coefficient: 1.0,
            exponent: d,
            risk_multiplier: z,
        }
    }

    #[test]
    fn liquidity_matches_stage_h_and_optimum_is_a_minimum() {
        let out = liquidity_cost(&params(0.0, 0.5), &[1e5], &[1.0]).unwrap();
        assert!((out.impact[0][0] - 0.002).abs() < 1e-17);
        assert!(out.optimal_horizon.is_none());
        for (z, d, q) in [
            (1.0, 0.5, 1e5),
            (2.5, 0.6, 3e6),
            (0.3, 1.0, 4e4),
            (1.645, 0.2, 7e5),
        ] {
            let o = liquidity_cost(&params(z, d), &[q], &[1.0]).unwrap();
            let (h, m) = (o.optimal_horizon.unwrap()[0], o.min_cost.unwrap()[0]);
            for k in [0.9, 1.1] {
                let other = liquidity_cost(&params(z, d), &[q], &[h * k])
                    .unwrap()
                    .total_cost[0][0];
                assert!(other >= m - 1e-15);
            }
        }
        let zero = liquidity_cost(&params(1.0, 0.5), &[0.0], &[1.0]).unwrap();
        assert_eq!(zero.optimal_horizon.unwrap()[0], 0.0);
        assert_eq!(
            liquidity_cost(&params(0.0, 0.0), &[1.0], &[1.0])
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        assert_eq!(
            liquidity_cost(&params(0.0, 0.5), &[], &[1.0])
                .unwrap_err()
                .code,
            "E_INPUT"
        );
    }
}
