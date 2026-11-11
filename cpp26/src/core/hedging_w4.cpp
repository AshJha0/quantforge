// Stage I wave 4b: dynamic delta-hedge backtest and hedge effectiveness.
// specifications/08-hedging/dynamic-hedge-and-effectiveness.md, rulings I-29 to I-32.
#include <algorithm>
#include <cmath>
#include <string>

#include "quantforge/core/error.hpp"
#include "quantforge/core/hedging.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge::hedging {
namespace {

void input_if(bool bad, const char* field, const std::string& why) {
    if (bad) throw Error("E_INPUT", std::string(field) + ": " + why, field);
}
void domain_if(bool bad, const char* field, const std::string& why) {
    if (bad) throw Error("E_DOMAIN", std::string(field) + ": " + why, field);
}

// Sum with Neumaier compensation in extended precision, so a series that sums to zero in exact arithmetic is
// seen as zero by the I-31 test.
double exact_sum(const Vec& v) {
    long double s = 0.0L, c = 0.0L;
    for (const double x : v) {
        const long double t = s + x;
        c += std::fabs(s) >= std::fabs((long double)x) ? (s - t) + x : (x - t) + s;
        s = t;
    }
    return double(s + c);
}

bool constant(const Vec& v) {
    return std::ranges::all_of(v, [&](double x) { return x == v.front(); });
}

// Black-Scholes-Merton value and delta at time to expiry tau; at tau = 0 the payoff and no delta.
struct Mark {
    double value, delta;
};
Mark mark(const BacktestOption& o, double s, double tau, double r, double q, double v) {
    const bool call = o.call;
    if (tau <= 0.0) return {call ? std::max(s - o.strike, 0.0) : std::max(o.strike - s, 0.0), 0.0};
    const double sq = std::sqrt(tau);
    const double d1 = (std::log(s / o.strike) + (r - q + 0.5 * v * v) * tau) / (v * sq), d2 = d1 - v * sq;
    const double carry = std::exp(-q * tau), df = std::exp(-r * tau);
    if (call) return {s * carry * normal_cdf(d1) - o.strike * df * normal_cdf(d2), carry * normal_cdf(d1)};
    return {o.strike * df * normal_cdf(-d2) - s * carry * normal_cdf(-d1), -carry * normal_cdf(-d1)};
}

}  // namespace

Effectiveness effectiveness(const Vec& x, const Vec& y) {
    input_if(x.size() != y.size(), "hedge_changes", "length differs from item_changes");
    input_if(x.size() < 3, "item_changes", "needs at least 3 values");
    const double sx = exact_sum(x), sy = exact_sum(y);
    domain_if(sx == 0.0, "item_changes", "sum to zero (I-31)");
    domain_if(constant(x), "item_changes", "zero sample variance (I-31)");
    domain_if(constant(y), "hedge_changes", "zero sample variance (I-31)");
    const double n = double(x.size()), mx = sx / n, my = sy / n;
    double vx = 0.0, vy = 0.0, cxy = 0.0, vs = 0.0;
    const double ms = (sx + sy) / n;
    for (std::size_t i = 0; i < x.size(); ++i) {
        const double dx = x[i] - mx, dy = y[i] - my, ds = (x[i] + y[i]) - ms;
        vx += dx * dx;
        vy += dy * dy;
        cxy += dx * dy;
        vs += ds * ds;
    }
    vx /= n - 1.0;
    vy /= n - 1.0;
    cxy /= n - 1.0;
    vs /= n - 1.0;
    Effectiveness e;
    e.dollar_offset = -sy / sx;
    e.regression_slope = cxy / vx;
    e.regression_r2 = cxy * cxy / (vx * vy);
    e.variance_reduction = 1.0 - vs / vx;
    return e;
}

DeltaBacktest backtest_delta(const BacktestOption& o, double quantity, double r, double q, double vol,
                             const Vec& times, const Vec& spots) {
    // Check 1.
    input_if(times.size() != spots.size(), "spots", "length differs from times");
    input_if(times.size() < 4, "times", "needs at least 4 points");
    input_if(times.front() != 0.0, "times", "must start at 0");
    for (std::size_t i = 1; i < times.size(); ++i) input_if(times[i] <= times[i - 1], "times", "must increase strictly");
    input_if(times.back() > o.expiry_years, "times", "the path ends after expiry");
    // Check 2.
    for (const double s : spots) domain_if(s <= 0.0, "spots", "must be above 0");
    domain_if(o.strike <= 0.0, "option", "strike must be above 0");
    domain_if(o.expiry_years <= 0.0, "option", "expiry_years must be above 0");
    domain_if(vol <= 0.0, "hedge_volatility", "must be above 0");
    // The replay (I-29).
    const std::size_t m = times.size();
    DeltaBacktest out;
    Vec delta(m, 0.0);
    for (std::size_t i = 0; i < m; ++i) {
        const Mark k = mark(o, spots[i], o.expiry_years - times[i], r, q, vol);
        out.option_values.push_back(k.value);
        delta[i] = k.delta;
    }
    for (std::size_t i = 0; i + 1 < m; ++i) out.shares.push_back(-quantity * delta[i] + 0.0);
    double cash = -quantity * out.option_values[0] - out.shares[0] * spots[0];
    out.portfolio_values.push_back(0.0);
    Vec item, hedge;
    for (std::size_t i = 0; i + 1 < m; ++i) {
        const double dt = times[i + 1] - times[i];
        const double interest = cash * std::expm1(r * dt), dividends = out.shares[i] * spots[i] * std::expm1(q * dt);
        cash += interest + dividends;
        const double pi = quantity * out.option_values[i + 1] + out.shares[i] * spots[i + 1] + cash;
        item.push_back(quantity * (out.option_values[i + 1] - out.option_values[i]));
        // hedge_i = (Pi_{i+1} - Pi_i) - item_i, summed from its terms: exactly 0 on a constant path without carry,
        // where the difference of portfolio values would leave rounding noise in front of the I-31 test.
        hedge.push_back(out.shares[i] * (spots[i + 1] - spots[i]) + interest + dividends);
        out.portfolio_values.push_back(pi);
        if (i + 2 < m) cash -= (out.shares[i + 1] - out.shares[i]) * spots[i + 1];
    }
    out.final_pnl = out.portfolio_values.back();
    out.stats = effectiveness(item, hedge);  // check 3 (I-31)
    return out;
}

}  // namespace quantforge::hedging
