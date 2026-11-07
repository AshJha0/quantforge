#pragma once
// Stage D, D7 to D9: caps, floors and swaptions (05-volatility/caps-and-swaptions.md), commodity curves and
// storage carry (02-curves/commodity.md), MBS pass-throughs (04-pricing/mbs.md).
#include <optional>
#include <vector>

#include "quantforge/core/rates.hpp"

namespace quantforge {

enum class RateVolModel { Black76, Bachelier };

struct CapPrice {
    std::vector<double> caplets;
    double price;
};
/// vols: one entry (flat) or one per caplet. phi +1 for a cap, -1 for a floor.
CapPrice cap_price(const Curve& discount, const Curve& projection, RateVolModel model, const std::vector<double>& vols,
                   bool flat, double phi, long long start_months, long long tenor_months, double strike, double notional);

struct SwaptionPrice {
    double price, forward_rate, annuity;
};
/// phi +1 for a payer.
SwaptionPrice swaption_price(const Curve& discount, const Curve& projection, RateVolModel model, double vol, double phi,
                             long long expiry_months, long long tenor_months, double strike, double notional);

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

struct MbsPool {
    double balance, wac, net_coupon;
    long long wam, age;
    bool psa;
    double rate_or_speed;
};
struct MbsCashflows {
    std::vector<double> balance, interest, scheduled_principal, prepayment;
    double wal;
};
MbsCashflows mbs_cashflows(const MbsPool& pool);

struct MbsPrice {
    double price, modified_duration, wal;
};
MbsPrice mbs_price(const MbsPool& pool, double yield, long long delay_days);

}  // namespace quantforge
