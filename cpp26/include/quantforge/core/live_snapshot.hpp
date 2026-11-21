// Stage K, K-5 (spec 12-platform/lock-free-snapshots.md 1.0.0, rulings KR-280 to KR-288 confirmed 2026-11-20): versioned
// immutable snapshots published by one writer to many readers through single-writer hazard pointers over a fixed
// pool (KR-280), and the real-time hedge a snapshot carries (KR-283). Latency-aware analytics on simulated data.
//
// Progress (KR-282): the writer is wait-free (one scan of R hazards); a reader is lock-free, not wait-free (it
// retries only when a publish lands between its two loads of `current`). No heap allocation after construction.
// No latency is claimed: no timing run exists.
#pragma once

#include <array>
#include <atomic>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <new>
#include <stdexcept>
#include <type_traits>
#include <vector>

#include "quantforge/core/stage_k.hpp"

namespace quantforge::live {

/// Test-only planted faults (KR-288). Production code uses `Fault::None`.
enum class Fault : std::uint8_t {
    None,
    RelaxedPublish,  // `current` stored and loaded relaxed: ThreadSanitizer must report a race on slot contents
    SkipHazardScan,  // the writer reuses the next slot without scanning hazards: ThreadSanitizer must report
};

inline constexpr std::size_t max_readers = 64;
inline constexpr std::uint32_t none_slot = 0xFFFFFFFFu;

/// Single writer, R readers (1..64), pool of R + 2 slots of a trivially copyable T (KR-280).
template <class T>
class SnapshotCell {
    static_assert(std::is_trivially_copyable_v<T>, "a snapshot is a fixed-size value");

    struct alignas(64) Slot {
        T value;
    };
    struct alignas(64) Hazard {
        std::atomic<std::uint32_t> slot{none_slot};
    };

public:
    /// Guard over one held snapshot; releases the hazard on destruction.
    class Guard {
    public:
        Guard(const Guard&) = delete;
        Guard& operator=(const Guard&) = delete;
        Guard(Guard&& o) noexcept : hazard_(o.hazard_), value_(o.value_) { o.hazard_ = nullptr; }
        Guard& operator=(Guard&&) = delete;
        ~Guard() {
            if (hazard_ != nullptr) hazard_->slot.store(none_slot, std::memory_order_release);
        }
        const T& operator*() const noexcept { return *value_; }
        const T* operator->() const noexcept { return value_; }

    private:
        friend class SnapshotCell;
        Guard(Hazard* h, const T* v) noexcept : hazard_(h), value_(v) {}
        Hazard* hazard_;
        const T* value_;
    };

    SnapshotCell(std::size_t readers, const T& initial, Fault fault = Fault::None)
        : readers_(readers), fault_(fault) {
        if (readers < 1 || readers > max_readers) throw std::invalid_argument("readers must be 1 to 64 (KR-280)");
        slots_ = std::make_unique<Slot[]>(readers + 2);
        hazards_ = std::make_unique<Hazard[]>(readers);
        slots_[0].value = initial;
        current_.store(0, std::memory_order_seq_cst);
    }

    std::size_t readers() const noexcept { return readers_; }
    std::size_t pool_size() const noexcept { return readers_ + 2; }

    /// Reader `i` takes the current snapshot (KR-280). Each reader index must be used by one thread at a time and
    /// hold at most one guard.
    Guard acquire(std::size_t reader) {
        if (reader >= readers_) throw std::out_of_range("reader index");
        Hazard& h = hazards_[reader];
        const auto load_order = relaxed() ? std::memory_order_relaxed : std::memory_order_acquire;
        const auto check_order = relaxed() ? std::memory_order_relaxed : std::memory_order_seq_cst;
        for (;;) {
            const std::uint32_t s = current_.load(load_order);
            h.slot.store(s, check_order);
            if (current_.load(check_order) == s) return Guard(&h, &slots_[s].value);
        }
    }

