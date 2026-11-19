// Stage K wave 1; see stage_k.hpp. A port of the Python build's stage_k.py (as the Java build ports it).
#include "quantforge/core/stage_k.hpp"

#include <algorithm>
#include <cmath>

#include "quantforge/core/error.hpp"
#include "quantforge/core/research.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge::stage_k {
namespace {

using Vec = std::vector<double>;
using research::fsum;

[[noreturn]] void input(const std::string& message, const std::string& field) {
    throw Error("E_INPUT", message, field);
}

[[noreturn]] void domain(const std::string& message, const std::string& field) {
    throw Error("E_DOMAIN", message, field);
}

void limit(std::size_t n, std::size_t most, const std::string& field) {
    if (n > most) throw Error("E_LIMIT", field + " is above its limit of " + std::to_string(most), field);
}

// Continues the recursion after the pillars in `out`; the running sum is accumulated left to right, so a
// continuation is bit-identical to a full build over the same quotes.
Vec bootstrap_from(const Vec& quotes, Vec out) {
    double acc = 0.0;
    for (const double p : out) acc += p;
    for (std::size_t i = out.size(); i < quotes.size(); ++i) {
        const double s = quotes[i];
        const double p = (1.0 - s * acc) / (1.0 + s);
        out.push_back(p);
        acc += p;
    }
    return out;
}

void check_quotes(const Vec& quotes, const std::string& field) {
    if (std::ranges::any_of(quotes, [](double s) { return !(s > -1.0); })) domain("every quote must be above -1", field);
}

}  // namespace

// ---- bitemporal store ----

std::string_view status_name(BiStatus s) {
    switch (s) {
        case BiStatus::Found: return "FOUND";
        case BiStatus::Withdrawn: return "WITHDRAWN";
        default: return "NONE";
    }
}

void check_log(const std::vector<BiRecord>& records) {
    for (std::size_t i = 1; i < records.size(); ++i)
        if (records[i].sequence <= records[i - 1].sequence) input("sequence must be strictly increasing", "records");
    for (std::size_t i = 1; i < records.size(); ++i)
        if (records[i].knowledge_time < records[i - 1].knowledge_time) input("knowledge_time went backwards", "records");
    for (const BiRecord& r : records)
        if (r.valid_to && *r.valid_to <= r.valid_from) input("valid_to must be after valid_from", "records");
}

BiAnswer bitemporal_query(const std::vector<BiRecord>& records, std::string_view series_id,
                          std::int64_t knowledge_as_of, std::int64_t valid_at) {
    check_log(records);
    limit(records.size(), max_records, "records");
    std::optional<std::size_t> best;
    for (std::size_t i = 0; i < records.size(); ++i) {
        const BiRecord& r = records[i];
        if (r.series_id == series_id && r.knowledge_time <= knowledge_as_of && r.valid_from <= valid_at &&
            (!r.valid_to || valid_at < *r.valid_to) && (!best || r.sequence > records[*best].sequence))
            best = i;
    }
    if (!best) return {BiStatus::None, std::nullopt};
    if (records[*best].deleted) return {BiStatus::Withdrawn, std::nullopt};
    return {BiStatus::Found, best};
}

// ---- par bootstrap and incremental update ----

void check_quotes_shape(std::size_t n) {
    if (n < 1) input("quotes must hold at least one quote", "quotes");
}

Vec par_annual(const Vec& quotes) {
    check_quotes_shape(quotes.size());
    check_quotes(quotes, "quotes");
    limit(quotes.size(), max_quotes, "quotes");
    return bootstrap_from(quotes, {});
}

void check_update_shape(std::size_t n_previous, std::size_t n_dfs, std::size_t n_new) {
    if (n_previous < 1 || n_previous != n_dfs || n_dfs != n_new)
        input("previous_quotes, previous_discount_factors and new_quotes must have one equal, non-zero length",
              "new_quotes");
}

Update incremental_update(const Vec& previous_quotes, const Vec& previous_dfs, const Vec& new_quotes) {
    check_update_shape(previous_quotes.size(), previous_dfs.size(), new_quotes.size());
    check_quotes(previous_quotes, "previous_quotes");
    check_quotes(new_quotes, "new_quotes");
    const Vec fresh = bootstrap_from(previous_quotes, {});
    for (std::size_t i = 0; i < fresh.size(); ++i)
        if (fresh[i] != previous_dfs[i] || std::signbit(fresh[i]) != std::signbit(previous_dfs[i]))
            input("previous_discount_factors is not the bootstrap of previous_quotes", "previous_discount_factors");
    limit(new_quotes.size(), max_quotes, "new_quotes");
    std::size_t j = 0;
    while (j < new_quotes.size() && previous_quotes[j] == new_quotes[j]) ++j;
    if (j == new_quotes.size()) return {previous_dfs, std::nullopt, 0};
    return {bootstrap_from(new_quotes, Vec(previous_dfs.begin(), previous_dfs.begin() + std::ptrdiff_t(j))), j,
            new_quotes.size() - j};
}

