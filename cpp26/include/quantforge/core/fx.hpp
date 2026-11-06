#pragma once
// FX from 02-curves/fx.md. Instrument, market data and valuation stay apart, as in rates.hpp.
#include <array>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "quantforge/core/rates.hpp"

namespace quantforge {

struct FxPair {
    std::string id, base, quote;
    int spot_lag;
    std::array<Calendar, 2> calendars;
    double pip;
};

/// GBPUSD or EURUSD; nullptr otherwise.
const FxPair* fx_pair(std::string_view id);
Date fx_spot_date(const FxPair& pair, Date trade_date);

struct FxMarket {
    const FxPair* pair;
    double spot;
    Date as_of;
    const Curve* base;
    const Curve* quote;
};

enum class FxSide { Buy, Sell };

struct FxForwardTrade {
    double notional_base, strike;
    Date value_date;
    FxSide side;
};

struct FxSwapTrade {
    double notional_base;
    Date near_date;
    double near_rate;
    Date far_date;
    double far_rate;
    FxSide far_side;
};

struct FxOutright {
    double forward, points;
};
struct FxPrice {
    Valuation valuation;
    double fx_delta;
};
struct FxNode {
    Date value_date;
    double implied_ratio, basis_bp;
};
struct FxPoint {
    Tenor tenor;
    double points;
};

/// All check spot: E_DOMAIN.
void check_fx_market(const FxMarket& m);
FxOutright fx_outright(const FxMarket& m, Date value_date);
FxPrice fx_forward_price(const FxMarket& m, const FxForwardTrade& t);
FxPrice fx_swap_price(const FxMarket& m, const FxSwapTrade& t);
std::vector<FxNode> fx_implied(const FxMarket& m, const std::vector<FxPoint>& points);

}  // namespace quantforge
