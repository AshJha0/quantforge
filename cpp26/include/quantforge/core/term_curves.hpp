#pragma once
// Stage J curves lane (rulings J-C-1 to J-C-9): the financing term structure over the funding curve
// (02-curves/financing-term-structure.md) and the liquidity cost curve (10-execution/liquidity-curve.md).
#include <optional>
#include <vector>

namespace quantforge::termcurves {

using Vec = std::vector<double>;

// Knots of cumulative funding Z(t) t, financing spread S(t) and borrow fee B(t).
struct FinancingCurve {
    Vec funding_times, funding_cum, quote_times, spread_cum, borrow_times, borrow_cum;
    double cover() const;
    double zt(double t) const;
    double s(double t) const;
    double b(double t) const;
    double financing_df(double t) const;  // exp(-Z(t) t - S(t))
};

// Bootstraps S(T_i) = ln(1 + R_i T_i) - Z(T_i) T_i (J-C-2) and B(T_j) = b_j T_j (J-C-4).
FinancingCurve build(const Vec& funding_times, const Vec& funding_zero_rates, const Vec& quote_times,
                     const Vec& repo_rates, const Vec& borrow_times, const Vec& borrow_fees);

struct TermCurve {
    Vec pillar_spreads, spread, financing_df, financing_rate, forward_financing;
    std::optional<Vec> borrow_fee;
};
TermCurve term_curve(const FinancingCurve& c, const Vec& query_times);  // repo.term.curve

struct TermForward {
    double forward, carry, carry_factor, financing_df, pv_dividends;
};
// eq.forward.term_financed (J-C-5).
TermForward forward_term_financed(const FinancingCurve& c, double spot, double maturity, const Vec& dividend_times,
                                  const Vec& dividend_amounts);

struct LiquidityParams {
    double half_spread_bps, daily_volume, daily_vol, coefficient, exponent, risk_multiplier;
};
struct LiquidityCurve {
    double spread_cost;
    std::vector<Vec> impact;
    Vec timing_risk;
    std::vector<Vec> total_cost;
    std::optional<Vec> optimal_horizon, min_cost;
};
// liq.curve.cost (J-C-6 to J-C-8).
LiquidityCurve liquidity_cost(const LiquidityParams& p, const Vec& sizes, const Vec& horizons);

}  // namespace quantforge::termcurves
