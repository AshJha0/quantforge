#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <string>

#include "quantforge/core/compounding.hpp"
#include "quantforge/core/data_checks.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/rng.hpp"
#include "quantforge/core/snapshot.hpp"
#include "quantforge/core/sobol.hpp"

using namespace quantforge;
using Catch::Approx;

namespace {
std::string code_of(auto&& f) {
    try { f(); } catch (const Error& e) { return e.code(); }
    return "none";
}
}  // namespace

TEST_CASE("compounding examples from the spec") {
    using enum CompoundingKind;
    CHECK(discount_factor(0.05, 2, {Simple, {}}) == Approx(1 / 1.1));
    CHECK(discount_factor(0.05, 2, {Periodic, 2}) == Approx(0.905950645));
    CHECK(discount_factor(0.05, 2, {Continuous, {}}) == Approx(0.904837418));
    CHECK(discount_factor(5.0, 0, {Simple, {}}) == 1.0);
    CHECK(convert_rate(0.05, 2, {Continuous, {}}, {Continuous, {}}) == Approx(0.05));
    CHECK(code_of([] { convert_rate(0.05, 0, {Simple, {}}, {Simple, {}}); }) == "E_DOMAIN");
    CHECK(code_of([] { discount_factor(0.05, 1, {Periodic, 5}); }) == "E_SCHEMA");
}

TEST_CASE("snapshot worked example and SHA-256") {
    const auto bytes = sha256("abc");
    CHECK(bytes[0] == 0xba);
    CHECK(bytes[31] == 0xad);
    const auto h = snapshot_hash(R"({"b":1,"a":[true,null,"x\n"]})");
    CHECK(h.canonical == R"({"a":[true,null,"x\u000a"],"b":#3ff0000000000000})");
    CHECK(snapshot_hash(R"({"b":1.0e0,"a":[true,null,"x\n"],"snapshot_id":"z"})").snapshot_id == h.snapshot_id);
    CHECK(snapshot_hash(R"({"a":-0})").canonical == R"({"a":#0000000000000000})");
    CHECK(snapshot_hash(R"({"a":1e-999})").canonical == R"({"a":#0000000000000000})");
}

TEST_CASE("snapshot rejections rank as the spec lists them") {
    CHECK(code_of([] { snapshot_hash("{"); }) == "E_PARSE");
    CHECK(code_of([] { snapshot_hash(R"({"a":1,"a":2})"); }) == "E_PARSE");
    CHECK(code_of([] { snapshot_hash(R"({"a":1e999})"); }) == "E_SCHEMA");
    CHECK(code_of([] { snapshot_hash(R"({"a":"\ud800"})"); }) == "E_SCHEMA");
    CHECK(code_of([] { snapshot_hash("[]"); }) == "E_SCHEMA");
    CHECK(code_of([] { snapshot_hash(R"({"a":1e999,"b":1,"b":2})"); }) == "E_PARSE");
    std::string deep = R"({"a":)";
    for (int i = 0; i < 63; ++i) deep += '[';
    deep += "1";
    for (int i = 0; i < 63; ++i) deep += ']';
    deep += '}';
    CHECK_NOTHROW(snapshot_hash(deep));
    const std::string too_deep = R"({"a":[)" + deep + "]}";
    CHECK(code_of([&] { snapshot_hash(too_deep); }) == "E_LIMIT");
    const std::string absurd = "{\"a\":" + std::string(200000, '[') + std::string(200000, ']') + "}";
    CHECK(code_of([&] { snapshot_hash(absurd); }) == "E_LIMIT");
    CHECK(code_of([&] { snapshot_hash("{\"a\":" + std::string(200000, '[')); }) == "E_LIMIT");  // the scan checks no syntax
    CHECK(code_of([] { snapshot_hash(R"({"a":")" + std::string(100, '[') + R"("})"); }) == "none");
    CHECK(code_of([] { snapshot_hash(std::string(1048577, ' ')); }) == "E_LIMIT");
}

TEST_CASE("JSON numbers round trip") {
    for (const double v : {0.1, 1e300, 5e-324, 1.7976931348623157e308, -2.5})
        CHECK(json::parse(json::format_real(v)).value.number == v);
    CHECK(json::parse("12").value.integral);
    CHECK_FALSE(json::parse("12.0").value.integral);
    for (const char* bad : {"01", "1.", ".5", "+1", "NaN", "[1,]", "\"\t\""})
        CHECK(code_of([&] { json::parse(bad); }) == "E_PARSE");
}

TEST_CASE("xoshiro256** reference output") {
    Xoshiro256 rng(Xoshiro256::State{1, 2, 3, 4});
    CHECK(rng.next() == 11520);
    CHECK(rng.next() == 0);
    CHECK(rng.next() == 1509978240);
    CHECK(rng.next() == 1215971899390074240ULL);
}

TEST_CASE("uniforms stay inside (0, 1), and streams differ") {
    CHECK(uniform_from_bits(0) == 0x1p-53);
    CHECK(uniform_from_bits(~0ULL) == 1.0 - 0x1p-53);
    CHECK(Xoshiro256(7, 0).next() != Xoshiro256(7, 1).next());
}

TEST_CASE("PPND16 known values") {
    CHECK(ppnd16(0.5) == 0.0);
    CHECK(ppnd16(0.975) == Approx(1.959963984540054).epsilon(1e-14));
    CHECK(ppnd16(1e-300) == Approx(-37.0471).epsilon(1e-4));
    CHECK(ppnd16(0.1) == -ppnd16(0.9));
}

TEST_CASE("Sobol first points and skip") {
    Sobol s(2);
    double p[2];
    s.next(p);
    CHECK((p[0] == 0.5 && p[1] == 0.5));
    s.next(p);
    CHECK((p[0] == 0.75 && p[1] == 0.25));
    s.next(p);
    double q[2];
    Sobol skipped(2, 3);
    skipped.next(q);
    s.next(p);
    CHECK((p[0] == q[0] && p[1] == q[1]));
    CHECK(code_of([] { check_sobol_request(65, 1, 0); }) == "E_INPUT");
}

TEST_CASE("quote checks") {
    QuoteCheckInputs in;
    in.as_of = 1000;
    in.stale_after_seconds = 60;
    in.positive_only = true;
    in.history["H"] = {10, 10.1, 9.9, 10.2, 9.8};
    in.quotes = {{"A", 940, 1.0, 1.1, "FIRM"},
                 {"B", 939, 1.0, 1.1, "INDICATIVE"},
                 {"C", 1000, {}, -1.0, "FIRM"},
                 {"D", 1000, 2.0, 1.0, "FIRM"},
                 {"E", 1000, 1.0, 1.0, "INDICATIVE"},
                 {"H", 1000, 20.0, 20.0, "FIRM"}};
    const auto r = check_quotes(in);
    CHECK(r[0].quote_status == "FIRM");
    CHECK(r[1].quote_status == "STALE");
    CHECK(r[2].quote_status == "MISSING");
    CHECK(r[2].quality_flags == std::vector<std::string>{"MISSING_BID", "NON_POSITIVE"});
    CHECK(r[3].quote_status == "CROSSED");
    CHECK(r[4].quote_status == "INDICATIVE");
    CHECK(r[4].quality_flags == std::vector<std::string>{"LOCKED"});
    CHECK(r[5].quality_flags == std::vector<std::string>{"LOCKED", "OUTLIER"});
    in.quotes[0].event_time = 1001;
    CHECK(code_of([&] { check_quotes(in); }) == "E_INPUT");
}
