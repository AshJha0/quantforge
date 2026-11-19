//! Stage H wave 2 execution (rulings HR-59 to HR-67): the adaptive algorithms of
//! `10-execution/adaptive-algos.md` (arrival price, close, liquidity seeking, pairs, baskets) and
//! the pre-trade estimate and cost attribution of `10-execution/tca-pretrade.md`.
//!
//! Sources, as the specs cite them: [AC00] Almgren and Chriss, J. Risk 3(2), preprint eq. (17)
//! for the arrival holdings and eq. (10) for the timing-risk line; [Kis13] Kissell (I-star form,
//! recalled, UNVERIFIED; parameters are inputs); [Per88] Perold for the total that the
//! attribution splits. Error precedence is HR-66: structural `E_INPUT` before any `E_DOMAIN`.
//! Reuses the wave-1 schedules (TWAP, VWAP, HR-3 largest remainder) of `execution`.
use crate::error::{Result, fail};
use crate::execution::{Amount, largest_remainder, quantity, schedule_twap, schedule_vwap};

fn buckets(n: i64) -> Result<usize> {
    if n < 1 {
        return fail("E_INPUT", "n_buckets must be at least 1");
    }
    Ok(usize::try_from(n).unwrap_or(0))
}

fn sign(buy: bool) -> f64 {
    if buy { 1.0 } else { -1.0 }
}

/// HR-59, HR-62: `floor(x + 1/2)`. HR-121: `x + 1/2` within 1e-12 relative of an integer is that
/// integer, so an exact half that binary64 lands just below still rounds up.
#[allow(clippy::cast_possible_truncation)]
fn half_up(x: f64) -> i64 {
    let t = x + 0.5;
    let near = t.round();
    if (t - near).abs() <= 1e-12 * near.abs() {
        near as i64
    } else {
        t.floor() as i64
    }
}

#[allow(clippy::cast_possible_truncation)]
fn whole(x: f64) -> i64 {
    x as i64
}

/// `cosh(a) / sinh(b)` for `0 <= a <= b`, `b > 0`, without overflow.
fn cosh_over_sinh(a: f64, b: f64) -> f64 {
    if b <= 700.0 {
        a.cosh() / b.sinh()
    } else {
        (a - b).exp() * (1.0 + (-2.0 * a).exp()) / -(-2.0 * b).exp_m1()
    }
}

fn cumulative(xs: &[f64]) -> Vec<f64> {
    xs.iter()
        .scan(0.0, |c, x| {
            *c += x;
            Some(*c)
        })
        .collect()
}

fn values(v: &[Amount]) -> Vec<f64> {
    v.iter().map(|a| a.value()).collect()
}

// ------------------------------------------------------------------ adaptive-algos.md

/// `exec.algo.arrival`: holdings `x_j = X sinh(kappa (N - j)) / sinh(kappa N)` ([AC00] eq. (17),
/// one bucket per time unit); kappa = 0 is TWAP. `UNITS` by largest remainder (HR-3, HR-67).
pub fn arrival(x: f64, n_buckets: i64, urgency: f64, units: bool) -> Result<Vec<Amount>> {
    let n = buckets(n_buckets)?;
    quantity(x, units)?;
    if urgency < 0.0 {
        return fail("E_DOMAIN", "urgency must be non-negative");
    }
    if urgency == 0.0 {
        return schedule_twap(x, n_buckets, units); // the TWAP limit in both modes (HR-67)
    }
    // n_j = x_{j-1} - x_j = X 2 sinh(k/2) cosh(k (N - j + 1/2)) / sinh(k N): strictly decreasing
    // in j and free of cancellation.
    let k = urgency;
    let h = 2.0 * (0.5 * k).sinh();
    #[allow(clippy::cast_precision_loss)]
    let nf = n as f64;
    #[allow(clippy::cast_precision_loss)]
    let exact: Vec<f64> = (1..=n)
        .map(|j| x * h * cosh_over_sinh(k * (nf - j as f64 + 0.5), k * nf))
        .collect();
    Ok(if units {
        largest_remainder(x, &exact)
            .into_iter()
            .map(Amount::Units)
            .collect()
    } else {
        exact.into_iter().map(Amount::Real).collect()
    })
}

