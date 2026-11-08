#pragma once
// Stage D, D7 to D9: caps, floors and swaptions (05-volatility/caps-and-swaptions.md), commodity curves and
// storage carry (02-curves/commodity.md), MBS pass-throughs (04-pricing/mbs.md).
#include <optional>
#include <vector>

#include "quantforge/core/rates.hpp"
#include "quantforge/core/sabr.hpp"

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

// ---- Stage E, E4: rates and inflation vol (05-volatility/rates-vol-cube.md, rulings E-B8 to E-B13) ----

struct SabrCube {
    std::vector<long long> expiries_months, tenors_months;
    std::vector<std::vector<double>> alpha, beta, rho, nu;  // rows by expiry, columns by tenor
};
struct CubeSwaption {
    double price, forward_rate, annuity, vol;
    SabrParameters sabr;
};
/// phi +1 payer, -1 receiver. Parameters bilinear in (ACT/365F time, tenor years); no extrapolation.
CubeSwaption swaption_price_cube(const Curve& discount, const Curve& projection, const SabrCube& cube, double phi,
                                 long long expiry_months, long long tenor_months, double strike, double notional);

struct CapStrip {
    std::vector<double> caplet_vols, cap_prices;
};
CapStrip cap_strip(const Curve& discount, const Curve& projection, RateVolModel model, long long start_months, double strike,
                   const std::vector<long long>& cap_tenors_months, const std::vector<double>& flat_vols, double notional);

struct BondFutOption {
    double price, contract_value;
};
/// phi +1 call, -1 put; prices per 100 face.
BondFutOption bondfut_option_price(double phi, double futures, double strike, double t, double discount, double vol,
                                   double contract_size);
struct BondFutVol {
    double price_vol, yield_vol;
};
BondFutVol bondfut_implied_vol(double phi, double futures, double strike, double t, double discount, double premium,
                               double ctd_yield, double ctd_modified_duration);

struct YoyPeriod {
    double accrual, discount_factor, yoy_forward, expiry_years, vol;
};
CapPrice yoy_cap_price(RateVolModel model, double phi, double strike, double notional, const std::vector<YoyPeriod>& periods);
struct ZcCap {
    double price, strike_ratio;
};
ZcCap zc_cap_price(RateVolModel model, double phi, double forward_index_ratio, double years, double strike, double discount,
                   double vol, double notional);

}  // namespace quantforge
