#pragma once
#include <optional>

namespace quantforge {

enum class CompoundingKind { Simple, Periodic, Continuous };

struct Compounding {
    CompoundingKind kind;
    std::optional<long long> frequency;  // needed by Periodic
};

double discount_factor(double rate, double t, const Compounding& c);
double convert_rate(double rate, double t, const Compounding& from, const Compounding& to);

}  // namespace quantforge