/// `exec.algo.close`: auction `min(X, p_c V_c)` (`UNITS` floors `p_c V_c`) and the remainder over
/// the profile as `exec.schedule.vwap` (HR-60).
pub fn close(
    x: f64,
    close_volume: f64,
    participation: f64,
    profile: &[f64],
    units: bool,
) -> Result<(Amount, Vec<Amount>)> {
    quantity(x, units)?;
    if profile.is_empty() {
        return fail("E_INPUT", "profile must not be empty");
    }
    if !(0.0..=1.0).contains(&participation) {
        return fail("E_DOMAIN", "auction_participation must lie in [0, 1]");
    }
    if close_volume < 0.0 {
        return fail("E_DOMAIN", "close_volume must be non-negative");
    }
    if profile.iter().any(|&w| w < 0.0) {
        return fail("E_DOMAIN", "profile weights must be non-negative");
    }
    let mut cap = participation * close_volume;
    if units {
        // within 1e-12 relative of an integer: snap before flooring
        let near = cap.round();
        cap = if (cap - near).abs() <= 1e-12 * near.abs() {
            near
        } else {
            cap.floor()
        };
    }
    let auction = x.min(cap);
    let rest = x - auction;
    let amount = |v: f64| {
        if units {
            Amount::Units(whole(v))
        } else {
            Amount::Real(v)
        }
    };
    if rest <= 0.0 {
        return Ok((amount(auction), vec![amount(0.0); profile.len()]));
    }
    if profile.iter().sum::<f64>() == 0.0 {
        return fail("E_DOMAIN", "profile is all zero with a remainder to place");
    }
    Ok((amount(auction), schedule_vwap(rest, profile, units)?))
}

/// The `exec.algo.liquidity_seek` result.
#[derive(Debug, Clone, PartialEq)]
pub struct Seek {
    pub slices: Vec<f64>,
    pub avg_prices: Vec<Option<f64>>,
    pub filled: f64,
    pub residual: f64,
    pub notional: f64,
    pub avg_fill_price: Option<f64>,
}

fn inside(buy: bool, price: f64, limit: f64) -> bool {
    if buy { price <= limit } else { price >= limit }
}

/// `exec.algo.liquidity_seek`: child `c_i = min(R_{i-1}, alpha A_i)`, `A_i` the depth inside the
/// limit; the child walks the levels best first, inside the limit only (HR-61). `books[i]` holds
/// `[price, size]` levels best first.
pub fn liquidity_seek(
    buy: bool,
    x: f64,
    limit: f64,
    alpha: f64,
    books: &[Vec<[f64; 2]>],
) -> Result<Seek> {
    if books.is_empty() {
        return fail("E_INPUT", "books must not be empty");
    }
    if x <= 0.0 {
        return fail("E_INPUT", "quantity must be positive");
    }
    for book in books {
        for (k, lvl) in book.iter().enumerate() {
            if lvl[1] <= 0.0 {
                return fail("E_INPUT", "level sizes must be positive");
            }
            if k > 0 {
                let prev = book[k - 1][0];
                if !(if buy { lvl[0] > prev } else { lvl[0] < prev }) {
                    return fail(
                        "E_INPUT",
                        "levels must be strictly ordered best first (asks ascending, bids descending)",
                    );
                }
            }
        }
    }
    if !(alpha > 0.0 && alpha <= 1.0) {
        return fail("E_DOMAIN", "take_fraction must lie in (0, 1]");
    }
    if limit <= 0.0 {
        return fail("E_DOMAIN", "limit_price must be positive");
    }
    if books.iter().flatten().any(|l| l[0] <= 0.0) {
        return fail("E_DOMAIN", "level prices must be positive");
    }
    let (mut remaining, mut filled, mut notional) = (x, 0.0, 0.0);
    let mut slices = Vec::with_capacity(books.len());
    let mut avg_prices = Vec::with_capacity(books.len());
    for book in books {
        let levels: Vec<&[f64; 2]> = book.iter().filter(|l| inside(buy, l[0], limit)).collect();
        let depth: f64 = levels.iter().map(|l| l[1]).sum();
        let child = remaining.min(alpha * depth);
        let (mut left, mut paid) = (child, 0.0);
        for l in &levels {
            if left <= 0.0 {
                break;
            }
            let take = left.min(l[1]);
            paid += take * l[0];
            left -= take;
        }
        slices.push(child);
        avg_prices.push((child > 0.0).then(|| paid / child));
        remaining -= child;
        filled += child;
        notional += paid;
    }
    Ok(Seek {
        slices,
        avg_prices,
        filled,
        residual: remaining,
        notional,
        avg_fill_price: (filled > 0.0).then(|| notional / filled),
    })
}

/// One leg of a pair or basket: side (true for `BUY`), quantity, price.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Leg {
    pub buy: bool,
    pub quantity: f64,
    pub price: f64,
}

/// The `exec.algo.pair` result.
#[derive(Debug, Clone, PartialEq)]
pub struct Pair {
    pub slices_a: Vec<Amount>,
    pub slices_b: Vec<Amount>,
    pub quantity_b: Amount,
    pub cash_imbalance: Vec<f64>,
}

