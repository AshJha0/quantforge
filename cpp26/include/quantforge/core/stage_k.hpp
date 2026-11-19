#pragma once
// Stage K wave 1 (PROPOSED rulings KR-1 to KR-14, specifications/stage-k-rulings-w1.md): the bitemporal store
// query (01-core/bitemporal-store.md), the sequential par bootstrap and its incremental update
// (02-curves/incremental-update.md), recalibration triggers (03-calibration/recalibration-triggers.md), intraday
// delta-gamma risk with a Lagrange bound (06-risk/intraday-risk-bounds.md) and the Richardson guard
// (06-risk/bermudan-ladder-k8.md, `num.richardson.check`). A port of the Python build's stage_k.py, matching the
// Java build bit for bit where the spec fixes the arithmetic (left-to-right bootstrap sum, correctly rounded sums).
//
// Error order (HR-66): the CLI raises E_SCHEMA, then the structural E_INPUT (the check_*_shape functions and
// check_log), then a non-finite input (F-2); each function here then raises its E_DOMAIN checks, the
// value-dependent E_INPUT and the stage K size limit (E_LIMIT), last.
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace quantforge::stage_k {

inline constexpr std::string_view label = "latency-aware analytics on simulated data";  // KR-10
inline constexpr std::size_t max_records = 1'000'000;
inline constexpr std::size_t max_quotes = 200;
inline constexpr std::size_t max_changes = 100'000;
inline constexpr std::size_t max_positions = 100'000;

// ---- bitemporal store (KR-2, KR-3, KR-14) ----

/// One bitemporal record; instants are whole seconds since the epoch, no valid_to is an open interval. The value
/// stays with the caller: a query answers with the index of the winning record.
struct BiRecord {
    long long sequence;
    std::string series_id;
    std::int64_t valid_from;
    std::optional<std::int64_t> valid_to;
    std::int64_t knowledge_time;
    bool deleted;
};

enum class BiStatus { Found, Withdrawn, None };

struct BiAnswer {
    BiStatus status;
    std::optional<std::size_t> winner;  // index into the log when FOUND
};

std::string_view status_name(BiStatus s);

/// Log checks 2 to 4 (structural E_INPUT) in the spec's order: sequence strictly increasing, knowledge time
/// never going back, valid_to after valid_from.
void check_log(const std::vector<BiRecord>& records);

/// `core.store.bitemporal_query`: the record with the highest sequence among those known by K (inclusive) whose
/// valid interval holds V. A deleted winner is WITHDRAWN: it masks every older record.
BiAnswer bitemporal_query(const std::vector<BiRecord>& records, std::string_view series_id,
                          std::int64_t knowledge_as_of, std::int64_t valid_at);

// ---- par bootstrap and incremental update (KR-5) ----

void check_quotes_shape(std::size_t n);

/// `curve.bootstrap.par_annual`: discount factors of annual par swaps with accrual 1,
/// P_k = (1 - S_k sum_(i<k) P_i) / (1 + S_k), the running sum taken left to right.
std::vector<double> par_annual(const std::vector<double>& quotes);

void check_update_shape(std::size_t n_previous, std::size_t n_dfs, std::size_t n_new);

struct Update {
    std::vector<double> discount_factors;
    std::optional<std::size_t> first_changed_index;
    std::size_t recomputed;
};

/// `curve.incremental.update`: copies the pillars before the first changed quote and solves the rest. The cache
/// must be the bootstrap of previous_quotes bit for bit, sign of zero included (E_INPUT otherwise).
Update incremental_update(const std::vector<double>& previous_quotes, const std::vector<double>& previous_dfs,
                          const std::vector<double>& new_quotes);

// ---- recalibration trigger (KR-6, KR-13) ----

void check_changes_shape(std::size_t n);

struct Trigger {
    bool fire;
    double sigma, threshold, false_alarm_rate;
};

/// `calib.trigger.check`: fires iff |x_now - x_ref| > k sigma sqrt(d), strictly; sigma is the sample standard
/// deviation with correctly rounded sums; the false-alarm rate is erfc(k / sqrt 2).
Trigger trigger_check(const std::vector<double>& changes, double x_ref, double x_now, double days_since, double k);

// ---- intraday delta-gamma with a Lagrange bound (KR-7, KR-10, KR-12) ----

struct ZeroPosition {
    double notional, maturity, yield;
};

void check_positions_shape(std::size_t n);

/// |h|^3 M3 / 6 with M3 = T^3 |N| exp(-T min(y, y + h)).
double position_bound(const ZeroPosition& p, double shift);
/// V' h + V'' h^2 / 2 with V = N exp(-y T).
double position_estimate(const ZeroPosition& p, double shift);

struct Intraday {
    double estimate_pnl, bound;
};

/// `risk.intraday.delta_gamma_bound`: correctly rounded sums of the per-position estimates and bounds (no
/// netting of the bounds).
Intraday delta_gamma_bound(const std::vector<ZeroPosition>& positions, double shift);

/// Full revaluation sum N exp(-y T) expm1(-h T); a test helper, not an operation.
double zero_revalue(const std::vector<ZeroPosition>& positions, double shift);

// ---- Richardson guard (KR-9, KR-12) ----

void check_values_shape(std::size_t n);

enum class RichStatus { Ok, OrderMismatch, NonMonotone };

struct Richardson {
    RichStatus status;
    std::optional<double> observed_order, extrapolated;
};

std::string_view status_name(RichStatus s);

/// `num.richardson.check`: extrapolates only when the two differences keep one sign and the observed order is
/// within 0.5 of the assumed order.
Richardson richardson_check(const std::vector<double>& values, double ratio, double assumed_order);

}  // namespace quantforge::stage_k
