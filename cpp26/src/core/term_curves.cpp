// Stage J curves lane (rulings J-C-1 to J-C-9): financing term structure and liquidity cost curve.
#include "quantforge/core/term_curves.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <string>

#include "quantforge/core/error.hpp"

namespace quantforge::termcurves {
namespace {

[[noreturn]] void input(const std::string& why, const std::string& field = {}) { throw Error("E_INPUT", why, field); }
[[noreturn]] void domain(const std::string& why, const std::string& field = {}) { throw Error("E_DOMAIN", why, field); }

bool increasing_positive(const Vec& ts) {
    for (std::size_t k = 0; k < ts.size(); ++k)
        if (!(ts[k] > 0) || (k > 0 && !(ts[k] > ts[k - 1]))) return false;
    return true;
}

// Linear in y on the knots (0, 0), (ts[k], ys[k]) for t in (0, ts.back()] (J-C-3).
double lin(const Vec& ts, const Vec& ys, double t) {
    double x0 = 0, y0 = 0;
    for (std::size_t k = 0; k < ts.size(); ++k) {
        if (t <= ts[k]) return y0 + (t - x0) / (ts[k] - x0) * (ys[k] - y0);
        x0 = ts[k];
        y0 = ys[k];
    }
    return std::numeric_limits<double>::quiet_NaN();
}

}  // namespace

double FinancingCurve::cover() const {
    const double c = std::min(funding_times.back(), quote_times.back());
    return borrow_times.empty() ? c : std::min(c, borrow_times.back());
}
double FinancingCurve::zt(double t) const { return lin(funding_times, funding_cum, t); }
double FinancingCurve::s(double t) const { return lin(quote_times, spread_cum, t); }
double FinancingCurve::b(double t) const { return borrow_times.empty() ? 0.0 : lin(borrow_times, borrow_cum, t); }
double FinancingCurve::financing_df(double t) const { return std::exp(-zt(t) - s(t)); }

FinancingCurve build(const Vec& ft, const Vec& fz, const Vec& qt, const Vec& qr, const Vec& bt, const Vec& bf) {
    if (ft.size() != fz.size() || qt.size() != qr.size() || bt.size() != bf.size() || ft.empty() || qt.empty())
        input("curve arrays must pair up; funding and quotes non-empty", "quote_times");
    if (!increasing_positive(ft) || !increasing_positive(qt) || !increasing_positive(bt))
        input("times must be positive and strictly increasing");
    for (std::size_t i = 0; i < qt.size(); ++i)
        if (1.0 + qr[i] * qt[i] <= 0) domain("1 + R T must be positive", "repo_rates");
    for (const double f : bf)
        if (f < 0) domain("borrow fees must be non-negative", "borrow_fees");
    FinancingCurve c;
    c.borrow_times = bt;
    for (std::size_t j = 0; j < bt.size(); ++j) {
        c.borrow_cum.push_back(bf[j] * bt[j]);
        if (j > 0 && c.borrow_cum[j] < c.borrow_cum[j - 1]) domain("cumulative borrow fee must not fall", "borrow_fees");
    }
    if (qt.back() > ft.back()) domain("a quote lies beyond the funding curve", "quote_times");
    c.funding_times = ft;
    for (std::size_t k = 0; k < ft.size(); ++k) c.funding_cum.push_back(fz[k] * ft[k]);
    c.quote_times = qt;
    for (std::size_t i = 0; i < qt.size(); ++i) c.spread_cum.push_back(std::log1p(qr[i] * qt[i]) - c.zt(qt[i]));
    return c;
}

TermCurve term_curve(const FinancingCurve& c, const Vec& q) {
    if (q.empty() || !increasing_positive(q)) input("query_times must be non-empty, positive, increasing", "query_times");
    if (q.back() > c.cover()) domain("query beyond the coverage of the curve", "query_times");
    TermCurve r;
    for (std::size_t i = 0; i < c.quote_times.size(); ++i) r.pillar_spreads.push_back(c.spread_cum[i] / c.quote_times[i]);
    double pt = 0, pp = 1;
    Vec fee;
    for (const double t : q) {
        const double p = c.financing_df(t);
        r.financing_df.push_back(p);
        r.spread.push_back(c.s(t) / t);
        r.financing_rate.push_back((1.0 / p - 1.0) / t);
        r.forward_financing.push_back((pp / p - 1.0) / (t - pt));
        pt = t;
        pp = p;
        fee.push_back(c.b(t) / t);
    }
    if (!c.borrow_times.empty()) r.borrow_fee = fee;
    return r;
}

TermForward forward_term_financed(const FinancingCurve& c, double spot, double maturity, const Vec& dt, const Vec& da) {
    if (dt.size() != da.size()) input("dividend arrays must pair up", "dividend_amounts");
    for (std::size_t k = 1; k < dt.size(); ++k)
        if (!(dt[k] > dt[k - 1])) input("dividend_times must be strictly increasing", "dividend_times");
    if (!(spot > 0)) domain("spot must be positive", "spot");
    if (!(maturity > 0 && maturity <= c.cover())) domain("maturity must lie in (0, coverage]", "maturity_years");
    for (const double a : da)
        if (a < 0) domain("dividends must be non-negative", "dividend_amounts");
    const auto carry = [&c](double t) { return std::exp(-c.zt(t) - c.s(t) + c.b(t)); };
    double pv = 0;
    for (std::size_t k = 0; k < dt.size(); ++k)
        if (dt[k] > 0 && dt[k] <= maturity) pv += da[k] * carry(dt[k]);
    const double cf = carry(maturity);
    const double f = (spot - pv) / cf;
    if (!(f > 0)) domain("forward is not positive", "dividend_amounts");
    return {f, f - spot, cf, c.financing_df(maturity), pv};
}

LiquidityCurve liquidity_cost(const LiquidityParams& p, const Vec& sizes, const Vec& horizons) {
    if (sizes.empty() || horizons.empty()) input("sizes and horizons_days must be non-empty", "sizes");
    bool bad = p.half_spread_bps < 0 || !(p.daily_volume > 0) || p.daily_vol < 0 || p.coefficient < 0 ||
               p.risk_multiplier < 0 || !(p.exponent > 0 && p.exponent <= 1);
    for (const double q : sizes) bad = bad || q < 0;
    for (const double h : horizons) bad = bad || !(h > 0);
    if (bad) domain("liquidity curve input out of domain");
    LiquidityCurve r;
    r.spread_cost = p.half_spread_bps / 10000.0;
    for (const double h : horizons) r.timing_risk.push_back(p.risk_multiplier * p.daily_vol * std::sqrt(h / 3.0));
    for (const double q : sizes) {
        Vec imp, tot;
        for (std::size_t j = 0; j < horizons.size(); ++j) {
            imp.push_back(p.coefficient * p.daily_vol * std::pow(q / (p.daily_volume * horizons[j]), p.exponent));
            tot.push_back(r.spread_cost + imp.back() + r.timing_risk[j]);
        }
        r.impact.push_back(imp);
        r.total_cost.push_back(tot);
    }
    const double b = p.risk_multiplier * p.daily_vol / std::sqrt(3.0);
    if (b > 0 && p.coefficient > 0) {
        Vec hs, cs;
        for (const double q : sizes) {
            const double a = p.coefficient * p.daily_vol * std::pow(q / p.daily_volume, p.exponent);
            if (a == 0) {
                hs.push_back(0.0);
                cs.push_back(r.spread_cost);
                continue;
            }
            const double h = std::pow(2.0 * p.exponent * a / b, 1.0 / (p.exponent + 0.5));
            hs.push_back(h);
            cs.push_back(r.spread_cost + a * std::pow(h, -p.exponent) + b * std::sqrt(h));
        }
        r.optimal_horizon = hs;
        r.min_cost = cs;
    }
    return r;
}

}  // namespace quantforge::termcurves
