#pragma once
// Stage H wave 2: micro.book.rebuild (specifications/09-microstructure/order-book.md, HR-11 to HR-17) and
// exec.sim.lit.run (specifications/10-execution/lit-matching.md, HR-25 to HR-31). Prices, quantities and fees
// are exact decimals (ExactDecimal, HR-12); outputs are written with sorted keys (HR-29).
#include <cstdint>
#include <string>
#include <utility>
#include <vector>
#include <string_view>

#include "quantforge/core/exact_decimal.hpp"
#include "quantforge/core/json.hpp"

namespace quantforge::micro {

inline constexpr long long max_book_messages = 50'000'000;  // HR-17
inline constexpr long long max_lit_events = 10'000'000;
inline constexpr std::size_t max_book_events = 10'000;
inline constexpr std::string_view lit_label = "simulated venue; not a real exchange";
inline constexpr long long max_dark_events = 10'000'000;
inline constexpr std::string_view dark_label = "simulated venue; not a real dark pool";
inline constexpr std::string_view sor_label = "simulated venues; router scored in simulation only";

/// IEEE 802.3 CRC32 (zlib.crc32), as [KR-CRC] is inferred to use.
std::uint32_t crc32(std::string_view bytes);

/// MBP rebuild. `messages` must be an array; `checkpoints` may be null. Writes the output members
/// (book, checksum_string when asked, crc32, events, events_omitted when non-zero, stats) into `out`.
void book_rebuild(const json::Value& messages, long long depth, long long price_decimals, long long qty_decimals,
                  const json::Value* checkpoints, bool emit_checksum_string, json::Writer& out);

/// The simulated lit engine. `events` must be an array, `fee_schedule` an object. Writes book, cancelled,
/// conservation, fees, fills, label, mbp and rejects into `out`.
/// With `session` (an object: phase, ref_price, tie_break; HR-83) the run also takes PHASE events and writes
/// auctions and phase (asset-conventions.md 1.3, auction.md); `fee_schedule/auction_fee` prices auction fills.
void lit_run(std::string_view tick_size, std::string_view lot_size, const json::Value& events,
             const json::Value& fee_schedule, json::Writer& out, const json::Value* session = nullptr);

/// exec.sim.dark.run (specifications/10-execution/dark-pool.md, HR-32 to HR-36): one pool run; writes fills,
/// invitations, label, resting and suspensions into `out`.
void dark_run(const json::Value& config, const json::Value& events, json::Writer& out);

/// exec.sim.dark.markouts: bp markouts per horizon, rounded half-even to 6 decimals; writes `fills`.
void dark_markouts(const json::Value& fills, json::Writer& out);

/// exec.sor.allocate (specifications/10-execution/smart-order-router.md, HR-37 to HR-40), [CK] eq. 5 with the
/// dark extension; exact expectations. Writes L, M, expected_cost, expected_fill, p_underfill (and the extras).
void sor_allocate(const json::Value& inputs, json::Writer& out);

/// Kaplan-Meier tail T(s) = P(liquidity >= s), s = 1..s_max, from (v, r) observations ([GKNV09] section 2),
/// with its Greenwood standard error; plain KM, no optimistic modification.
std::vector<std::pair<double, double>> km_tail(const std::vector<std::pair<long long, long long>>& obs, int s_max);

/// num / den rounded half-even to `places` decimals, exact (long division), trailing zeros removed.
std::string div_round(ExactDecimal num, ExactDecimal den, int places);

}  // namespace quantforge::micro
