#pragma once
// Stage H wave 2: micro.book.rebuild (specifications/09-microstructure/order-book.md, HR-11 to HR-17) and
// exec.sim.lit.run (specifications/10-execution/lit-matching.md, HR-25 to HR-31). Prices, quantities and fees
// are exact decimals (ExactDecimal, HR-12); outputs are written with sorted keys (HR-29).
#include <cstdint>
#include <string_view>

#include "quantforge/core/json.hpp"

namespace quantforge::micro {

inline constexpr long long max_book_messages = 50'000'000;  // HR-17
inline constexpr long long max_lit_events = 10'000'000;
inline constexpr std::size_t max_book_events = 10'000;
inline constexpr std::string_view lit_label = "simulated venue; not a real exchange";

/// IEEE 802.3 CRC32 (zlib.crc32), as [KR-CRC] is inferred to use.
std::uint32_t crc32(std::string_view bytes);

/// MBP rebuild. `messages` must be an array; `checkpoints` may be null. Writes the output members
/// (book, checksum_string when asked, crc32, events, events_omitted when non-zero, stats) into `out`.
void book_rebuild(const json::Value& messages, long long depth, long long price_decimals, long long qty_decimals,
                  const json::Value* checkpoints, bool emit_checksum_string, json::Writer& out);

/// The simulated lit engine. `events` must be an array, `fee_schedule` an object. Writes book, cancelled,
/// conservation, fees, fills, label, mbp and rejects into `out`.
void lit_run(std::string_view tick_size, std::string_view lot_size, const json::Value& events,
             const json::Value& fee_schedule, json::Writer& out);

}  // namespace quantforge::micro
