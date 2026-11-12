// Stage I wave 2: credit and correlation hedges. specifications/08-hedging/credit-and-correlation-hedges.md,
// rulings I-15 to I-19. The CDS legs are those of credit.cds.price (04-pricing/credit.md).
#include <algorithm>
#include <cmath>
#include <string>

#include "quantforge/core/dates.hpp"
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

// Square solve G q = rhs after the I-3 singularity check on G.
Vec square_solve(const Matrix& g, const Vec& rhs, const char* field) {
    const Vec sv = singular_values(g);
    if (sv.back() <= singular_threshold * sv.front())
        throw Error("E_SINGULAR", "the hedge instruments cannot set the targets independently", field);
    Vec q = lu_solve(g, rhs);
    for (double& v : q) v += 0.0;
    return q;
}

// The hazard curve with the piecewise-flat hazards h_k shifted by eps, on every section or on one (I-15).
// Survival is rebuilt from the shifted hazards; the last section's hazard covers the time after it.
HazardCurve shifted(const HazardCurve& h, double eps, std::optional<std::size_t> only) {
    HazardCurve out = h;
    double t0 = 0.0, l0 = 0.0, cumulative = 0.0;
    for (std::size_t k = 0; k < h.dates.size(); ++k) {
        const double t1 = double(days_between(h.as_of, h.dates[k])) / 365.0, l1 = -std::log(h.survival[k]);
        const double hazard = (l1 - l0) / (t1 - t0) + (!only || *only == k ? eps : 0.0);
        if (hazard < 0.0)  // R6-11.9: the downward bump makes a hazard negative
            throw Error("E_DOMAIN", "a bumped hazard rate is below 0 (spread under about 1 bp)", "hazard");
        cumulative += hazard * (t1 - t0);
        out.survival[k] = std::exp(-cumulative);
        t0 = t1;
        l0 = l1;
    }
    return out;
}

double unit_pv(Date t, const Curve& discount, const HazardCurve& h, double recovery, Date maturity, double coupon) {
    return cds_price(t, discount, h, recovery, maturity, coupon, 1.0, CdsSide::Buy, CdsPayout::Standard).pv;
}

double credit_value(const CreditRisk& r, const CreditTarget& t) {
    switch (t.kind) {
        case CreditTarget::Kind::Cs01: return r.cs01;
        case CreditTarget::Kind::Jtd: return r.jtd;
        case CreditTarget::Kind::Bucket: return r.buckets[t.bucket];
    }
    return 0.0;
}

void add_scaled(CreditRisk& into, const CreditRisk& unit, double scale) {
    into.pv += scale * unit.pv;
    into.cs01 += scale * unit.cs01;
    into.jtd += scale * unit.jtd;
    for (std::size_t k = 0; k < unit.buckets.size(); ++k) into.buckets[k] += scale * unit.buckets[k];
}

}  // namespace

CreditRisk unit_credit_risk(Date t, const Curve& discount, const HazardCurve& h, double recovery, Date maturity,
                            double coupon) {
    const double eps = 1e-4 / (1.0 - recovery);
    const auto central = [&](std::optional<std::size_t> only) {
        return 0.5 * (unit_pv(t, discount, shifted(h, eps, only), recovery, maturity, coupon) -
                      unit_pv(t, discount, shifted(h, -eps, only), recovery, maturity, coupon));
    };
    CreditRisk r;
    r.pv = unit_pv(t, discount, h, recovery, maturity, coupon);
    r.cs01 = central(std::nullopt);
    r.jtd = (1.0 - recovery) - r.pv;  // I-16
    for (std::size_t k = 0; k < h.dates.size(); ++k) r.buckets.push_back(central(k));
    return r;
}

namespace {

std::vector<CreditTarget> credit_targets(const std::vector<std::string>& names, std::size_t pillars) {
    std::vector<CreditTarget> out;
    for (const std::string& s : names) {
        CreditTarget t;
        if (s == "CS01") {
            t.kind = CreditTarget::Kind::Cs01;
        } else if (s == "JTD") {
            t.kind = CreditTarget::Kind::Jtd;
        } else {
            const std::string prefix = "BUCKET_";
            const std::string digits = s.starts_with(prefix) ? s.substr(prefix.size()) : std::string{};
            const bool numeric = !digits.empty() && digits.size() <= 6 && digits[0] != '0' &&
                                 std::ranges::all_of(digits, [](char c) { return c >= '0' && c <= '9'; });
            const std::size_t k = numeric ? std::stoul(digits) : 0;
            input_if(k < 1 || k > pillars, "targets", "unknown target " + s);
            t.kind = CreditTarget::Kind::Bucket;
            t.bucket = k - 1;
        }
        input_if(std::ranges::find(out, t) != out.end(), "targets", "a target is repeated");
        out.push_back(t);
    }
    return out;
}

}  // namespace

