#pragma once
// Stage D, D6: CPI curves with seasonality, zero-coupon inflation swaps and linkers (02-curves/inflation.md).
#include <optional>
#include <vector>

#include "quantforge/core/bonds.hpp"

namespace quantforge {

/// Month index k = 12 year + month - 1.
long long month_index(Date d);

struct ZcisQuote {
    double years, rate;
};

struct CpiCurve {
    long long base_month;
    double base_cpi;
    std::vector<ZcisQuote> quotes;
    std::optional<std::vector<double>> seasonality;

    /// The checks of infl.curve.cpi, in order, short of the month check.
    void check() const;
    /// E_OUT_OF_RANGE before base_month. Call check() first.
    /// unchecked: caller guarantees finite inputs
    double cpi(long long month) const;
};

struct ZcisPrice {
    double index_ratio, pv;
};
/// sign +1 for RECEIVE_INFLATION.
ZcisPrice zcis_price(const CpiCurve& curve, const Curve& discount, double years, double fixed_rate, double notional,
                     double sign, Date payment_date);

/// TIPS reference CPI: three-month lag, daily interpolation; `index(month)` gives I.
template <class F>
double reference_cpi(Date d, F index) {
    using namespace std::chrono;
    const year_month_day ymd{d};
    const long long m = month_index(d);
    const double dim = double(unsigned((ymd.year() / ymd.month() / last).day()));
    const double a = index(m - 3), b = index(m - 2);
    return a + (double(unsigned(ymd.day())) - 1.0) / dim * (b - a);
}

struct CpiFixing {
    long long month;
    double value;
};
struct LinkerPrice {
    double ref_cpi, index_ratio, real_clean, real_accrued, nominal_clean, nominal_accrued;
};
LinkerPrice linker_price(const Bond& bond, Date settlement, double real_yield, double base_ref_cpi,
                         const std::vector<CpiFixing>& fixings);
double linker_price_curve(const Bond& bond, Date settlement, double base_ref_cpi, const CpiCurve& curve, const Curve& discount);

}  // namespace quantforge
