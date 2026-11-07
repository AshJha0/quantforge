#include "quantforge/core/surface.hpp"

#include <algorithm>
#include <cmath>

#include "quantforge/core/black.hpp"
#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

constexpr double tolerance = 1e-12;

bool increasing(const std::vector<double>& v) {
    for (std::size_t i = 1; i < v.size(); ++i)
        if (!(v[i - 1] < v[i])) return false;
    return true;
}

double node_w(const Surface& s, std::size_t j, std::size_t i) { return s.vols[j][i] * s.vols[j][i] * s.expiry_years[j]; }

// w is linear in k on a slice, with k clamped to the grid.
double slice_w(const Surface& s, std::size_t j, double k) {
    const auto& g = s.log_moneyness;
    if (k <= g.front()) return node_w(s, j, 0);
    if (k >= g.back()) return node_w(s, j, g.size() - 1);
    const std::size_t i = std::size_t(std::ranges::upper_bound(g, k) - g.begin()) - 1;
    const double u = (k - g[i]) / (g[i + 1] - g[i]);
    return node_w(s, j, i) + u * (node_w(s, j, i + 1) - node_w(s, j, i));
}

}  // namespace

void check_surface(const Surface& s) {
    if (s.expiry_years.empty() || s.log_moneyness.empty() || !increasing(s.expiry_years) || !increasing(s.log_moneyness) ||
        s.vols.size() != s.expiry_years.size())
        throw Error("E_INPUT", "grids are not strictly increasing, or shapes differ");
    for (const auto& row : s.vols)
        if (row.size() != s.log_moneyness.size()) throw Error("E_INPUT", "a row does not match the grid");
    for (const double t : s.expiry_years)
        if (t <= 0) throw Error("E_DOMAIN", "a grid time is not above 0");
    for (const auto& row : s.vols)
        for (const double v : row)
            if (v <= 0) throw Error("E_DOMAIN", "a vol is not above 0");
}

double surface_total_variance(const Surface& s, double t, double k) {
    const auto& g = s.expiry_years;
    if (t <= g.front()) return slice_w(s, 0, k) * t / g.front();
    if (t >= g.back()) return slice_w(s, g.size() - 1, k) * t / g.back();
    const std::size_t j = std::size_t(std::ranges::upper_bound(g, t) - g.begin()) - 1;
    const double u = (t - g[j]) / (g[j + 1] - g[j]), low = slice_w(s, j, k);
    return low + u * (slice_w(s, j + 1, k) - low);
}

SurfaceCheck surface_check(const Surface& s) {
    SurfaceCheck out;
    const std::size_t rows = s.expiry_years.size(), n = s.log_moneyness.size();
    for (std::size_t j = 1; j < rows; ++j)
        for (std::size_t i = 0; i < n; ++i)
            if (node_w(s, j, i) < node_w(s, j - 1, i) - tolerance) out.calendar.push_back({j, i});
    for (std::size_t j = 0; j < rows; ++j) {
        std::vector<double> strikes, calls, slopes;
        for (std::size_t i = 0; i < n; ++i) {
            strikes.push_back(std::exp(s.log_moneyness[i]));
            calls.push_back(black_price(1.0, strikes[i], s.vols[j][i], s.expiry_years[j], 1.0, 1.0));
        }
        for (std::size_t i = 0; i + 1 < n; ++i) slopes.push_back((calls[i + 1] - calls[i]) / (strikes[i + 1] - strikes[i]));
        for (std::size_t i = 0; i < slopes.size(); ++i)
            if (slopes[i] < -1 - tolerance || slopes[i] > tolerance) out.butterfly.push_back({j, i, "SLOPE"});
        for (std::size_t i = 0; i + 1 < slopes.size(); ++i)
            if (slopes[i + 1] < slopes[i] - tolerance) out.butterfly.push_back({j, i + 1, "CONVEXITY"});
    }
    return out;
}

}  // namespace quantforge
