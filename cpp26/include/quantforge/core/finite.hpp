#pragma once
// Plan item E1: every public numeric input is finite, otherwise E_DOMAIN. A comparison such as vol < 0 lets
// NaN through, so each checked entry point calls these before any other rule check.
//
// Functions documented as "unchecked" in the headers are raw kernels: they take any double, including
// infinities on purpose (for example a normal CDF at -inf), and their callers check their own inputs.
#include <cmath>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "quantforge/core/error.hpp"

namespace quantforge {

[[noreturn]] inline void not_finite(std::string_view field) {
    throw Error("E_DOMAIN", std::string(field) + " must be finite", std::string(field));
}

inline void require_finite(double x, std::string_view field) {
    if (!std::isfinite(x)) not_finite(field);
}

inline void require_finite(const std::optional<double>& x, std::string_view field) {
    if (x) require_finite(*x, field);
}

inline void require_finite(std::span<const double> xs, std::string_view field) {
    for (const double x : xs) require_finite(x, field);
}

inline void require_finite(const std::vector<double>& xs, std::string_view field) {
    require_finite(std::span<const double>(xs), field);
}

inline void require_finite(const std::optional<std::vector<double>>& xs, std::string_view field) {
    if (xs) require_finite(*xs, field);
}

inline void require_finite(const std::vector<std::vector<double>>& rows, std::string_view field) {
    for (const auto& row : rows) require_finite(row, field);
}

}  // namespace quantforge
