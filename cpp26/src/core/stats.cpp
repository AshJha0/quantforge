#include "quantforge/core/stats.hpp"

#include <algorithm>
#include <cmath>
#include <numbers>
#include <utility>

#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

}  // namespace

Centred centre(const std::vector<double>& x) {
    std::vector<double> d;
    d.reserve(x.size());
    double m = 0.0;
    for (const double v : x) {
        d.push_back(v - x[0]);
        m += d.back();
    }
    m /= double(x.size());
    for (double& v : d) v -= m;
    return {x[0] + m, std::move(d)};
}

bool all_equal(const std::vector<double>& x) {
    return std::ranges::all_of(x, [&](double v) { return v == x[0]; });
}

double normal_pdf(double x) { return std::exp(-x * x / 2.0) / std::sqrt(2.0 * std::numbers::pi); }

double normal_cdf(double x) {
    // erfc is so steep at x = -37 that rounding x/sqrt(2) alone costs about 3e-13 relative.
    // So carry the rounding error of the argument and correct by one Taylor term.
    constexpr double c_hi = 0.70710678118654757;       // 1/sqrt(2), rounded up
    constexpr double c_lo = -4.8336466567264567e-17;   // 1/sqrt(2) - c_hi
    const double y = -x * c_hi;
    const double dy = std::fma(-x, c_hi, -y) - x * c_lo;
    const double slope = -2.0 / std::sqrt(std::numbers::pi) * std::exp(-y * y);
    return (std::erfc(y) + slope * dy) / 2.0;
}

Summary summary(const std::vector<double>& x) {
    if (x.size() < 2) throw Error("E_INPUT", "at least 2 values are needed", "x");
    const double n = double(x.size());
    const auto [m, dev] = centre(x);
    double s2 = 0.0, s3 = 0.0, s4 = 0.0;
    for (const double d : dev) {
        const double d2 = d * d;
        s2 += d2;
        s3 += d2 * d;
        s4 += d2 * d2;
    }
    Summary r{x.size(), m, s2 / (n - 1.0), std::sqrt(s2 / (n - 1.0)), {}, {}, *std::ranges::min_element(x),
              *std::ranges::max_element(x)};
    if (!all_equal(x)) {
        const double m2 = s2 / n, m3 = s3 / n, m4 = s4 / n;
        r.skewness = m3 / std::pow(m2, 1.5);
        r.excess_kurtosis = m4 / (m2 * m2) - 3.0;
    }
    return r;
}

std::vector<double> quantiles(std::vector<double> x, const std::vector<double>& p) {
    if (x.empty()) throw Error("E_INPUT", "at least 1 value is needed", "x");
    for (const double v : p)
        if (v < 0.0 || v > 1.0) throw Error("E_DOMAIN", "p must lie in [0, 1]", "p");
    std::ranges::sort(x);
    std::vector<double> out;
    out.reserve(p.size());
    const std::size_t n = x.size();
    for (const double v : p) {
        const double h = double(n - 1) * v;
        const auto k = std::size_t(std::floor(h));
        out.push_back(k + 1 >= n ? x[n - 1] : x[k] + (h - double(k)) * (x[k + 1] - x[k]));
    }
    return out;
}

Covariance covariance(const std::vector<double>& x, const std::vector<double>& y) {
    if (x.size() != y.size() || x.size() < 2) throw Error("E_INPUT", "x and y must have equal length of at least 2");
    const auto dx = centre(x).d, dy = centre(y).d;
    double sxy = 0.0, sxx = 0.0, syy = 0.0;
    for (std::size_t i = 0; i < x.size(); ++i) {
        const double a = dx[i], b = dy[i];
        sxy += a * b;
        sxx += a * a;
        syy += b * b;
    }
    Covariance r{sxy / double(x.size() - 1), {}};
    if (!all_equal(x) && !all_equal(y)) r.correlation = sxy / (std::sqrt(sxx) * std::sqrt(syy));
    return r;
}

Ols ols(const std::vector<double>& x, const std::vector<double>& y) {
    if (x.size() != y.size() || x.size() < 3) throw Error("E_INPUT", "x and y must have equal length of at least 3");
    const double n = double(x.size());
    const auto [mx, dx] = centre(x);
    const auto [my, dy] = centre(y);
    double sxx = 0.0, sxy = 0.0, syy = 0.0;
    for (std::size_t i = 0; i < x.size(); ++i) {
        const double a = dx[i], b = dy[i];
        sxx += a * a;
        sxy += a * b;
        syy += b * b;
    }
    if (all_equal(x)) throw Error("E_SINGULAR", "x has zero variance", "x");
    const double beta = sxy / sxx, alpha = my - beta * mx;
    double sse = 0.0;
    for (std::size_t i = 0; i < x.size(); ++i) {
        const double e = dy[i] - beta * dx[i];
        sse += e * e;
    }
    const double s2 = sse / (n - 2.0);
    std::optional<double> r_squared;
    if (!all_equal(y)) r_squared = 1.0 - sse / syy;
    return {alpha, beta, r_squared, std::sqrt(s2 * (1.0 / n + mx * mx / sxx)), std::sqrt(s2 / sxx)};
}

}  // namespace quantforge
