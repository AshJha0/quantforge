#pragma once
#include <array>
#include <cstdint>
#include <vector>

namespace quantforge {

/// Gray-code Sobol generator over the Joe-Kuo table. No scrambling.
class Sobol {
public:
    static constexpr int max_dimensions = 64;
    /// The first next() serves index skip + 1. Range checks: check_sobol_request.
    explicit Sobol(int dimensions, std::uint64_t skip = 0);
    /// Writes the next point into out[0..dimensions).
    void next(double* out);

private:
    std::uint64_t index_;
    std::vector<std::array<std::uint32_t, 33>> v_;
    std::vector<std::uint32_t> x_;
};

void check_sobol_request(long long dimensions, long long count, long long skip);

}  // namespace quantforge
