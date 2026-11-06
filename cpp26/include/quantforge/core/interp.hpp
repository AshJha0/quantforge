#pragma once
#include <vector>

namespace quantforge {

enum class InterpMethod { Linear, LogLinear, CubicNatural, CubicClamped, CubicNotAKnot, MonotonePchip, Tension };

struct InterpParams {
    double slope_start = 0.0;
    double slope_end = 0.0;
    double tension = 0.0;
};

struct InterpResult {
    std::vector<double> values;
    std::vector<double> derivatives;  // empty for Linear and LogLinear
};

InterpResult interpolate(InterpMethod method, const std::vector<double>& x, const std::vector<double>& y,
                         const std::vector<double>& at, const InterpParams& params = {});

struct MonotoneConvexResult {
    std::vector<double> forwards;
    std::vector<double> zero_rates;
};

MonotoneConvexResult monotone_convex(const std::vector<double>& t, const std::vector<double>& r,
                                     const std::vector<double>& at, bool positive);

}  // namespace quantforge
