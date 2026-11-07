#pragma once
// Stage D, D4: the ISDA standard CDS model (04-pricing/credit.md). Business days are weekdays.
#include <vector>

#include "quantforge/core/rates.hpp"

namespace quantforge {

struct HazardCurve {
    Date as_of;
    std::vector<Date> dates;
    std::vector<double> survival;
    /// E_INPUT on dates, E_DOMAIN on survival <= 0.
    void check() const;
    /// -ln Q linear in time between nodes, flat hazard after the last.
    double q(Date d) const;
};

enum class CdsSide { Buy, Sell };
enum class CdsPayout { Standard, Digital };

struct CdsPrice {
    double protection_leg, rpv01, accrued, par_spread, upfront, pv;
};

/// Roll date plus the tenor, on the 20th.
Date cds_maturity(Date trade_date, Tenor tenor);
CdsPrice cds_price(Date trade_date, const Curve& discount, const HazardCurve& hazard, double recovery, Date maturity,
                   double coupon, double notional, CdsSide side, CdsPayout payout);

struct CdsQuote {
    Tenor tenor;
    double spread;
};
HazardCurve cds_bootstrap(Date trade_date, const Curve& discount, double recovery, const std::vector<CdsQuote>& quotes);

}  // namespace quantforge
