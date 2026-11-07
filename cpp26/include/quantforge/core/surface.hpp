#pragma once
// Vol surface on a (time, log-moneyness) grid: 05-volatility/smile-and-surface.md.
#include <string>
#include <vector>

#include "quantforge/core/linalg.hpp"

namespace quantforge {

struct Surface {
    std::vector<double> expiry_years, log_moneyness;
    Matrix vols;
};
void check_surface(const Surface& s);
double surface_total_variance(const Surface& s, double t, double k);

struct CalendarViolation {
    std::size_t expiry_index, k_index;
};
struct ButterflyViolation {
    std::size_t expiry_index, k_index;
    std::string kind;
};
struct SurfaceCheck {
    std::vector<CalendarViolation> calendar;
    std::vector<ButterflyViolation> butterfly;
};
SurfaceCheck surface_check(const Surface& s);

}  // namespace quantforge
