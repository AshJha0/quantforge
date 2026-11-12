#include "quantforge/core/inflation.hpp"

#include <cmath>
#include <map>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"

namespace quantforge {

long long month_index(Date d) { return 12LL * year_of(d) + month_of(d) - 1; }

namespace {

void require_finite_curve(const CpiCurve& c) {
    require_finite(c.base_cpi, "base_cpi");
    for (const ZcisQuote& q : c.quotes) {
        require_finite(q.years, "quotes");
        require_finite(q.rate, "quotes");
    }
    require_finite(c.seasonality, "seasonality");
}

}  // namespace

void CpiCurve::check() const {
    require_finite_curve(*this);
    if (quotes.empty()) throw Error("E_INPUT", "no quotes", "quotes");
    double previous = 0.0;
    for (const ZcisQuote& q : quotes) {
        if (!(q.years > previous) || q.years != std::floor(q.years) || q.years > 100)
            throw Error("E_INPUT", "years must be strictly increasing positive integers", "quotes");
        previous = q.years;
    }
    for (const ZcisQuote& q : quotes)
        if (!(q.rate > -1.0)) throw Error("E_DOMAIN", "a rate is at or below -1", "quotes");
    if (seasonality) {
        if (seasonality->size() != 12) throw Error("E_INPUT", "seasonality needs 12 factors", "seasonality");
        for (const double s : *seasonality)
            if (!(s > 0.0)) throw Error("E_DOMAIN", "a seasonality factor is not positive", "seasonality");
    }
    if (!(base_cpi > 0.0)) throw Error("E_DOMAIN", "base_cpi is not positive", "base_cpi");
}

double CpiCurve::cpi(long long k) const {
    if (k < base_month) throw Error("E_OUT_OF_RANGE", "the month is before base_month", "months");
    double k0 = double(base_month), l0 = std::log(base_cpi), slope = 0.0, smooth = 0.0;
    bool done = false;
    for (const ZcisQuote& q : quotes) {
        const double k1 = double(base_month) + 12.0 * q.years, l1 = std::log(base_cpi) + q.years * std::log1p(q.rate);
        slope = (l1 - l0) / (k1 - k0);
        if (double(k) <= k1) {
            smooth = l0 + slope * (double(k) - k0);
            done = true;
            break;
        }
        k0 = k1;
        l0 = l1;
    }
    if (!done) smooth = l0 + slope * (double(k) - k0);
    double i = std::exp(smooth);
    if (k == base_month) i = base_cpi;
    if (seasonality) {
        const auto s = [&](long long m) { return (*seasonality)[std::size_t(((m % 12) + 12) % 12)]; };
        i *= s(k) / s(base_month);
    }
    return i;
}

ZcisPrice zcis_price(const CpiCurve& curve, const Curve& discount, double years, double k, double n, double sign, Date pay) {
    require_finite_curve(curve);
    require_finite(years, "years");
    require_finite(k, "fixed_rate");
    require_finite(n, "notional");
    require_finite(sign, "sign");
    curve.check();
    if (!(years >= 1.0) || years != std::floor(years) || years > 100) throw Error("E_INPUT", "years must be a positive integer", "trade");
    const double ratio = curve.cpi(curve.base_month + 12 * (long long)years) / curve.base_cpi;
    return {ratio, sign * n * (ratio - std::pow(1.0 + k, years)) * discount.discount(pay)};
}

LinkerPrice linker_price(const Bond& bond, Date settlement, double real_yield, double base_ref_cpi,
                         const std::vector<CpiFixing>& fixings) {
    require_finite(bond.coupon, "coupon");
    require_finite(real_yield, "real_yield");
    require_finite(base_ref_cpi, "base_ref_cpi");
    for (const CpiFixing& f : fixings) require_finite(f.value, "cpi_fixings");
    std::map<long long, double> by_month;
    for (const CpiFixing& f : fixings)
        if (!by_month.emplace(f.month, f.value).second) throw Error("E_INPUT", "two fixings share a month", "cpi_fixings");
    const double ref = reference_cpi(settlement, [&](long long m) {
        const auto it = by_month.find(m);
        if (it == by_month.end()) throw Error("E_INPUT", "a needed fixing is missing", "cpi_fixings");
        return it->second;
    });
    if (!(base_ref_cpi > 0.0)) throw Error("E_DOMAIN", "base_ref_cpi is not positive", "base_ref_cpi");
    const YieldPrice p = price_from_yield(bond, settlement, real_yield);
    // R6-7.5 (31 CFR 356 App. B): Ref CPI and index ratio truncated to six decimals, then rounded half up to five.
    const auto trunc6 = [](double x) { return std::floor(x * 1e6) / 1e6; };
    const auto round5 = [](double x) { return std::floor(x * 1e5 + 0.5) / 1e5; };
    const double ref_r = round5(trunc6(ref));
    const double ratio = round5(trunc6(ref_r / base_ref_cpi));
    return {ref_r, ratio, p.clean, p.accrued, p.clean * ratio, p.accrued * ratio};
}

double linker_price_curve(const Bond& bond, Date settlement, double base_ref_cpi, const CpiCurve& curve, const Curve& discount) {
    require_finite(bond.coupon, "coupon");
    require_finite(base_ref_cpi, "base_ref_cpi");
    require_finite_curve(curve);
    curve.check();
    if (!(base_ref_cpi > 0.0)) throw Error("E_DOMAIN", "base_ref_cpi is not positive", "base_ref_cpi");
    const BondPeriod p = bond_period(bond, settlement);
    const double c = coupon_amount(bond);
    double sum = 0.0;
    for (std::size_t k = 0; k < p.flows.size(); ++k) {
        const double cf = c + (k + 1 == p.flows.size() ? 100.0 : 0.0);
        const double ref = reference_cpi(p.flows[k], [&](long long m) { return curve.cpi(m); });
        sum += cf * ref / base_ref_cpi * discount.discount(p.flows[k]);
    }
    return sum / discount.discount(settlement);
}

}  // namespace quantforge