    /// The writer publishes a new snapshot (one writer only). Wait-free: one scan of the hazards.
    void publish(const T& next) {
        const std::uint32_t cur = current_.load(std::memory_order_relaxed);  // only the writer stores it
        const std::uint32_t f = fault_ == Fault::SkipHazardScan ? next_slot(cur) : free_slot(cur);
        slots_[f].value = next;  // plain write: no reader holds or can validate f
        current_.store(f, relaxed() ? std::memory_order_relaxed : std::memory_order_seq_cst);
    }

private:
    bool relaxed() const noexcept { return fault_ == Fault::RelaxedPublish; }

    std::uint32_t next_slot(std::uint32_t cur) const noexcept {
        return static_cast<std::uint32_t>((cur + 1u) % pool_size());
    }

    std::uint32_t free_slot(std::uint32_t cur) const {
        std::array<bool, max_readers + 2> held{};
        held[cur] = true;
        const auto order = relaxed() ? std::memory_order_relaxed : std::memory_order_seq_cst;
        for (std::size_t i = 0; i < readers_; ++i) {
            const std::uint32_t s = hazards_[i].slot.load(order);
            if (s != none_slot) held[s] = true;
        }
        for (std::uint32_t k = 0; k < pool_size(); ++k) {
            if (!held[k]) return k;
        }
        throw std::logic_error("no free slot: impossible with R + 2 slots (pigeonhole)");
    }

    std::size_t readers_;
    Fault fault_;
    std::unique_ptr<Slot[]> slots_;
    std::unique_ptr<Hazard[]> hazards_;
    alignas(64) std::atomic<std::uint32_t> current_{0};
};

// ---- the hedge snapshot (KR-283, KR-287) ----

inline constexpr std::uint64_t check_seed = 0x9E3779B97F4A7C15ull;
inline constexpr std::uint64_t check_mul = 0x94D049BB133111EBull;

/// KR-287: c = rotl64(c xor w, 27) * MUL mod 2^64 from SEED.
inline std::uint64_t checksum(const std::uint64_t* words, std::size_t n) noexcept {
    std::uint64_t c = check_seed;
    for (std::size_t i = 0; i < n; ++i) c = std::rotl(c ^ words[i], 27) * check_mul;
    return c;
}

struct HedgeSnapshot {
    std::uint64_t version, as_of;
    double shift, estimate_pnl, bound, book_delta, hedge_unit_delta, hedge_notional;
    std::uint64_t check;

    std::array<std::uint64_t, 8> words() const noexcept {
        return {version,
                as_of,
                std::bit_cast<std::uint64_t>(shift),
                std::bit_cast<std::uint64_t>(estimate_pnl),
                std::bit_cast<std::uint64_t>(bound),
                std::bit_cast<std::uint64_t>(book_delta),
                std::bit_cast<std::uint64_t>(hedge_unit_delta),
                std::bit_cast<std::uint64_t>(hedge_notional)};
    }
    /// The reader's torn-read test.
    bool intact() const noexcept {
        const auto w = words();
        return checksum(w.data(), w.size()) == check;
    }
};

struct HedgeInstrument {
    double maturity, yield;
};

/// fsum(-T * (N * exp(-(y + h) * T))): the book's parallel delta at the shifted yields (KR-283).
double book_delta(const std::vector<stage_k::ZeroPosition>& positions, double shift);
/// -T_H * exp(-(y_H + h) * T_H): the delta of one unit of the hedge zero (KR-283).
double hedge_unit_delta(const HedgeInstrument& hedge, double shift);
/// The writer's per-publish computation: direct library calls only (KR-283, KR-284).
HedgeSnapshot build(std::uint64_t version, std::uint64_t as_of, const std::vector<stage_k::ZeroPosition>& positions,
                    const HedgeInstrument& hedge, double shift);
/// KR-287: 0 for version 0, else ((k * 7919) mod 401 - 200) * 5e-5.
double scenario_shift(std::uint64_t k);

}  // namespace quantforge::live
