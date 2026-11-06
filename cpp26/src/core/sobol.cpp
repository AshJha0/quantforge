#include "quantforge/core/sobol.hpp"

#include <bit>
#include <string_view>

#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"

namespace quantforge {
namespace {

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wc23-extensions"
#endif
constexpr unsigned char table_bytes[] = {
#embed "../../../specifications/01-core/data/sobol-joe-kuo-d6-64.json"
};
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

using Directions = std::array<std::uint32_t, 33>;

Directions build(const json::Value& row) {
    const int s = int(row.find("s")->number);
    const auto a = std::uint32_t(row.find("a")->number);
    const auto& m = row.find("m")->items;
    Directions v{};
    if (s == 0) {
        for (std::size_t k = 1; k <= 32; ++k) v[k] = std::uint32_t{1} << (32 - k);
        return v;
    }
    const auto su = std::size_t(s);
    for (std::size_t k = 1; k <= su && k <= 32; ++k) v[k] = std::uint32_t(m[k - 1].number) << (32 - k);
    for (std::size_t k = su + 1; k <= 32; ++k) {
        std::uint32_t x = v[k - su] ^ (v[k - su] >> s);
        for (std::size_t j = 1; j < su; ++j)
            if (a >> (su - 1 - j) & 1) x ^= v[k - j];
        v[k] = x;
    }
    return v;
}

// v[k], k = 1..32, per dimension. Built once from the embedded table, and never changed.
const std::vector<Directions>& directions() {
    static const std::vector<Directions> table = [] {
        const std::string_view text(reinterpret_cast<const char*>(table_bytes), sizeof table_bytes);
        const auto doc = json::parse(text);
        std::vector<Directions> all;
        for (const auto& row : doc.value.find("dimensions")->items) all.push_back(build(row));
        return all;
    }();
    return table;
}

}  // namespace

void check_sobol_request(long long dimensions, long long count, long long skip) {
    if (dimensions < 1 || dimensions > Sobol::max_dimensions)
        throw Error("E_INPUT", "dimensions must be 1 to 64", "dimensions");
    if (count < 1) throw Error("E_INPUT", "count must be at least 1", "count");
    if (skip < 0) throw Error("E_INPUT", "skip must not be negative", "skip");
}

Sobol::Sobol(int dimensions, std::uint64_t skip) : index_(skip), x_(std::size_t(dimensions), 0) {
    const auto& all = directions();
    v_.assign(all.begin(), all.begin() + dimensions);
    // Point i is the XOR of v[k+1] over the set bits k of the Gray code of i.
    const std::uint64_t gray = skip ^ (skip >> 1);
    for (std::size_t d = 0; d < x_.size(); ++d)
        for (std::size_t k = 0; k < 32; ++k)
            if (gray >> k & 1) x_[d] ^= v_[d][k + 1];
}

void Sobol::next(double* out) {
    const auto c = std::size_t(std::countr_one(index_)) + 1;  // lowest zero bit, from 1
    for (std::size_t d = 0; d < x_.size(); ++d) {
        x_[d] ^= v_[d][c];
        out[d] = double(x_[d]) * 0x1p-32;
    }
    ++index_;
}

}  // namespace quantforge