// ---- recalibration trigger ----

void check_changes_shape(std::size_t n) {
    if (n < 2) input("changes must hold at least two one-day changes", "changes");
}

// 2 (1 - Phi(k)) of KR-6, evaluated as 2 Phi(-k) through the normal CDF, which carries the rounding of
// k / sqrt(2); a bare erfc(k / sqrt(2)) loses about 1.2e-13 relative at k = 30 (trig_k-0009).
namespace {
double two_sided_normal_tail(double k) { return 2.0 * normal_cdf(-k); }
}  // namespace

Trigger trigger_check(const Vec& changes, double x_ref, double x_now, double days_since, double k) {
    check_changes_shape(changes.size());
    if (!(k > 0)) domain("k must be above 0", "k");
    if (!(days_since >= 1)) domain("days_since must be at least 1", "days_since");
    const double n = static_cast<double>(changes.size());
    const double mean = fsum(changes) / n;
    Vec squares;
    squares.reserve(changes.size());
    for (const double x : changes) squares.push_back((x - mean) * (x - mean));
    const double sigma = std::sqrt(fsum(squares) / (n - 1.0));
    if (sigma == 0) domain("the changes have zero standard deviation: no noise scale", "changes");
    limit(changes.size(), max_changes, "changes");
    const double threshold = k * sigma * std::sqrt(days_since);
    return {std::fabs(x_now - x_ref) > threshold, sigma, threshold, two_sided_normal_tail(k)};
}

// ---- intraday delta-gamma ----

void check_positions_shape(std::size_t n) {
    if (n < 1) input("positions must not be empty", "positions");
}

double position_bound(const ZeroPosition& p, double shift) {
    const double t = p.maturity;
    const double m3 = std::pow(t, 3.0) * std::fabs(p.notional) * std::exp(-t * std::min(p.yield, p.yield + shift));
    return std::pow(std::fabs(shift), 3.0) * m3 / 6.0;
}

double position_estimate(const ZeroPosition& p, double shift) {
    const double t = p.maturity;
    const double v = p.notional * std::exp(-p.yield * t);
    return v * (-t * shift + t * t * shift * shift / 2.0);
}

Intraday delta_gamma_bound(const std::vector<ZeroPosition>& positions, double shift) {
    check_positions_shape(positions.size());
    if (std::ranges::any_of(positions, [](const ZeroPosition& p) { return !(p.maturity > 0); }))
        domain("every maturity must be above 0", "positions.maturity");
    limit(positions.size(), max_positions, "positions");
    Vec estimates, bounds;
    estimates.reserve(positions.size());
    bounds.reserve(positions.size());
    for (const ZeroPosition& p : positions) {
        estimates.push_back(position_estimate(p, shift));
        bounds.push_back(position_bound(p, shift));
    }
    return {fsum(estimates), fsum(bounds)};
}

double zero_revalue(const std::vector<ZeroPosition>& positions, double shift) {
    Vec terms;
    terms.reserve(positions.size());
    for (const ZeroPosition& p : positions)
        terms.push_back(p.notional * std::exp(-p.yield * p.maturity) * std::expm1(-shift * p.maturity));
    return fsum(terms);
}

// ---- Richardson guard ----

void check_values_shape(std::size_t n) {
    if (n != 3) input("values must hold exactly three grid values", "values");
}

std::string_view status_name(RichStatus s) {
    switch (s) {
        case RichStatus::Ok: return "OK";
        case RichStatus::OrderMismatch: return "ORDER_MISMATCH";
        default: return "NON_MONOTONE";
    }
}

Richardson richardson_check(const Vec& values, double ratio, double assumed_order) {
    check_values_shape(values.size());
    if (!(ratio > 1)) domain("ratio must be above 1", "ratio");
    if (!(assumed_order > 0)) domain("assumed_order must be above 0", "assumed_order");
    const double f1 = values[0], f2 = values[1], f3 = values[2];
    const double d1 = f1 - f2, d2 = f2 - f3;
    if (d1 == 0 || d2 == 0 || (d1 > 0) != (d2 > 0)) return {RichStatus::NonMonotone, std::nullopt, std::nullopt};
    const double observed = std::log(d1 / d2) / std::log(ratio);
    if (!(std::fabs(observed - assumed_order) <= 0.5)) return {RichStatus::OrderMismatch, observed, std::nullopt};
    const double rp = std::pow(ratio, assumed_order);
    return {RichStatus::Ok, observed, (rp * f3 - f2) / (rp - 1)};
}

}  // namespace quantforge::stage_k
