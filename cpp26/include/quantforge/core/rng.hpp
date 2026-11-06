#pragma once
#include <array>
#include <cstdint>

namespace quantforge {

/// xoshiro256** seeded by SplitMix64, as fixed by specifications/01-core/rng.md.
class Xoshiro256 {
public:
    using State = std::array<std::uint64_t, 4>;
    explicit Xoshiro256(const State& s) : s_(s) {}
    /// Seeded state advanced by `stream` jumps.
    Xoshiro256(std::uint64_t seed, int stream);
    std::uint64_t next();
    void jump();
    double next_uniform();
    double next_normal();

private:
    State s_{};
};

double uniform_from_bits(std::uint64_t x);
/// Wichura's AS 241. p must lie in (0, 1).
double ppnd16(double p);

}  // namespace quantforge
