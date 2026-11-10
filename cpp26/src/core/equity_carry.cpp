#include "quantforge/core/equity_carry.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <set>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"

namespace quantforge {
namespace {

/// Root of a strictly decreasing f on [-0.5, 0.5], by bisection to the last bit.
template <class F>
double decreasing_root(F f) {
    double lo = -0.5, hi = 0.5;
    const double flo = f(lo), fhi = f(hi);
    if (!(flo >= 0.0 && fhi <= 0.0)) throw Error("E_NOT_BRACKETED", "no solution in [-0.5, 0.5]");
    if (flo == 0.0) return lo;
    if (fhi == 0.0) return hi;
    for (int i = 0; i < 200; ++i) {
        const double mid = (lo + hi) / 2.0;
        if (mid == lo || mid == hi) break;
        const double fm = f(mid);
        if (fm == 0.0) return mid;
        (fm > 0.0 ? lo : hi) = mid;
    }
    return (lo + hi) / 2.0;
}

}  // namespace

double EquityCarry::carry(Date d) const {
    const double t = funding.time(d);
    return funding.discount(d) * std::exp((borrow - spread) * t);
}

double EquityCarry::forward(double spot, const std::vector<CashDividend>& dividends, Date expiry) const {
    double x = spot;
    for (const CashDividend& div : dividends)
        if (div.ex_date > funding.as_of() && div.ex_date <= expiry) x -= div.amount * carry(div.ex_date);
    return x / carry(expiry);
}

ImpliedDividends implied_dividends(double spot, const Curve& funding, double borrow, const std::vector<FuturesQuote>& futures) {
    require_finite(spot, "spot");
    require_finite(borrow, "borrow");
    for (const FuturesQuote& f : futures) require_finite(f.price, "futures");
    if (futures.empty()) throw Error("E_INPUT", "no futures", "futures");
    Date previous = funding.as_of();
    for (const FuturesQuote& f : futures) {
        if (f.expiry <= previous) throw Error("E_INPUT", "expiries must increase and follow as_of", "futures");
        previous = f.expiry;
    }
    if (!(spot > 0.0)) throw Error("E_DOMAIN", "spot is not positive", "spot");
    for (const FuturesQuote& f : futures)
        if (!(f.price > 0.0)) throw Error("E_DOMAIN", "a price is not positive", "futures");
    const EquityCarry c{funding, borrow, 0.0};
    ImpliedDividends out;
    for (const FuturesQuote& f : futures) {
        const double fc = f.price * c.carry(f.expiry);
        out.period_pv_dividends.push_back(spot - fc - (out.pv_dividends.empty() ? 0.0 : out.pv_dividends.back()));
        out.pv_dividends.push_back(spot - fc);
        out.dividend_yields.push_back(-std::log(fc / spot) / funding.time(f.expiry));
    }
    return out;
}

double implied_borrow(double spot, const Curve& funding, const std::vector<CashDividend>& dividends, Date expiry, double forward) {
    require_finite(spot, "spot");
    for (const CashDividend& d : dividends) require_finite(d.amount, "dividends");
    require_finite(forward, "forward");
    if (expiry <= funding.as_of()) throw Error("E_DATE_ORDER", "expiry must follow as_of", "expiry");
    return decreasing_root([&](double b) { return EquityCarry{funding, b, 0.0}.forward(spot, dividends, expiry) - forward; });
}

FuturesBasis equity_futures_basis(double spot, const Curve& funding, double borrow, double spread,
                                  const std::vector<CashDividend>& dividends, Date expiry, double futures_price) {
    require_finite(spot, "spot");
    require_finite(borrow, "borrow");
    require_finite(spread, "spread");
    for (const CashDividend& d : dividends) require_finite(d.amount, "dividends");
    require_finite(futures_price, "futures_price");
    if (expiry <= funding.as_of()) throw Error("E_DATE_ORDER", "expiry must follow as_of", "expiry");
    const double fair = EquityCarry{funding, borrow, spread}.forward(spot, dividends, expiry);
    // F rises with the financing spread s; solve on -s to reuse the decreasing root.
    const double s = -decreasing_root(
        [&](double m) { return EquityCarry{funding, borrow, -m}.forward(spot, dividends, expiry) - futures_price; });
    return {fair, futures_price - fair, s};
}

IndexDividends index_dividends(double divisor, const std::vector<Constituent>& cs, const std::vector<Period2>& periods,
                               const std::vector<double>& implied) {
    require_finite(divisor, "divisor");
    for (const Constituent& c : cs) {
        require_finite(c.shares, "constituents");
        require_finite(c.price, "constituents");
        for (const CashDividend& d : c.dividends) require_finite(d.amount, "constituents");
    }
    require_finite(implied, "implied_period_points");
    if (!(divisor > 0.0)) throw Error("E_DOMAIN", "divisor is not positive", "divisor");
    for (const Period2& p : periods)
        if (p.end < p.start) throw Error("E_DATE_ORDER", "a period ends before it starts", "periods");
    if (periods.size() != implied.size()) throw Error("E_INPUT", "periods and implied_period_points differ in length", "periods");
    IndexDividends out{0.0, {}, {}, {}, {}};
    std::map<Date, double> by_date;
    for (const Constituent& c : cs) {
        out.level += c.shares * c.price;
        for (const CashDividend& d : c.dividends) by_date[d.ex_date] += c.shares * d.amount;
    }
    out.level /= divisor;
    for (const auto& [d, v] : by_date) {
        out.ex_dates.push_back(d);
        out.points.push_back(v / divisor);
    }
    for (std::size_t i = 0; i < periods.size(); ++i) {
        double s = 0.0;
        for (std::size_t j = 0; j < out.ex_dates.size(); ++j)
            if (out.ex_dates[j] >= periods[i].start && out.ex_dates[j] <= periods[i].end) s += out.points[j];
        out.period_points.push_back(s);
        out.basis.push_back(implied[i] - s);
    }
    return out;
}

Rebalance index_rebalance(double divisor, const std::vector<Constituent>& old_list, const std::vector<Constituent>& new_list) {
    require_finite(divisor, "divisor");
    for (const Constituent& c : old_list) {
        require_finite(c.shares, "constituents");
        require_finite(c.price, "constituents");
        for (const CashDividend& d : c.dividends) require_finite(d.amount, "constituents");
    }
    for (const Constituent& c : new_list) {
        require_finite(c.shares, "new_constituents");
        require_finite(c.price, "new_constituents");
        for (const CashDividend& d : c.dividends) require_finite(d.amount, "new_constituents");
    }
    for (const auto* list : {&old_list, &new_list}) {
        std::set<std::string> ids;
        for (const Constituent& c : *list)
            if (!ids.insert(c.id).second) throw Error("E_INPUT", "duplicate id", "constituents");
    }
    if (!(divisor > 0.0)) throw Error("E_DOMAIN", "divisor is not positive", "divisor");
    if (new_list.empty()) throw Error("E_INPUT", "no new constituents", "new_constituents");
    double cap = 0.0, new_cap = 0.0;
    for (const Constituent& c : old_list) cap += c.shares * c.price;
    for (const Constituent& c : new_list) new_cap += c.shares * c.price;
    const double level = cap / divisor;
    Rebalance out{level, new_cap / level, {}};
    for (const Constituent& c : new_list) out.weights.push_back(c.shares * c.price / new_cap);
    return out;
}

ActionResult corporate_action(CorporateAction action, double p, double shares, double strike, double a, double k) {
    require_finite(p, "cum_price");
    require_finite(shares, "shares");
    require_finite(strike, "strike");
    require_finite(a, action == CorporateAction::Rights ? "new_per_old" : action == CorporateAction::SpecialDividend ? "amount" : "ratio");
    require_finite(k, "subscription_price");
    double f = 0.0;
    switch (action) {
        case CorporateAction::Split:
        case CorporateAction::ReverseSplit:
            if (!(a > 0.0)) throw Error("E_DOMAIN", "ratio is not positive", "ratio");
            f = 1.0 / a;
            break;
        case CorporateAction::Rights:
            if (!(a > 0.0)) throw Error("E_DOMAIN", "new_per_old is not positive", "new_per_old");
            if (!(k > 0.0)) throw Error("E_DOMAIN", "subscription_price is not positive", "subscription_price");
            f = (p + a * k) / (1.0 + a) / p;
            break;
        case CorporateAction::SpecialDividend:
            if (!(a > 0.0) || !(a < p)) throw Error("E_DOMAIN", "amount must be in (0, cum_price)", "amount");
            f = (p - a) / p;
            break;
    }
    return {f, f * p, shares / f, f * strike};
}

TrsPrice trs_price(double spot, const Curve& funding, double borrow, const std::vector<CashDividend>& dividends,
                   const TrsTrade& t, std::optional<double> current_rate) {
    require_finite(spot, "spot");
    require_finite(borrow, "borrow");
    for (const CashDividend& d : dividends) require_finite(d.amount, "dividends");
    require_finite(t.initial_price, "trade");
    require_finite(t.shares, "trade");
    require_finite(t.spread, "trade");
    require_finite(t.sign, "trade");
    require_finite(current_rate, "current_rate");
    if (t.end <= t.start) throw Error("E_DATE_ORDER", "end must follow start", "trade");
    if (t.start < funding.as_of() && !current_rate) throw Error("E_INPUT", "current_rate is needed once the period has started", "current_rate");
    const EquityCarry c{funding, borrow, 0.0};
    double divs = 0.0;
    for (const CashDividend& d : dividends)
        if (d.ex_date > funding.as_of() && d.ex_date <= t.end) divs += d.amount;
    const double de = funding.discount(t.end), alpha = double(days_between(t.start, t.end)) / 360.0;
    const double r = current_rate ? *current_rate : (funding.discount(t.start) / de - 1.0) / alpha;
    const double equity = t.shares * de * (c.forward(spot, dividends, t.end) + divs - t.initial_price);
    const double fund = t.shares * t.initial_price * (r + t.spread) * alpha * de;
    return {equity, fund, t.sign * (equity - fund)};
}

}  // namespace quantforge
