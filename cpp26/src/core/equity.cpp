#include "quantforge/core/equity.hpp"

#include <algorithm>
#include <cmath>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"

namespace quantforge {

EquityForward equity_forward(double spot, Date as_of, Date expiry, const Curve& funding, const Curve* borrow,
                             const std::vector<Dividend>& dividends) {
    require_finite(spot, "spot");
    for (const Dividend& d : dividends) require_finite(d.amount, "dividends");
    if (funding.as_of() != as_of || (borrow && borrow->as_of() != as_of)) throw Error("E_INPUT", "a curve as_of differs");
    if (expiry < as_of) throw Error("E_DATE_ORDER", "expiry is before as_of");
    for (const Dividend& d : dividends)
        if (d.amount < 0) throw Error("E_DOMAIN", "dividend amount below 0");
    for (std::size_t i = 1; i < dividends.size(); ++i)
        if (!(dividends[i - 1].ex_date < dividends[i].ex_date)) throw Error("E_INPUT", "ex_dates not strictly increasing");

    // The carry factor C = D/B grows the stock and carries dividends (ruling C2).
    const auto carry = [&](Date d) { return funding.discount(d) / (borrow ? borrow->discount(d) : 1.0); };
    const double c_t = carry(expiry);
    double pv = 0.0;
    for (const Dividend& d : dividends)
        if (as_of < d.ex_date && !(expiry < d.ex_date)) pv += d.amount * carry(d.ex_date);
    const double forward = (spot - pv) / c_t;
    if (forward <= 0) throw Error("E_DOMAIN", "forward is not above 0");
    return {forward, funding.discount(expiry), c_t, pv};
}

double equity_forward_flat(double spot, double rate, double borrow, double expiry_years,
                           const std::vector<TimedDividend>& dividends) {
    require_finite(spot, "spot");
    require_finite(rate, "rate");
    require_finite(borrow, "borrow");
    require_finite(expiry_years, "expiry_years");
    for (const TimedDividend& d : dividends) {
        require_finite(d.time_years, "dividends");
        require_finite(d.amount, "dividends");
    }
    if (spot <= 0) throw Error("E_DOMAIN", "spot is not above 0");
    if (expiry_years < 0) throw Error("E_DOMAIN", "expiry_years below 0");
    for (const TimedDividend& d : dividends)
        if (d.amount < 0) throw Error("E_DOMAIN", "dividend amount below 0");
    for (std::size_t i = 1; i < dividends.size(); ++i)
        if (!(dividends[i - 1].time_years < dividends[i].time_years)) throw Error("E_INPUT", "time_years not strictly increasing");
    const double carry = rate - borrow;
    double forward = spot * std::exp(carry * expiry_years);
    for (const TimedDividend& d : dividends)
        if (d.time_years > 0 && d.time_years <= expiry_years)
            forward -= d.amount * std::exp(carry * (expiry_years - d.time_years));
    if (forward <= 0) throw Error("E_DOMAIN", "forward is not above 0");
    return forward;
}

ParityForward parity_forward(const std::vector<ParityQuote>& quotes, std::optional<double> discount_factor) {
    for (const ParityQuote& q : quotes)
        for (const double x : {q.strike, q.call_bid, q.call_ask, q.put_bid, q.put_ask}) require_finite(x, "quotes");
    require_finite(discount_factor, "discount_factor");
    if (quotes.empty()) throw Error("E_INPUT", "quotes is empty");
    for (const ParityQuote& q : quotes) {
        if (q.strike <= 0) throw Error("E_DOMAIN", "strike is not above 0");
        if (q.call_bid < 0 || q.call_ask < 0 || q.put_bid < 0 || q.put_ask < 0) throw Error("E_DOMAIN", "negative quote");
    }
    if (discount_factor && *discount_factor <= 0) throw Error("E_DOMAIN", "discount_factor is not above 0");
    for (std::size_t i = 0; i < quotes.size(); ++i) {
        if (i > 0 && !(quotes[i - 1].strike < quotes[i].strike)) throw Error("E_INPUT", "strikes not strictly increasing");
        if (quotes[i].call_bid > quotes[i].call_ask || quotes[i].put_bid > quotes[i].put_ask)
            throw Error("E_INPUT", "a bid is above its ask");
    }
    if (!discount_factor && quotes.size() < 2) throw Error("E_INPUT", "one quote cannot give a discount factor");

    const double n = double(quotes.size());
    std::vector<double> y;
    for (const ParityQuote& q : quotes) y.push_back((q.call_bid + q.call_ask) / 2 - (q.put_bid + q.put_ask) / 2);
    double d, f;
    if (discount_factor) {
        d = *discount_factor;
        double sum = 0.0;
        for (std::size_t i = 0; i < y.size(); ++i) sum += quotes[i].strike + y[i] / d;
        f = sum / n;
    } else {
        double mean_k = 0.0, mean_y = 0.0;
        for (std::size_t i = 0; i < y.size(); ++i) {
            mean_k += quotes[i].strike;
            mean_y += y[i];
        }
        mean_k /= n;
        mean_y /= n;
        double sxx = 0.0, sxy = 0.0;
        for (std::size_t i = 0; i < y.size(); ++i) {
            const double dk = quotes[i].strike - mean_k;
            sxx += dk * dk;
            sxy += dk * (y[i] - mean_y);
        }
        const double slope = sxy / sxx;
        d = -slope;
        if (d <= 0) throw Error("E_DOMAIN", "fitted discount factor is not above 0");
        f = (mean_y - slope * mean_k) / d;
    }
    if (f <= 0) throw Error("E_DOMAIN", "forward is not above 0");

    ParityForward out{f, d, 0.0, {}};
    for (std::size_t i = 0; i < y.size(); ++i) {
        const ParityQuote& q = quotes[i];
        const double model = d * (f - q.strike);
        out.max_residual = std::max(out.max_residual, std::fabs(y[i] - model));
        if (model < q.call_bid - q.put_ask || model > q.call_ask - q.put_bid) out.outside_spread.push_back(q.strike);
    }
    return out;
}

}  // namespace quantforge