CreditHedge credit_hedge(Date t, const Curve& discount, const HazardCurve& hazard, double recovery,
                         const std::vector<CdsContract>& book, const std::vector<CdsContract>& hedges,
                         const std::vector<std::string>& target_names) {
    // Check 2.
    input_if(book.empty(), "book", "needs at least one trade");
    input_if(hedges.empty(), "hedges", "needs at least one contract");
    input_if(target_names.size() != hedges.size(), "targets", "one target per hedge contract");
    const std::vector<CreditTarget> targets = credit_targets(target_names, hazard.dates.size());
    for (const CdsContract& c : book) input_if(c.maturity <= t, "book", "a maturity is on or before trade_date");
    for (const CdsContract& c : hedges) input_if(c.maturity <= t, "hedges", "a maturity is on or before trade_date");
    // Check 3.
    domain_if(!(recovery >= 0.0 && recovery < 1.0), "recovery", "must be in [0, 1)");
    for (const CdsContract& c : book) {
        domain_if(c.notional < 0.0, "book", "a notional is below 0");
        domain_if(c.coupon < 0.0, "book", "a coupon is below 0");
    }
    for (const CdsContract& c : hedges) domain_if(c.coupon < 0.0, "hedges", "a coupon is below 0");
    // Risks.
    const std::size_t pillars = hazard.dates.size(), n = hedges.size();
    CreditHedge out;
    out.book.buckets.assign(pillars, 0.0);
    for (const CdsContract& c : book)
        add_scaled(out.book, unit_credit_risk(t, discount, hazard, recovery, c.maturity, c.coupon),
                   (c.buy ? 1.0 : -1.0) * c.notional);
    std::vector<CreditRisk> unit;
    Vec upfront;
    for (const CdsContract& c : hedges) {
        unit.push_back(unit_credit_risk(t, discount, hazard, recovery, c.maturity, c.coupon));
        upfront.push_back(cds_price(t, discount, hazard, recovery, c.maturity, c.coupon, 1.0, CdsSide::Buy,
                                    CdsPayout::Standard)
                              .upfront);
    }
    // Check 4 and the solve.
    Matrix g(n, Vec(n));
    Vec rhs(n);
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = 0; j < n; ++j) g[i][j] = credit_value(unit[j], targets[i]);
        rhs[i] = -credit_value(out.book, targets[i]);
    }
    out.notionals = square_solve(g, rhs, "hedges");
    out.after = out.book;
    for (std::size_t j = 0; j < n; ++j) {
        add_scaled(out.after, unit[j], out.notionals[j]);
        out.hedge_upfront += out.notionals[j] * upfront[j];
    }
    return out;
}

// ---- correlation ----

TwoAssetGreeks unit_two_asset_greeks(const TwoAssetMarket& m, const TwoAssetPosition& p) {
    TwoAssetGreeks g{};
    const auto vanilla = [&](bool first, Instrument kind) {
        const Market one{first ? m.spot1 : m.spot2, m.rate, first ? m.yield1 : m.yield2, first ? m.vol1 : m.vol2};
        const Greeks u = unit_greeks(one, Position{kind, p.strike, p.expiry_years, 1.0});
        g[first ? 0 : 1] = u.delta;
        g[first ? 2 : 3] = u.vega;
    };
    switch (p.kind) {
        case TwoAssetKind::Underlying1: g[0] = 1.0; break;
        case TwoAssetKind::Underlying2: g[1] = 1.0; break;
        case TwoAssetKind::Call1: vanilla(true, Instrument::Call); break;
        case TwoAssetKind::Put1: vanilla(true, Instrument::Put); break;
        case TwoAssetKind::Call2: vanilla(false, Instrument::Call); break;
        case TwoAssetKind::Put2: vanilla(false, Instrument::Put); break;
        case TwoAssetKind::Exchange: {
            // Margrabe [M78]: receive Q1 S1 for Q2 S2 at expiry.
            const double t = p.expiry_years, sq = std::sqrt(t), rho = m.correlation;
            const double s = std::sqrt(m.vol1 * m.vol1 + m.vol2 * m.vol2 - 2.0 * rho * m.vol1 * m.vol2);
            if (!(s > 1e-12 * (m.vol1 + m.vol2)))  // R6-11.16: a degenerate Margrabe volatility
                throw Error("E_SINGULAR", "the spread volatility of an exchange option is 0", "hedges");
            const double c1 = p.quantity1 * std::exp(-m.yield1 * t), c2 = p.quantity2 * std::exp(-m.yield2 * t);
            const double f1 = c1 * m.spot1, f2 = c2 * m.spot2;
            const double d1 = (std::log(f1 / f2) + 0.5 * s * s * t) / (s * sq), d2 = d1 - s * sq;
            const double dvds = f1 * normal_pdf(d1) * sq;
            g[0] = c1 * normal_cdf(d1);
            g[1] = -c2 * normal_cdf(d2);
            g[2] = dvds * (m.vol1 - rho * m.vol2) / s;
            g[3] = dvds * (m.vol2 - rho * m.vol1) / s;
            g[4] = dvds * (-m.vol1 * m.vol2 / s) * 0.01;  // per 0.01 of correlation (I-18)
            break;
        }
    }
    return g;
}