/// `exec.algo.pair`: leg A is TWAP; leg B follows leg A's cumulative times the ratio r (`P_A /
/// P_B` when `hedged` is false, else `hedge_ratio`), rounded half up in `UNITS` (HR-62). Leg B's
/// quantity in `leg_b` is ignored.
pub fn pair(
    leg_a: Leg,
    leg_b: Leg,
    hedged: bool,
    hedge_ratio: Option<f64>,
    n_buckets: i64,
    units: bool,
) -> Result<Pair> {
    buckets(n_buckets)?;
    quantity(leg_a.quantity, units)?;
    if !hedged && leg_a.buy == leg_b.buy {
        return fail("E_INPUT", "a cash-balanced pair needs opposite sides");
    }
    if hedged && hedge_ratio.is_none() {
        return fail("E_INPUT", "HEDGED needs hedge_ratio");
    }
    let (pa, pb) = (leg_a.price, leg_b.price);
    if pa <= 0.0 || pb <= 0.0 {
        return fail("E_DOMAIN", "prices must be positive");
    }
    let h = hedge_ratio.unwrap_or(0.0);
    if hedged && h <= 0.0 {
        return fail("E_DOMAIN", "hedge_ratio must be positive");
    }
    let slices_a = schedule_twap(leg_a.quantity, n_buckets, units)?;
    let cum_a = cumulative(&values(&slices_a));
    let target: Vec<f64> = if hedged {
        cum_a.iter().map(|c| h * c).collect()
    } else {
        // P_A C first: C_B P_B stays within ulps of C_A P_A
        cum_a.iter().map(|c| c * pa / pb).collect()
    };
    let (cum_b, slices_b, quantity_b) = if units {
        let ints: Vec<i64> = target.iter().map(|&t| half_up(t)).collect();
        let mut prev = 0;
        let mut s = Vec::with_capacity(ints.len());
        for &c in &ints {
            s.push(Amount::Units(c - prev));
            prev = c;
        }
        #[allow(clippy::cast_precision_loss)]
        let cum: Vec<f64> = ints.iter().map(|&c| c as f64).collect();
        (cum, s, Amount::Units(prev))
    } else {
        let mut prev = 0.0;
        let mut s = Vec::with_capacity(target.len());
        for &c in &target {
            s.push(Amount::Real(c - prev));
            prev = c;
        }
        let last = *target.last().unwrap_or(&0.0);
        (target, s, Amount::Real(last))
    };
    let (sa, sb) = (sign(leg_a.buy), sign(leg_b.buy));
    let cash_imbalance = cum_a
        .iter()
        .zip(&cum_b)
        .map(|(ca, cb)| sa * ca * pa + sb * cb * pb)
        .collect();
    Ok(Pair {
        slices_a,
        slices_b,
        quantity_b,
        cash_imbalance,
    })
}

/// The `exec.algo.basket` result.
#[derive(Debug, Clone, PartialEq)]
pub struct Basket {
    pub slices: Vec<Vec<Amount>>,
    pub cash_imbalance: Vec<f64>,
    pub gross_notional: f64,
}

/// `exec.algo.basket`: every leg TWAP-sliced (HR-3); per-bucket cash imbalance and gross notional,
/// no re-balancing (HR-63).
pub fn basket(legs: &[Leg], n_buckets: i64, units: bool) -> Result<Basket> {
    if legs.is_empty() {
        return fail("E_INPUT", "legs must not be empty");
    }
    let n = buckets(n_buckets)?;
    for l in legs {
        quantity(l.quantity, units)?;
    }
    if legs.iter().any(|l| l.price <= 0.0) {
        return fail("E_DOMAIN", "prices must be positive");
    }
    let slices = legs
        .iter()
        .map(|l| schedule_twap(l.quantity, n_buckets, units))
        .collect::<Result<Vec<_>>>()?;
    let cums: Vec<Vec<f64>> = slices.iter().map(|s| cumulative(&values(s))).collect();
    let cash_imbalance = (0..n)
        .map(|j| {
            legs.iter()
                .zip(&cums)
                .map(|(l, c)| sign(l.buy) * c[j] * l.price)
                .sum()
        })
        .collect();
    Ok(Basket {
        slices,
        cash_imbalance,
        gross_notional: legs.iter().map(|l| l.quantity * l.price).sum(),
    })
}

// ------------------------------------------------------------------ tca-pretrade.md

/// The [Kis13] I-star parameters, inputs only (HR-64).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct IstarParams {
    pub a1: f64,
    pub a2: f64,
    pub a3: f64,
    pub a4: f64,
    pub b1: f64,
}

/// The `exec.tca.pretrade` result; `expected_cost` and `timing_risk` only with a price.
#[derive(Debug, Clone, PartialEq)]
pub struct Pretrade {
    pub istar_bps: f64,
    pub impact_bps: f64,
    pub spread_bps: f64,
    pub expected_cost_bps: f64,
    pub duration_days: f64,
    pub timing_risk_bps: f64,
    pub expected_cost: Option<f64>,
    pub timing_risk: Option<f64>,
}

