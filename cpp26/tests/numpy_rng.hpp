#pragma once
// A port of numpy.random.default_rng(seed) for integer seeds below 2^32: SeedSequence, PCG64 (XSL-RR 128/64) and
// the Generator draws the micro-estimator recovery tests use (HR-71 ties the spec's seeds to this generator).
// A C++ copy of the Java lane's port (java25/src/test/java/org/quantforge/micro/NumpyRng.java), itself ported from
// numpy's bit_generator.pyx, pcg64.h and distributions.c. Checked draw by draw against numpy in test_micro_est.cpp.
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <span>
#include <stdexcept>

#include "numpy_ziggurat_tables.hpp"

namespace quantforge::test {

class NumpyRng {
public:
    explicit NumpyRng(long long seed) {
        if (seed < 0 || seed > 0xFFFFFFFFLL) throw std::invalid_argument("seed must fit in 32 bits");
        const auto w = seed_sequence(static_cast<std::uint32_t>(seed));
        // pcg_setseq_128_srandom_r: inc = (initseq << 1) | 1; state = 0; step; state += initstate; step
        const U128 initstate = (U128(w[0]) << 64) | w[1];
        const U128 initseq = (U128(w[2]) << 64) | w[3];
        inc_ = (initseq << 1) | 1U;
        state_ = 0;
        step();
        state_ += initstate;
        step();
    }

    /// SeedSequence(seed).generate_state(4, uint64) for a one-word entropy and a pool of 4 words.
    static std::array<std::uint64_t, 4> seed_sequence(std::uint32_t seed) {
        std::uint32_t hc = 0x43b0d7e5U;
        const auto hashmix = [&hc](std::uint32_t value) {
            std::uint32_t v = value ^ hc;
            hc *= 0x931e8875U;
            v *= hc;
            return v ^ (v >> 16);
        };
        const auto mix = [](std::uint32_t x, std::uint32_t y) {
            const std::uint32_t r = 0xca01f9ddU * x - 0x4973f715U * y;
            return r ^ (r >> 16);
        };
        std::array<std::uint32_t, 4> mixer{};
        for (int i = 0; i < 4; ++i) mixer[i] = hashmix(i == 0 ? seed : 0U);
        for (int src = 0; src < 4; ++src)
            for (int dst = 0; dst < 4; ++dst)
                if (src != dst) mixer[dst] = mix(mixer[dst], hashmix(mixer[src]));
        std::uint32_t h = 0x8b51f9ddU;
        std::array<std::uint64_t, 4> out{};
        for (int i = 0; i < 8; ++i) {
            std::uint32_t v = mixer[i % 4];
            v ^= h;
            h *= 0x58f38dedU;
            v *= h;
            v ^= v >> 16;
            out[i / 2] |= (i % 2 == 0) ? std::uint64_t(v) : std::uint64_t(v) << 32;
        }
        return out;
    }

    /// bit_generator.random_raw().
    std::uint64_t next_u64() {
        step();
        const auto hi = static_cast<std::uint64_t>(state_ >> 64);
        const auto lo = static_cast<std::uint64_t>(state_);
        return std::rotr(hi ^ lo, static_cast<int>(hi >> 58));
    }

    /// numpy's buffered 32-bit draw: low half of a fresh 64-bit draw, then its high half.
    std::uint32_t next_u32() {
        if (has_u32_) {
            has_u32_ = false;
            return u32_;
        }
        const std::uint64_t n = next_u64();
        has_u32_ = true;
        u32_ = static_cast<std::uint32_t>(n >> 32);
        return static_cast<std::uint32_t>(n);
    }

    /// random(): 53 random bits over 2^53.
    double random() { return static_cast<double>(next_u64() >> 11) * (1.0 / 9007199254740992.0); }

    /// integers(low, high) with high - low at most 2^32 - 1: Lemire's method on buffered 32-bit draws.
    long long integers(long long low, long long high) {
        const auto rng = static_cast<std::uint64_t>(high - low - 1);
        if (rng == 0) return low;
        const std::uint64_t excl = rng + 1;
        std::uint64_t m = std::uint64_t(next_u32()) * excl;
        std::uint64_t left = m & 0xFFFFFFFFULL;
        if (left < excl) {
            const std::uint64_t threshold = (0xFFFFFFFFULL - rng) % excl;
            while (left < threshold) {
                m = std::uint64_t(next_u32()) * excl;
                left = m & 0xFFFFFFFFULL;
            }
        }
        return low + static_cast<long long>(m >> 32);
    }

    /// choice(values) with replacement and no weights: values[integers(0, n)].
    long long choice(std::span<const long long> values) {
        return values[static_cast<std::size_t>(integers(0, static_cast<long long>(values.size())))];
    }

