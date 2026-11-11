// Stage I wave 3: cross-asset hedge, equity and rates. specifications/08-hedging/cross-asset-hedge.md,
// rulings I-20 to I-23. The risk matrix comes from repricing (I-21); the solve is wave 1's hedge.qp.solve.
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

// z(T): flat before the first pillar, linear in time between pillars. T is at most the last pillar.
double zero_rate(const ZeroCurve& c, double t) {
    if (t <= c.times.front()) return c.zero_rates.front();
    for (std::size_t i = 1; i < c.times.size(); ++i)
        if (t <= c.times[i]) {
            const double w = (t - c.times[i - 1]) / (c.times[i] - c.times[i - 1]);
            return c.zero_rates[i - 1] + w * (c.zero_rates[i] - c.zero_rates[i - 1]);
        }
    return c.zero_rates.back();
}

bool has_expiry(CrossAssetKind k) { return k != CrossAssetKind::Underlying; }
bool has_strike(CrossAssetKind k) {
    return k == CrossAssetKind::Call || k == CrossAssetKind::Put || k == CrossAssetKind::Forward;
}

}  // namespace

void check_zero_curve(const ZeroCurve& c) {
    input_if(c.times.empty(), "curve", "needs at least one pillar");
    input_if(c.zero_rates.size() != c.times.size(), "curve", "zero_rates and times differ in length");
    input_if(c.times.front() <= 0.0, "curve", "the first pillar time must be above 0");
    for (std::size_t i = 1; i < c.times.size(); ++i)
        input_if(c.times[i] <= c.times[i - 1], "curve", "pillar times must increase strictly");
}

double cross_asset_value(double spot, double q, double vol, const ZeroCurve& c, const CrossAssetPosition& p) {
    if (p.kind == CrossAssetKind::Underlying) return spot;
    const double t = p.expiry_years, r = zero_rate(c, t), df = std::exp(-r * t), carry = std::exp(-q * t);
    switch (p.kind) {
        case CrossAssetKind::Zcb: return p.notional * df;
        case CrossAssetKind::Forward: return spot * carry - p.strike * df;
        default: break;
    }
    const double sq = std::sqrt(t);
    const double d1 = (std::log(spot / p.strike) + (r - q + 0.5 * vol * vol) * t) / (vol * sq), d2 = d1 - vol * sq;
    if (p.kind == CrossAssetKind::Call) return spot * carry * normal_cdf(d1) - p.strike * df * normal_cdf(d2);
    return p.strike * df * normal_cdf(-d2) - spot * carry * normal_cdf(-d1);
}

Vec cross_asset_risk(double spot, double q, double vol, const ZeroCurve& c, const CrossAssetPosition& p) {
    Vec risk;
    risk.push_back(0.5 * (cross_asset_value(1.01 * spot, q, vol, c, p) - cross_asset_value(0.99 * spot, q, vol, c, p)));
    for (std::size_t k = 0; k < c.times.size(); ++k) {
        ZeroCurve up = c, down = c;
        up.zero_rates[k] += 1e-4;
        down.zero_rates[k] -= 1e-4;
        risk.push_back(0.5 * (cross_asset_value(spot, q, vol, up, p) - cross_asset_value(spot, q, vol, down, p)));
    }
    return risk;
}

CrossAssetHedge cross_asset_hedge(double spot, double q, double vol, const ZeroCurve& c,
                                  const std::vector<CrossAssetPosition>& book,
                                  const std::vector<CrossAssetPosition>& hedges, const Vec& weights, double ridge) {
    check_zero_curve(c);
    const std::size_t factors = 1 + c.times.size();
    input_if(book.empty(), "book", "needs at least one position");
    input_if(hedges.empty(), "hedges", "needs at least one instrument");
    input_if(weights.size() != factors, "weights", "one weight per risk factor, 1 + P");
    for (const auto* list : {&book, &hedges})
        for (const CrossAssetPosition& p : *list)
            input_if(has_expiry(p.kind) && p.expiry_years > c.times.back(), list == &book ? "book" : "hedges",
                     "an expiry beyond the last pillar (I-20)");
    domain_if(spot <= 0.0, "spot", "must be above 0");
    domain_if(vol <= 0.0, "volatility", "must be above 0");
    for (const double w : weights) domain_if(w <= 0.0, "weights", "each weight must be above 0");
    domain_if(ridge < 0.0, "ridge", "must be at least 0");
    for (const auto* list : {&book, &hedges})
        for (const CrossAssetPosition& p : *list) {
            const char* field = list == &book ? "book" : "hedges";
            if (has_expiry(p.kind)) domain_if(p.expiry_years <= 0.0, field, "expiry_years must be above 0");
            if (has_strike(p.kind)) domain_if(p.strike <= 0.0, field, "strike must be above 0");
            if (p.kind == CrossAssetKind::Zcb) domain_if(p.notional <= 0.0, field, "notional must be above 0");
        }
    CrossAssetHedge out;
    out.book_risk.assign(factors, 0.0);
    for (const CrossAssetPosition& p : book) {
        const Vec r = cross_asset_risk(spot, q, vol, c, p);
        for (std::size_t f = 0; f < factors; ++f) out.book_risk[f] += p.quantity * r[f];
    }
    QpProblem qp;
    qp.a.assign(factors, Vec(hedges.size(), 0.0));
    for (std::size_t j = 0; j < hedges.size(); ++j) {
        const Vec r = cross_asset_risk(spot, q, vol, c, hedges[j]);
        for (std::size_t f = 0; f < factors; ++f) qp.a[f][j] = r[f];
    }
    qp.b = out.book_risk;
    qp.weights = weights;
    qp.ridge = ridge;
    const QpResult r = solve_qp(qp);  // check 5: E_SINGULAR under policy ERROR
    out.positions = r.x;
    out.residual_risk = r.residual;
    out.objective = r.objective;
    return out;
}

}  // namespace quantforge::hedging
