#pragma once
// Stage H wave 2 execution (rulings HR-59 to HR-67): the adaptive algorithms of 10-execution/adaptive-algos.md
// (arrival price, close, liquidity seeking, pairs, baskets) and the pre-trade estimate and cost attribution of
// 10-execution/tca-pretrade.md. Port of python/quantforge_core/adaptive_exec.py; error precedence HR-66
// (structural E_INPUT before any E_DOMAIN). Reuses the wave-1 TWAP and VWAP of execution.hpp.
//
// Sources, as the specs cite them: [AC00] Almgren and Chriss, J. Risk 3(2), preprint eq. (17) for the arrival
// holdings and eq. (10) for the timing-risk line; [Kis13] Kissell, I-star form (recalled, UNVERIFIED; parameters
// are inputs); [Per88] Perold for the total that the attribution splits.
#include <array>
#include <optional>
#include <vector>

#include "quantforge/core/execution.hpp"

namespace quantforge::execution {

enum class PairMode { CashBalanced, Hedged };

/// HR-3: floor every share, hand the missing units to the largest remainders (ties to the earliest); if rounding
/// left the floors above x, take units back from the smallest remainders (ties to the latest).
Vec largest_remainder(double x, const Vec& exact);

Vec algo_arrival(double quantity, long long n_buckets, double urgency, Mode mode);

struct Close {
    double auction_quantity;
    Vec slices;
};
Close algo_close(double quantity, double close_volume, double auction_participation, const Vec& profile, Mode mode);

using Level = std::array<double, 2>;  // [price, size]
using Book = std::vector<Level>;
struct Seek {
    Vec slices;
    std::vector<std::optional<double>> avg_prices;  // empty bucket: nullopt
    double filled, residual, notional;
    std::optional<double> avg_fill_price;  // nothing filled: nullopt
};
Seek algo_liquidity_seek(Side side, double quantity, double limit_price, double take_fraction,
                         const std::vector<Book>& books);

struct Pair {
    Vec slices_a, slices_b;
    double quantity_b;
    Vec cash_imbalance;
};
Pair algo_pair(Side side_a, double quantity_a, double price_a, Side side_b, double price_b, PairMode pair_mode,
               std::optional<double> hedge_ratio, long long n_buckets, Mode mode);

struct Leg {
    Side side;
    double quantity, price;
};
struct Basket {
    std::vector<Vec> slices;
    Vec cash_imbalance;
    double gross_notional;
};
Basket algo_basket(const std::vector<Leg>& legs, long long n_buckets, Mode mode);

struct PretradeParams {
    double a1, a2, a3, a4, b1;
};
struct Pretrade {
    double istar_bps, impact_bps, spread_bps, expected_cost_bps, duration_days, timing_risk_bps;
    std::optional<double> expected_cost, timing_risk;  // only with a price
};
Pretrade tca_pretrade(double quantity, double adv, double daily_vol, double participation, double half_spread_bps,
                      const PretradeParams& params, std::optional<double> price);

struct AttrFill {
    double quantity, price, mid;
};
struct Attribution {
    double delay, impact, spread, execution, opportunity, fees, total, total_bps;
};
Attribution tca_attribution(Side side, double decision_price, double arrival_mid, double end_price,
                            double order_quantity, const std::vector<AttrFill>& fills, double fees);

}  // namespace quantforge::execution
