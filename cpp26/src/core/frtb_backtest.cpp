#include "quantforge/core/frtb_backtest.hpp"

#include <algorithm>
#include <cmath>
#include <string_view>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"

namespace quantforge::frtb_backtest {
namespace {

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wc23-extensions"
#endif
constexpr unsigned char table_bytes[] = {
#embed "../../../specifications/06-risk/frtb-ima-backtest-tables.json"
};
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

Tables parse_tables() {
    const std::string_view text(reinterpret_cast<const char*>(table_bytes), sizeof table_bytes);
    const auto parsed = json::parse(text);
    const json::Value& d = parsed.value;
    const auto num = [&d](std::string_view k) { return d.find(k)->number; };
    Tables t{};
    t.coverage = num("coverage");
    t.amber_level = num("amber_from_cumulative");
    t.red_level = num("red_from_cumulative");
    t.table_observations = (long long)num("table_observations");
    for (const json::Value& m : d.find("multiplier_250")->items) t.multiplier_250.push_back(m.number);
    t.multiplier_red = num("multiplier_red");
    t.desk_limit_99 = (long long)num("desk_limit_99");
    t.desk_limit_975 = (long long)num("desk_limit_975");
    t.max_observations = (long long)num("max_observations");
    return t;
}

constexpr double p_99 = 0.01;  // KR-237: the binary64 literal nearest 1/100 (not 1 - coverage)
constexpr double p_975 = 0.025;
constexpr double up = 0x1p600;
constexpr double down = 0x1p-600;

struct Partial {
    double sum;
    long long scale;
};

// KR-237: compensated partial sums of the unnormalised weights w_0 = 1, w_(k+1) = w_k ((n - k) p) / ((k + 1) q),
// each with its scale count (a weight above 2^600 rescales the weight and the sum by 2^-600). Stops at n, or past
// the mode once the ratio is at most 1/2 and the weight at most 2^-64 of the sum. Only + - * /, as the Python
// build's binomial_partial_sums, so every build gives the same bits.
std::vector<Partial> partial_sums(long long n, double p) {
    const double q = 1.0 - p;
    const double mode = std::floor(double(n + 1) * p);
    double w = 1.0, s = 0.0, c = 0.0;
    long long e = 0;
    std::vector<Partial> out;
    long long k = 0;
    while (true) {
        const double t = s + w;
        c += std::fabs(s) >= std::fabs(w) ? (s - t) + w : (w - t) + s;
        s = t;
        out.push_back({s + c, e});
        if (k == n) return out;
        const double r = (double(n - k) * p) / (double(k + 1) * q);
        w = w * r;
        ++k;
        if (double(k) > mode && r <= 0.5 && w <= (s + c) * 0x1p-64) return out;
        if (w > up) {
            w = w * down;
            s = s * down;
            c = c * down;
            ++e;
        }
    }
}

double cdf_from(const std::vector<Partial>& sums, long long n, long long x) {
    if (x < 0) return 0.0;
    if (x >= n || x >= (long long)sums.size() - 1) return 1.0;
    const Partial& at = sums[std::size_t(x)];
    const Partial& last = sums.back();
    double v = at.sum / last.sum;
    for (long long i = 0; i < last.scale - at.scale; ++i) v *= down;
    return std::min(v, 1.0);
}

long long first_at_least_in(const std::vector<Partial>& sums, long long n, double level) {
    for (long long k = 0; k < n; ++k)
        if (cdf_from(sums, n, k) >= level) return k;
    return n;
}

void check_observations(long long n) {
    const long long cap = tables().max_observations;
    if (n > cap) throw Error("E_LIMIT", "observations is above its limit of " + std::to_string(cap), "observations");
    if (n < 1) throw Error("E_DOMAIN", "observations must be at least 1", "observations");
}

void check_count(long long n, long long x, const char* field) {
    if (!(0 <= x && x <= n)) throw Error("E_DOMAIN", std::string(field) + " must be in [0, observations]", field);
}

std::vector<long long> days(const std::vector<std::optional<double>>& var,
                            const std::vector<std::optional<double>>& pnl) {
    std::vector<long long> out;
    for (std::size_t t = 0; t < var.size(); ++t)
        if (!var[t] || !pnl[t] || -*pnl[t] > *var[t]) out.push_back((long long)t);
    return out;
}

void finite_series(const char* field, const std::vector<std::optional<double>>& v) {
    for (const auto& x : v)
        if (x && !std::isfinite(*x)) throw Error("E_DOMAIN", std::string(field) + " must be finite", field);
}

}  // namespace

const Tables& tables() {
    static const Tables t = parse_tables();
    return t;
}

double binomial_cdf(long long n, long long x, double p) {
    if (x < 0) return 0.0;
    if (x >= n) return 1.0;
    return cdf_from(partial_sums(n, p), n, x);
}

long long first_at_least(long long n, double p, double level) { return first_at_least_in(partial_sums(n, p), n, level); }

Zone zone(long long observations, long long actual, long long hypothetical) {
    check_observations(observations);
    check_count(observations, actual, "exceptions_actual");
    check_count(observations, hypothetical, "exceptions_hypothetical");
    const Tables& tb = tables();
    const long long x = std::max(actual, hypothetical);
    const std::vector<Partial> sums = partial_sums(observations, p_99);
    Zone z{};
    z.exceptions = x;
    z.cumulative_probability = cdf_from(sums, observations, x);
    z.amber_from = first_at_least_in(sums, observations, tb.amber_level);
    z.red_from = first_at_least_in(sums, observations, tb.red_level);
    z.zone = x >= z.red_from ? "RED" : x >= z.amber_from ? "AMBER" : "GREEN";
    if (observations == tb.table_observations)
        z.multiplier = std::size_t(x) < tb.multiplier_250.size() ? tb.multiplier_250[std::size_t(x)] : tb.multiplier_red;
    return z;
}

Desk desk(long long observations, const std::array<long long, 4>& counts) {
    check_observations(observations);
    constexpr const char* fields[] = {"exceptions_99_actual", "exceptions_99_hypothetical", "exceptions_975_actual",
                                      "exceptions_975_hypothetical"};
    for (std::size_t i = 0; i < 4; ++i) check_count(observations, counts[i], fields[i]);
    const Tables& tb = tables();
    Desk out{};
    out.exceptions_99 = std::max(counts[0], counts[1]);
    out.exceptions_975 = std::max(counts[2], counts[3]);
    out.cumulative_probability_99 = binomial_cdf(observations, out.exceptions_99, p_99);
    out.cumulative_probability_975 = binomial_cdf(observations, out.exceptions_975, p_975);
    out.breach_99 = out.exceptions_99 > tb.desk_limit_99;
    out.breach_975 = out.exceptions_975 > tb.desk_limit_975;
    out.eligible = !(out.breach_99 || out.breach_975);
    return out;
}

Count count_exceptions(const std::vector<std::optional<double>>& var, const std::vector<std::optional<double>>& actual,
                       const std::vector<std::optional<double>>& hypothetical) {
    finite_series("var", var);
    finite_series("actual", actual);
    finite_series("hypothetical", hypothetical);
    const std::size_t n = var.size();
    if (n == 0) throw Error("E_INPUT", "var is empty", "var");
    if (actual.size() != n) throw Error("E_INPUT", "actual and var differ in length", "actual");
    if (hypothetical.size() != n) throw Error("E_INPUT", "hypothetical and var differ in length", "hypothetical");
    Count c{};
    c.observations = (long long)n;
    c.days_actual = days(var, actual);
    c.days_hypothetical = days(var, hypothetical);
    c.exceptions_actual = (long long)c.days_actual.size();
    c.exceptions_hypothetical = (long long)c.days_hypothetical.size();
    c.exceptions = std::max(c.exceptions_actual, c.exceptions_hypothetical);
    return c;
}

}  // namespace quantforge::frtb_backtest
