// Stage C and D operations through the CLI layer, against golden expectations
// (tests/cli_cases_cd.inc). This reaches the argument handling in src/cli/ops_*.inc.
#include <catch2/catch_test_macros.hpp>
#include <algorithm>
#include <cmath>
#include <string>
#include <string_view>

#include "dispatch.hpp"
#include "quantforge/core/json.hpp"

namespace {

struct Row {
    std::string_view input, status, outputs;
    double abs_tol, rel_tol;
};
constexpr Row rows[] = {
#include "cli_cases_cd.inc"
};

using quantforge::json::Kind;
using quantforge::json::Value;

// Empty when equal within tolerance; otherwise the path of the first difference.
std::string diff(const Value& got, const Value& want, double a, double r, const std::string& path) {
    if (want.kind == Kind::Number) {
        if (got.kind != Kind::Number) return path;
        // The runner's rule: |got - want| <= abs + rel * max(|got|, |want|).
        const double tol = a + r * std::max(std::fabs(got.number), std::fabs(want.number));
        return std::fabs(got.number - want.number) <= tol ? "" : path;
    }
    if (got.kind != want.kind) return path;
    switch (want.kind) {
    case Kind::Array:
        if (got.items.size() != want.items.size()) return path + "[size]";
        for (std::size_t i = 0; i < want.items.size(); ++i)
            if (auto d = diff(got.items[i], want.items[i], a, r, path + "[" + std::to_string(i) + "]"); !d.empty())
                return d;
        return "";
    case Kind::Object:
        for (const auto& [k, v] : want.members) {
            const Value* g = got.find(k);
            if (!g) return path + "." + k + "(missing)";
            if (auto d = diff(*g, v, a, r, path + "." + k); !d.empty()) return d;
        }
        return "";
    case Kind::String: return got.text == want.text ? "" : path;
    case Kind::Bool: return got.boolean == want.boolean ? "" : path;
    default: return "";
    }
}

}  // namespace

TEST_CASE("stage C and D operations match their goldens through the CLI layer") {
    for (const Row& row : rows) {
        const auto result = quantforge::cli::run_case(row.input);
        const auto parsed = quantforge::json::parse(result.json);
        const Value& v = parsed.value;
        const Value* id = v.find("case_id");
        REQUIRE(id);
        INFO(id->text);
        if (row.status == "ok") {
            REQUIRE(result.ok);
            const auto want = quantforge::json::parse(row.outputs);
            const Value* out = v.find("outputs");
            REQUIRE(out);
            CHECK(diff(*out, want.value, row.abs_tol, row.rel_tol, "outputs") == "");
        } else {
            CHECK_FALSE(result.ok);
            const Value* err = v.find("error");
            REQUIRE(err);
            CHECK(err->find("code")->text == row.status);
        }
    }
}

TEST_CASE("credit operations need a LOG_LINEAR_DF discount curve (ruling R1-4)") {
    const auto r = quantforge::cli::run_case(
        R"({"schema_version":"1.0","case_id":"x","operation":"credit.cds.bootstrap","inputs":{"trade_date":"2026-11-06",)"
        R"("discount":{"as_of":"2026-11-06","interpolation":"LINEAR_ZERO","pillars":[{"date":"2031-11-06","discount_factor":0.85}]},)"
        R"("recovery":-1,"quotes":[{"tenor":"5Y","spread":0.01}]}})");
    CHECK_FALSE(r.ok);
    CHECK(r.json.find(R"("code":"E_INPUT")") != std::string::npos);  // before the recovery rule
}
