#include "quantforge/core/fx.hpp"

#include <cmath>

#include "quantforge/core/error.hpp"

using namespace std::chrono;

namespace quantforge {
namespace {

const FxPair pairs[] = {
    {"GBPUSD", "GBP", "USD", 2, {Calendar::Gblo, Calendar::Usgs}, 0.0001},
    {"EURUSD", "EUR", "USD", 2, {Calendar::Euta, Calendar::Usgs}, 0.0001},
};

bool open_on_both(const FxPair& p, Date d) {
    return is_business_day(p.calendars[0], d) && is_business_day(p.calendars[1], d);
}

double forward_at(const FxMarket& m, Date sp, Date t) {
    const double a = m.base->discount(t) / m.base->discount(sp);
    const double b = m.quote->discount(t) / m.quote->discount(sp);
    return m.spot * a / b;
}

double sign_of(FxSide s) { return s == FxSide::Buy ? 1.0 : -1.0; }

struct Leg {
    double pv, delta;
};

Leg forward_leg(const FxMarket& m, Date sp, const FxForwardTrade& t) {
    if (t.value_date < sp) throw Error("E_DATE_ORDER", "value_date is before spot", "value_date");
    const double f = forward_at(m, sp, t.value_date), d = m.quote->discount(t.value_date);
    const double n = sign_of(t.side) * t.notional_base;
    return {n * (f - t.strike) * d, n * (f / m.spot) * d};
}

}  // namespace

const FxPair* fx_pair(std::string_view id) {
    for (const FxPair& p : pairs)
        if (p.id == id) return &p;
    return nullptr;
}

Date fx_spot_date(const FxPair& p, Date d) {
    for (int left = p.spot_lag; left > 0;) {
        d += days{1};
        if (open_on_both(p, d)) --left;
    }
    return d;
}

void check_fx_market(const FxMarket& m) {
    if (m.spot <= 0.0) throw Error("E_DOMAIN", "spot must be positive", "spot");
}

FxOutright fx_outright(const FxMarket& m, Date value_date) {
    check_fx_market(m);
    const Date sp = fx_spot_date(*m.pair, m.as_of);
    if (value_date < sp) throw Error("E_DATE_ORDER", "value_date is before spot", "value_date");
    const double f = forward_at(m, sp, value_date);
    return {f, (f - m.spot) / m.pair->pip};
}

FxPrice fx_forward_price(const FxMarket& m, const FxForwardTrade& t) {
    check_fx_market(m);
    const Leg leg = forward_leg(m, fx_spot_date(*m.pair, m.as_of), t);
    return {{leg.pv, m.pair->quote, "FX_FORWARD_DISCOUNTING", std::nullopt, m.pair->id, m.as_of}, leg.delta};
}

FxPrice fx_swap_price(const FxMarket& m, const FxSwapTrade& t) {
    check_fx_market(m);
    const Date sp = fx_spot_date(*m.pair, m.as_of);
    const FxSide near = t.far_side == FxSide::Buy ? FxSide::Sell : FxSide::Buy;
    const Leg a = forward_leg(m, sp, {t.notional_base, t.near_rate, t.near_date, near});
    const Leg b = forward_leg(m, sp, {t.notional_base, t.far_rate, t.far_date, t.far_side});
    return {{a.pv + b.pv, m.pair->quote, "FX_SWAP_DISCOUNTING", std::nullopt, m.pair->id, m.as_of}, a.delta + b.delta};
}

std::vector<FxNode> fx_implied(const FxMarket& m, const std::vector<FxPoint>& points) {
    check_fx_market(m);
    const Date sp = fx_spot_date(*m.pair, m.as_of);
    std::vector<FxNode> out;
    for (const FxPoint& p : points) {
        const int months = p.tenor.count * (p.tenor.unit == 'Y' ? 12 : 1);
        Date t = adjust(m.pair->calendars[0], add_months(sp, months), BusinessDayConvention::ModifiedFollowing);
        while (!open_on_both(*m.pair, t)) t += days{1};
        if (!out.empty() && t <= out.back().value_date) throw Error("E_INPUT", "points must be in tenor order", "points");
        const double f = m.spot + p.points * m.pair->pip;
        const double b = m.quote->discount(t) / m.quote->discount(sp);
        const double a = m.base->discount(t) / m.base->discount(sp);
        const double ratio = f / m.spot * b;
        const double tau = double(days_between(sp, t)) / 365.0;
        out.push_back({t, ratio, 10000.0 * (-std::log(ratio) / tau + std::log(a) / tau)});
    }
    return out;
}

}  // namespace quantforge
