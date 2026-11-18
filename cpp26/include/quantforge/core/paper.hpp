#pragma once
// Stage H item H-21: paper trading with simulated fills (specifications/10-execution/paper-trading.md, rulings
// HR-42 to HR-55, cli-contract.md "Stage H paper trading operations"). A port of the Python reference
// (quantforge_core/paper.py and paper_fills.py), which it follows step for step:
//  - decimals follow Python's decimal module in its default context (28 significant digits, half-even after every
//    operation), so every value and every ledger hash matches byte for byte;
//  - the ledger's canonical bytes are Python json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True);
//  - TCA runs in binary64 in the contract's order (this file is built with -ffp-contract=off, as is the project).
// Nothing here opens a socket or names an order-entry endpoint: an order whose mode is not "simulated" is
// E_UNSUPPORTED_OPERATION (HR-42). Fills come from this build's lit engine, dark pool and router only.
#include <optional>
#include <string>
#include <string_view>

#include "quantforge/core/json.hpp"

namespace quantforge::paper {

inline constexpr std::string_view label = "crypto venue; simulated";
inline constexpr std::string_view ceiling =
    "Paper trading on free data; simulated fills; no evidence of tradable profitability.";
inline constexpr std::string_view genesis = "0000000000000000000000000000000000000000000000000000000000000000";

/// The canonical bytes of a record without its `hash` key (HR-45). E_INPUT for a boolean or a number anywhere other
/// than an integer top-level `seq`.
std::string canonical(const json::Value& record);

/// A JSON string as Python json.dumps(..., ensure_ascii=True) writes it (quotes included).
std::string ascii_string(std::string_view utf8);

/// The verify object of `paper.ledger.verify`.
struct Verify {
    bool ok = true;
    long long records = 0;
    std::optional<long long> first_bad_seq;
    std::string reason;  // empty when ok
    std::string head;    // empty unless ok
};
Verify verify(std::string_view text);

/// The six CLI operations: `inputs` is the case's inputs object; members are written into `out`.
void book_apply_fill(const json::Value& inputs, json::Writer& out);
void book_end_of_day(const json::Value& inputs, json::Writer& out);
void pretrade_check(const json::Value& inputs, json::Writer& out);
void ledger_append(const json::Value& inputs, json::Writer& out);
void ledger_verify(const json::Value& inputs, json::Writer& out);
void session_run(const json::Value& inputs, json::Writer& out);

}  // namespace quantforge::paper
