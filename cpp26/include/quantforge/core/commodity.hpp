#pragma once
// Commodity curves and storage carry (02-curves/commodity.md).
#include <optional>
#include <vector>

#include "quantforge/core/rates.hpp"

namespace quantforge {

struct CommodityQuote {
    long long month;  // 12 year + month - 1
    double price;
};
std::vector<double> commodity_forwards(const std::vector<CommodityQuote>& quotes, const std::optional<std::vector<double>>& seasonality,
                                       const std::vector<long long>& months);

struct DatedPrice {
    Date date;
    double price;
};
struct StorageCarry {
    std::vector<double> convenience_yields, carry_values;
    std::vector<bool> arbitrage;
};
StorageCarry storage_carry(const Curve& funding, const std::vector<DatedPrice>& forwards, double storage_cost);

}  // namespace quantforge
