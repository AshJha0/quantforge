#include "quantforge/core/snapshot.hpp"

#include <algorithm>
#include <bit>
#include <cstdio>
#include <cstring>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"

namespace quantforge {
namespace {

constexpr std::uint32_t k[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

void block(std::uint32_t h[8], const std::uint8_t* p) {
    std::uint32_t w[64];
    for (int i = 0; i < 16; ++i)
        w[i] = std::uint32_t(p[4 * i]) << 24 | std::uint32_t(p[4 * i + 1]) << 16 | std::uint32_t(p[4 * i + 2]) << 8 |
               std::uint32_t(p[4 * i + 3]);
    for (int i = 16; i < 64; ++i) {
        const std::uint32_t s0 = std::rotr(w[i - 15], 7) ^ std::rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
        const std::uint32_t s1 = std::rotr(w[i - 2], 17) ^ std::rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    std::uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; ++i) {
        const std::uint32_t s1 = std::rotr(e, 6) ^ std::rotr(e, 11) ^ std::rotr(e, 25);
        const std::uint32_t t1 = hh + s1 + ((e & f) ^ (~e & g)) + k[i] + w[i];
        const std::uint32_t s0 = std::rotr(a, 2) ^ std::rotr(a, 13) ^ std::rotr(a, 22);
        const std::uint32_t t2 = s0 + ((a & b) ^ (a & c) ^ (b & c));
        hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
}

void canon(std::string& out, const json::Value& v, bool top) {
    using json::Kind;
    switch (v.kind) {
        case Kind::Null: out += "null"; break;
        case Kind::Bool: out += v.boolean ? "true" : "false"; break;
        case Kind::Number: {
            const double d = v.number == 0.0 ? 0.0 : v.number;  // -0 is written as +0
            char b[24];
            std::snprintf(b, sizeof b, "#%016llx", static_cast<unsigned long long>(std::bit_cast<std::uint64_t>(d)));
            out += b;
            break;
        }
        // The JSON writer's escapes are the canonical ones: ", \ and U+0000 to U+001F only.
        case Kind::String: json::append_string(out, v.text); break;
        case Kind::Array: {
            out += '[';
            bool first = true;
            for (const auto& item : v.items) {
                if (!first) out += ',';
                first = false;
                canon(out, item, false);
            }
            out += ']';
            break;
        }
        case Kind::Object: {
            std::vector<const json::Member*> members;
            for (const auto& m : v.members)
                if (!(top && m.first == "snapshot_id")) members.push_back(&m);
            std::ranges::sort(members, [](const auto* a, const auto* b) {
                return std::ranges::lexicographical_compare(a->first, b->first, [](char x, char y) {
                    return static_cast<unsigned char>(x) < static_cast<unsigned char>(y);
                });
            });
            out += '{';
            bool first = true;
            for (const auto* m : members) {
                if (!first) out += ',';
                first = false;
                json::append_string(out, m->first);
                out += ':';
                canon(out, m->second, false);
            }
            out += '}';
            break;
        }
    }
}

}  // namespace

std::array<std::uint8_t, 32> sha256(std::string_view bytes) {
    std::uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    const auto* p = reinterpret_cast<const std::uint8_t*>(bytes.data());
    std::size_t left = bytes.size();
    for (; left >= 64; left -= 64, p += 64) block(h, p);
    std::uint8_t tail[128] = {};
    if (left) std::memcpy(tail, p, left);
    tail[left] = 0x80;
    const std::size_t total = left < 56 ? 64 : 128;
    const std::uint64_t bits = std::uint64_t(bytes.size()) * 8;
    for (std::size_t i = 0; i < 8; ++i) tail[total - 1 - i] = std::uint8_t(bits >> (8 * i));
    block(h, tail);
    if (total == 128) block(h, tail + 64);
    std::array<std::uint8_t, 32> out{};
    for (std::size_t i = 0; i < 8; ++i)
        for (std::size_t j = 0; j < 4; ++j) out[4 * i + j] = std::uint8_t(h[i] >> (24 - 8 * j));
    return out;
}

SnapshotHash snapshot_hash(std::string_view text) {
    const json::Parsed parsed = json::parse(text);
    if (parsed.duplicate_key) throw Error("E_PARSE", "duplicate key");
    if (parsed.number_overflow) throw Error("E_SCHEMA", "a number overflows binary64");
    if (parsed.lone_surrogate) throw Error("E_SCHEMA", "lone surrogate escape");
    if (parsed.value.kind != json::Kind::Object) throw Error("E_SCHEMA", "the top level must be an object");
    return snapshot_of(parsed.value);
}

std::string sha256_hex(std::string_view bytes) {
    std::string out;
    char b[3];
    for (const std::uint8_t byte : sha256(bytes)) {
        std::snprintf(b, sizeof b, "%02x", unsigned(byte));
        out += b;
    }
    return out;
}

std::string canonical_form(const json::Value& v) {
    std::string out;
    canon(out, v, false);
    return out;
}

SnapshotHash snapshot_of(const json::Value& document) {
    SnapshotHash r;
    canon(r.canonical, document, true);
    r.snapshot_id = "sha256:" + sha256_hex(r.canonical);
    return r;
}

}  // namespace quantforge