/// `exec.tca.pretrade`: `I* = a1 (X/adv)^a2 sigma^a3`; impact `b1 I* p^a4 + (1 - b1) I*`;
/// expected cost = half spread + impact; timing risk `1e4 sigma sqrt(T/3)`, `T = X / (p adv)`,
/// reported beside the cost and never added (HR-64).
pub fn pretrade(
    x: f64,
    adv: f64,
    sigma: f64,
    p: f64,
    half_spread_bps: f64,
    k: IstarParams,
    price: Option<f64>,
) -> Result<Pretrade> {
    if x <= 0.0 {
        return fail("E_INPUT", "quantity must be positive");
    }
    let checks = [
        (adv <= 0.0, "adv must be positive"),
        (sigma < 0.0, "daily_vol must be non-negative"),
        (!(p > 0.0 && p < 1.0), "participation must lie in (0, 1)"),
        (
            half_spread_bps < 0.0,
            "half_spread_bps must be non-negative",
        ),
        (k.a1 <= 0.0, "a1 must be positive"),
        (!(0.0..=1.0).contains(&k.b1), "b1 must lie in [0, 1]"),
        (price.is_some_and(|v| v <= 0.0), "price must be positive"),
        (sigma == 0.0 && k.a3 <= 0.0, "0 to a non-positive power"),
    ];
    if let Some((_, m)) = checks.iter().find(|c| c.0) {
        return fail("E_DOMAIN", *m);
    }
    let istar = k.a1 * (x / adv).powf(k.a2) * sigma.powf(k.a3);
    let impact = k.b1 * istar * p.powf(k.a4) + (1.0 - k.b1) * istar;
    let cost = half_spread_bps + impact;
    let duration = x / (p * adv);
    let timing = 1e4 * sigma * (duration / 3.0).sqrt();
    Ok(Pretrade {
        istar_bps: istar,
        impact_bps: impact,
        spread_bps: half_spread_bps,
        expected_cost_bps: cost,
        duration_days: duration,
        timing_risk_bps: timing,
        expected_cost: price.map(|v| cost * x * v / 1e4),
        timing_risk: price.map(|v| timing * x * v / 1e4),
    })
}

/// One attribution fill: quantity, price, and the mid at the fill time.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Fill {
    pub quantity: f64,
    pub price: f64,
    pub mid: f64,
}

/// The `exec.tca.attribution` result (HR-65).
#[derive(Debug, Clone, PartialEq)]
pub struct Attribution {
    pub delay: f64,
    pub impact: f64,
    pub spread: f64,
    pub execution: f64,
    pub opportunity: f64,
    pub fees: f64,
    pub total: f64,
    pub total_bps: f64,
}

/// `exec.tca.attribution`: delay `s Q (m_0 - P_d)`, impact `s sum q (m - m_0)`, spread
/// `s sum q (p - m)` on executed quantity; opportunity and fees as HR-8 (HR-65).
#[allow(clippy::too_many_arguments)]
pub fn attribution(
    buy: bool,
    decision_price: f64,
    arrival_mid: f64,
    end_price: f64,
    order_quantity: f64,
    fills: &[Fill],
    fees: f64,
) -> Result<Attribution> {
    let s = sign(buy);
    if order_quantity <= 0.0 {
        return fail("E_INPUT", "order_quantity must be positive");
    }
    if fills.iter().any(|f| f.quantity <= 0.0) {
        return fail("E_INPUT", "fill quantities must be positive");
    }
    let filled: f64 = fills.iter().map(|f| f.quantity).sum();
    if filled > order_quantity {
        return fail("E_INPUT", "fills add up to more than the order");
    }
    let prices = [decision_price, arrival_mid, end_price];
    if prices.iter().any(|&p| p <= 0.0) || fills.iter().any(|f| f.price <= 0.0 || f.mid <= 0.0) {
        return fail("E_DOMAIN", "prices and mids must be positive");
    }
    // + 0.0 turns the -0 of a SELL into +0
    let delay = s * filled * (arrival_mid - decision_price) + 0.0;
    let impact = s * fills
        .iter()
        .map(|f| f.quantity * (f.mid - arrival_mid))
        .sum::<f64>()
        + 0.0;
    let spread = s * fills
        .iter()
        .map(|f| f.quantity * (f.price - f.mid))
        .sum::<f64>()
        + 0.0;
    let opportunity = s * (order_quantity - filled) * (end_price - decision_price) + 0.0;
    let total = delay + impact + spread + opportunity + fees;
    Ok(Attribution {
        delay,
        impact,
        spread,
        execution: impact + spread,
        opportunity,
        fees,
        total,
        total_bps: total / (order_quantity * decision_price) * 1e4,
    })
}

#[cfg(test)]
#[path = "adaptive_exec_tests.rs"]
mod tests;
