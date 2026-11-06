#pragma once
#include <array>
#include <cstdint>
#include <string>
#include <string_view>

namespace quantforge {

struct SnapshotHash {
    std::string canonical;
    std::string snapshot_id;
};

std::array<std::uint8_t, 32> sha256(std::string_view bytes);
SnapshotHash snapshot_hash(std::string_view document_text);

}  // namespace quantforge