CorrelationHedge correlation_hedge(const TwoAssetMarket& m, const std::vector<TwoAssetPosition>& book,
                                   const std::vector<TwoAssetPosition>& hedges,
                                   const std::vector<TwoAssetTarget>& targets) {
    input_if(hedges.empty(), "hedges", "needs at least one hedge instrument");
    input_if(targets.size() != hedges.size(), "targets", "one target per hedge instrument");
    for (std::size_t i = 0; i < targets.size(); ++i)
        for (std::size_t j = 0; j < i; ++j) input_if(targets[i] == targets[j], "targets", "a target is repeated");
    domain_if(m.spot1 <= 0.0, "spot1", "must be above 0");
    domain_if(m.spot2 <= 0.0, "spot2", "must be above 0");
    domain_if(m.vol1 <= 0.0, "vol1", "must be above 0");
    domain_if(m.vol2 <= 0.0, "vol2", "must be above 0");
    domain_if(!(m.correlation >= -1.0 && m.correlation <= 1.0), "correlation", "must be in [-1, 1]");
    bool exchange = false;
    for (const auto* list : {&book, &hedges})
        for (const TwoAssetPosition& p : *list) {
            const char* field = list == &book ? "book" : "hedges";
            if (p.kind == TwoAssetKind::Exchange) {
                exchange = true;
                domain_if(p.quantity1 <= 0.0 || p.quantity2 <= 0.0, field, "quantity1 and quantity2 must be above 0");
            } else if (p.kind != TwoAssetKind::Underlying1 && p.kind != TwoAssetKind::Underlying2) {
                domain_if(p.strike <= 0.0, field, "strike must be above 0");
            }
            if (p.kind != TwoAssetKind::Underlying1 && p.kind != TwoAssetKind::Underlying2)
                domain_if(p.expiry_years <= 0.0, field, "expiry_years must be above 0");
        }
    const double s2 = m.vol1 * m.vol1 + m.vol2 * m.vol2 - 2.0 * m.correlation * m.vol1 * m.vol2;
    domain_if(exchange && s2 <= 0.0, "correlation", "the spread volatility is 0");
    CorrelationHedge out;
    for (const TwoAssetPosition& p : book) {
        const TwoAssetGreeks u = unit_two_asset_greeks(m, p);
        for (std::size_t k = 0; k < 5; ++k) out.before[k] += p.quantity * u[k];
    }
    const std::size_t n = hedges.size();
    std::vector<TwoAssetGreeks> unit;
    for (const TwoAssetPosition& p : hedges) unit.push_back(unit_two_asset_greeks(m, p));
    Matrix g(n, Vec(n));
    Vec rhs(n);
    for (std::size_t i = 0; i < n; ++i) {
        const auto row = std::size_t(targets[i]);
        for (std::size_t j = 0; j < n; ++j) g[i][j] = unit[j][row];
        rhs[i] = -out.before[row];
    }
    out.quantities = square_solve(g, rhs, "hedges");
    out.after = out.before;
    for (std::size_t j = 0; j < n; ++j)
        for (std::size_t k = 0; k < 5; ++k) out.after[k] += out.quantities[j] * unit[j][k];
    return out;
}

}  // namespace quantforge::hedging
