#include "quantforge/core/rng.hpp"

#include <bit>
#include <cmath>
#include <cstddef>

namespace quantforge {
namespace {

std::uint64_t splitmix(std::uint64_t& state) {
    state += 0x9E3779B97F4A7C15ULL;
    std::uint64_t z = state;
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

template <std::size_t N>
double horner(const double (&c)[N], double r) {
    double v = c[N - 1];
    for (std::size_t i = N - 1; i-- > 0;) v = v * r + c[i];
    return v;
}

constexpr double A[] = {3.387132872796366608, 133.14166789178437745, 1971.5909503065514427, 13731.693765509461125,
                        45921.953931549871457, 67265.770927008700853, 33430.575583588128105, 2509.0809287301226727};
constexpr double B[] = {1, 42.313330701600911252, 687.18700749205790830, 5394.1960214247511077,
                        21213.794301586595867, 39307.895800092710610, 28729.085735721942674, 5226.4952788528545610};
constexpr double C[] = {1.42343711074968357734, 4.63033784615654529590, 5.76949722146069140550, 3.64784832476320460504,
                        1.27045825245236838258, 0.241780725177450611770, 0.0227238449892691845833, 0.000774545014278341407640};
constexpr double D[] = {1, 2.05319162663775882187, 1.67638483018380384940, 0.689767334985100004550,
                        0.148103976427480074590, 0.0151986665636164571966, 0.000547593808499534494600, 1.05075007164441684324e-9};
constexpr double E[] = {6.65790464350110377720, 5.46378491116411436990, 1.78482653991729133580, 0.296560571828504891230,
                        0.0265321895265761230930, 0.00124266094738807843860, 0.0000271155556874348757815, 2.01033439929228813265e-7};
constexpr double F[] = {1, 0.599832206555887937690, 0.136929880922735805310, 0.0148753612908506148525,
                        0.000786869131145613259100, 0.0000184631831751005468180, 1.42151175831644588870e-7, 2.04426310338993978564e-15};

}  // namespace

Xoshiro256::Xoshiro256(std::uint64_t seed, int stream) {
    std::uint64_t state = seed;
    for (auto& w : s_) w = splitmix(state);
    for (int i = 0; i < stream; ++i) jump();
}

std::uint64_t Xoshiro256::next() {
    const std::uint64_t result = std::rotl(s_[1] * 5, 7) * 9;
    const std::uint64_t t = s_[1] << 17;
    s_[2] ^= s_[0];
    s_[3] ^= s_[1];
    s_[1] ^= s_[2];
    s_[0] ^= s_[3];
    s_[2] ^= t;
    s_[3] = std::rotl(s_[3], 45);
    return result;
}

void Xoshiro256::jump() {
    constexpr std::uint64_t J[] = {0x180EC6D33CFD0ABAULL, 0xD5A61266F0C9392CULL, 0xA9582618E03FC9AAULL, 0x39ABDC4529B1661CULL};
    State n{};
    for (const std::uint64_t w : J) {
        for (int b = 0; b < 64; ++b) {
            if (w >> b & 1)
                for (std::size_t i = 0; i < 4; ++i) n[i] ^= s_[i];
            next();
        }
    }
    s_ = n;
}

double uniform_from_bits(std::uint64_t x) { return (double(x >> 12) + 0.5) * 0x1p-52; }
double Xoshiro256::next_uniform() { return uniform_from_bits(next()); }
double Xoshiro256::next_normal() { return ppnd16(next_uniform()); }

double ppnd16(double p) {
    const double q = p - 0.5;
    if (std::fabs(q) <= 0.425) {
        const double r = 0.180625 - q * q;
        return q * horner(A, r) / horner(B, r);
    }
    double r = q < 0 ? p : 1.0 - p;
    r = std::sqrt(-std::log(r));
    double v;
    if (r <= 5.0) {
        r -= 1.6;
        v = horner(C, r) / horner(D, r);
    } else {
        r -= 5.0;
        v = horner(E, r) / horner(F, r);
    }
    return q < 0 ? -v : v;
}

}  // namespace quantforge