    double normal(double loc, double scale) { return loc + scale * standard_normal(); }
    double exponential(double scale) { return scale * standard_exponential(); }

    double standard_normal() {
        namespace t = numpy_tables;
        for (;;) {
            std::uint64_t r = next_u64();
            const auto idx = static_cast<std::size_t>(r & 0xff);
            r >>= 8;
            const std::uint64_t rabs = (r >> 1) & 0x000fffffffffffffULL;
            const double x = static_cast<double>(rabs) * t::wi_double[idx] * ((r & 1) != 0 ? -1.0 : 1.0);
            if (rabs < t::ki_double[idx]) return x;
            if (idx == 0) {
                for (;;) {
                    const double xx = -nor_inv_r * std::log1p(-random());
                    const double yy = -std::log1p(-random());
                    if (yy + yy > xx * xx) return ((rabs >> 8) & 1) != 0 ? -(nor_r + xx) : nor_r + xx;
                }
            }
            if ((t::fi_double[idx - 1] - t::fi_double[idx]) * random() + t::fi_double[idx] < std::exp(-0.5 * x * x))
                return x;
        }
    }

    double standard_exponential() {
        namespace t = numpy_tables;
        for (;;) {
            std::uint64_t ri = next_u64() >> 3;
            const auto idx = static_cast<std::size_t>(ri & 0xff);
            ri >>= 8;
            const double x = static_cast<double>(ri) * t::we_double[idx];
            if (ri < t::ke_double[idx]) return x;
            if (idx == 0) return exp_r - std::log1p(-random());
            if ((t::fe_double[idx - 1] - t::fe_double[idx]) * random() + t::fe_double[idx] < std::exp(-x)) return x;
        }
    }

    /// poisson(lam) for lam at least 10 (PTRS, Hormann 1993), the only branch the tests reach.
    long long poisson(double lam) {
        if (lam < 10) throw std::invalid_argument("only the PTRS branch (lam >= 10) is ported");
        const double slam = std::sqrt(lam);
        const double loglam = std::log(lam);
        const double b = 0.931 + 2.53 * slam;
        const double a = -0.059 + 0.02483 * b;
        const double invalpha = 1.1239 + 1.1328 / (b - 3.4);
        const double vr = 0.9277 - 3.6224 / (b - 2);
        for (;;) {
            const double u = random() - 0.5;
            const double v = random();
            const double us = 0.5 - std::fabs(u);
            const auto k = static_cast<long long>(std::floor((2 * a / us + b) * u + lam + 0.43));
            if (us >= 0.07 && v <= vr) return k;
            if (k < 0 || (us < 0.013 && v > us)) continue;
            if (std::log(v) + std::log(invalpha) - std::log(a / (us * us) + b) <=
                -lam + static_cast<double>(k) * loglam - loggam(static_cast<double>(k) + 1.0))
                return k;
        }
    }

    static double loggam(double x) {
        static constexpr double lg[] = {8.333333333333333e-02,  -2.777777777777778e-03, 7.936507936507937e-04,
                                        -5.952380952380952e-04, 8.417508417508418e-04,  -1.917526917526918e-03,
                                        6.410256410256410e-03,  -2.955065359477124e-02, 1.796443723688307e-01,
                                        -1.39243221690590e+00};
        if (x == 1.0 || x == 2.0) return 0.0;
        const long long n = x < 7.0 ? static_cast<long long>(7 - x) : 0;
        double x0 = x + static_cast<double>(n);
        const double x2 = (1.0 / x0) * (1.0 / x0);
        double gl0 = lg[9];
        for (int k = 8; k >= 0; --k) {
            gl0 *= x2;
            gl0 += lg[k];
        }
        double gl = gl0 / x0 + 0.5 * 1.8378770664093453e+00 + (x0 - 0.5) * std::log(x0) - x0;
        for (long long k = 1; k <= n; ++k) {
            gl -= std::log(x0 - 1.0);
            x0 -= 1.0;
        }
        return gl;
    }

private:
    __extension__ using U128 = unsigned __int128;
    static constexpr U128 mul = (U128(0x2360ED051FC65DA4ULL) << 64) | 0x4385DF649FCCF645ULL;
    static constexpr double nor_r = 3.6541528853610087963519472518;
    static constexpr double nor_inv_r = 0.27366123732975827203338247596;
    static constexpr double exp_r = 7.6971174701310497140446280481;

    void step() { state_ = state_ * mul + inc_; }

    U128 state_ = 0;
    U128 inc_ = 0;
    bool has_u32_ = false;
    std::uint32_t u32_ = 0;
};

}  // namespace quantforge::test
