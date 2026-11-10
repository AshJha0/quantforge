#include "quantforge/core/compounding.hpp"

#include <cmath>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"

namespace quantforge {
namespace {

void check_base(double rate, double t, const Compounding& c) {
    if (c.kind == CompoundingKind::Simple && 1.0 + rate * t <= 0.0)
        throw Error("E_DOMAIN", "1 + r t must be positive", "rate");
    if (c.kind == CompoundingKind::Periodic && 1.0 + rate / double(*c.frequency) <= 0.0)
        throw Error("E_DOMAIN", "1 + r/n must be positive", "rate");
}

double factor(double rate, double t, const Compounding& c) {
    switch (c.kind) {
        case CompoundingKind::Simple: return 1.0 / (1.0 + rate * t);
        case CompoundingKind::Periodic: {
            const double n = double(*c.frequency);
            return std::pow(1.0 + rate / n, -n * t);
        }
        case CompoundingKind::Continuous: return std::exp(-rate * t);
    }
    return 0.0;
}

double rate_from(double d, double t, const Compounding& c) {
    switch (c.kind) {
        case CompoundingKind::Simple: return (1.0 / d - 1.0) / t;
        case CompoundingKind::Periodic: {
            const double n = double(*c.frequency);
            return n * (std::pow(d, -1.0 / (n * t)) - 1.0);
        }
        case CompoundingKind::Continuous: return -std::log(d) / t;
    }
    return 0.0;
}

}  // namespace

void check_frequency(const Compounding& c) {
    if (c.kind != CompoundingKind::Periodic) return;
    if (!c.frequency) throw Error("E_SCHEMA", "PERIODIC needs a frequency", "frequency");
    const long long n = *c.frequency;
    if (n != 1 && n != 2 && n != 3 && n != 4 && n != 6 && n != 12)
        throw Error("E_SCHEMA", "frequency is not listed", "frequency");
}

double discount_factor(double rate, double t, const Compounding& c) {
    require_finite(rate, "rate");
    require_finite(t, "t");
    check_frequency(c);
    if (t < 0.0) throw Error("E_DOMAIN", "t is negative", "t");
    check_base(rate, t, c);
    if (t == 0.0) return 1.0;
    return factor(rate, t, c);
}

double convert_rate(double rate, double t, const Compounding& from, const Compounding& to) {
    require_finite(rate, "rate");
    require_finite(t, "t");
    check_frequency(from);
    check_frequency(to);
    if (t < 0.0) throw Error("E_DOMAIN", "t is negative", "t");
    if (t == 0.0) throw Error("E_DOMAIN", "the rate is undefined at t = 0", "t");
    check_base(rate, t, from);
    return rate_from(factor(rate, t, from), t, to);
}

}  // namespace quantforge
