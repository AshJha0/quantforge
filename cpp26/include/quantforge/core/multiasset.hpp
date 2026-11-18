#pragma once
// Stage H multi-asset microstructure: equities (H-22), FX spot (H-23) and rates (H-24).
// Specs: specifications/09-microstructure/asset-conventions.md, 10-execution/auction.md, fx-rfq-venue.md and
// rates-futures-venue.md; rulings specifications/stage-h-rulings-multiasset.md (HR-80 to HR-108 and the dated
// rule versions of 2026-11-18). A port of python/quantforge_core/multiasset.py: decimal strings in and out
// (HR-12), exact arithmetic (HR-57, HR-58), error order HR-66, every output labelled (HR-94).
// The micro.* convention operations carry no label (HR-111); the venue operations do (HR-94).
// Each function reads the case `inputs` object and writes its outputs, keys sorted, into `out`.
#include <string_view>

#include "quantforge/core/json.hpp"

namespace quantforge::micro::ma {

inline constexpr std::string_view eq_label = "simulated venue; not a real exchange";
inline constexpr std::string_view iex_label = "IEX only; one venue";
inline constexpr std::string_view fx_label = "simulated venue; not a real exchange; no real FX data";
inline constexpr std::string_view rates_label = "simulated venue; not a real exchange; no real rates data";
/// Dated rule versions: the 2024-amended Rule 612/610 and round-lot text applies on and after this date
/// (a parameter, `compliance_date`). Default: the first business day of November 2025, adopting release
/// 34-101070 section VI (HR-110); any later SEC extension is UNVERIFIED.
inline constexpr std::string_view rule_2024_compliance = "2025-11-03";
inline constexpr long long max_auction_orders = 10'000'000;
inline constexpr long long max_auction_candidates = 1'000'000;
inline constexpr int max_calendar_days = 3660;

using json::Value;
using json::Writer;

void eq_round_price(const Value& in, Writer& out);   // micro.eq.round_price (HR-81)
void eq_fee_check(const Value& in, Writer& out);     // micro.eq.fee_check (HR-85)
void eq_round_lot(const Value& in, Writer& out);     // micro.eq.round_lot (HR-82, dated)
void eq_settle_date(const Value& in, Writer& out);   // micro.eq.settle_date (HR-86)
void auction_uncross(const Value& in, Writer& out);  // exec.sim.auction.uncross (HR-84, HR-96, HR-101)
void fx_pip_value(const Value& in, Writer& out);     // micro.fx.pip_value (HR-87)
void fx_spot_date(const Value& in, Writer& out);     // micro.fx.spot_date (HR-89)
void fx_stream(const Value& in, Writer& out);        // exec.sim.fx.stream
void fx_request(const Value& in, Writer& out);       // exec.sim.fx.request (HR-97)
void rates_parse_32nds(const Value& in, Writer& out);   // micro.rates.parse_32nds (HR-90)
void rates_format_32nds(const Value& in, Writer& out);  // micro.rates.format_32nds (HR-90)
void rates_tick_value(const Value& in, Writer& out);    // micro.rates.tick_value (HR-91)
void rates_bond_price(const Value& in, Writer& out);    // micro.rates.bond_price (HR-92)
void rates_bond_yield(const Value& in, Writer& out);    // micro.rates.bond_yield (HR-92): Brent, 1e-12, binary64
void rates_bill_price(const Value& in, Writer& out);    // micro.rates.bill_price ([UST-BILL])
void fut_to_ticks(const Value& in, Writer& out);        // exec.sim.fut.to_ticks
void fut_to_text(const Value& in, Writer& out);         // exec.sim.fut.to_text
void fut_pnl(const Value& in, Writer& out);             // exec.sim.fut.pnl (HR-102)
void fut_variation(const Value& in, Writer& out);       // exec.sim.fut.variation (HR-103)
void fut_run(const Value& in, Writer& out);             // exec.sim.fut.run: the lit engine unchanged

}  // namespace quantforge::micro::ma
