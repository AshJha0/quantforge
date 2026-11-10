#pragma once
#include <array>
#include <cstdint>
#include <string>
#include <string_view>

#include "quantforge/core/json.hpp"

namespace quantforge {

struct SnapshotHash {
    std::string canonical;
    std::string snapshot_id;
};

std::array<std::uint8_t, 32> sha256(std::string_view bytes);
std::string sha256_hex(std::string_view bytes);
/// No double inputs: json numbers are hashed by their spelling, so the finite rule does not apply here.
/// Canonical bytes of a value, with nothing excluded.
std::string canonical_form(const json::Value& v);
/// Canonical form and id of a parsed document; a top-level snapshot_id is left out.
SnapshotHash snapshot_of(const json::Value& document);
SnapshotHash snapshot_hash(std::string_view document_text);

}  // namespace quantforge
