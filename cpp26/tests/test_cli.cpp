#include <algorithm>
#include <catch2/catch_test_macros.hpp>
#include <string>

#include "dispatch.hpp"

using quantforge::cli::run_case;

namespace {
bool has(const std::string& s, const std::string& part) { return s.find(part) != std::string::npos; }
std::string wrap(const std::string& op, const std::string& inputs) {
    return R"({"schema_version":"1.0","case_id":"c1","operation":")" + op + R"(","inputs":)" + inputs + "}";
}
}  // namespace

TEST_CASE("the contract's success example") {
    const auto r = run_case(wrap("core.daycount.year_fraction", R"({"convention":"ACT_360","start":"2024-01-01","end":"2024-07-01"})"));
    CHECK(r.ok);
    CHECK(has(r.json, R"("year_fraction":0.5055555555555555)"));
}

TEST_CASE("malformed cases are results") {
    CHECK(has(run_case("{nope").json, R"("case_id":"unknown")"));
    CHECK(has(run_case("{nope").json, "E_PARSE"));
    CHECK(has(run_case("[1]").json, "E_SCHEMA"));
    CHECK(has(run_case(R"({"schema_version":"1.0","case_id":"c1","case_id":"c2","operation":"a.b","inputs":{}})").json, "E_PARSE"));
    CHECK(has(run_case(wrap("core.nothing.here", "{}")).json, "E_UNSUPPORTED_OPERATION"));
    CHECK(has(run_case(wrap("Bad", "{}")).json, "E_SCHEMA"));
    CHECK(has(run_case(wrap("core.rng.inverse_normal", R"({"p":[1e400]})")).json, "E_SCHEMA"));
}

TEST_CASE("integers have no fraction, and schema outranks rules") {
    CHECK(has(run_case(wrap("core.sobol.points", R"({"dimensions":1.0,"count":1})")).json, "E_SCHEMA"));
    CHECK(has(run_case(wrap("core.sobol.points", R"({"dimensions":0,"count":1})")).json, "E_INPUT"));
    CHECK(has(run_case(wrap("core.compounding.discount_factor", R"({"rate":0.1,"t":-1,"compounding":"PERIODIC"})")).json, "E_SCHEMA"));
}

TEST_CASE("non-finite outputs become E_NON_FINITE") {
    const auto r = run_case(wrap("core.integrate.trapezoid", R"({"function":"inv_sqrt","a":0,"b":1,"n":4})"));
    CHECK_FALSE(r.ok);
    CHECK(has(r.json, "E_NON_FINITE"));
}

TEST_CASE("nulls, and diagnostics") {
    CHECK(has(run_case(wrap("core.stats.summary", R"({"x":[2,2,2]})")).json, R"("skewness":null)"));
    const auto root = run_case(wrap("core.root.brent", R"({"function":"cos_minus_x","a":0,"b":1})")).json;
    CHECK(has(root, R"("termination")"));
    CHECK(has(root, R"("iterations")"));
    CHECK(has(run_case(wrap("core.integrate.gauss_kronrod", R"({"function":"inv_sqrt","a":0,"b":1})")).json, "error_estimate"));
}

TEST_CASE("operations are sorted and all answer") {
    const auto ops = quantforge::cli::operations();
    CHECK(ops.size() == 51);
    CHECK(std::is_sorted(ops.begin(), ops.end()));
    for (const auto& op : ops) CHECK_FALSE(has(run_case(wrap(op, "{}")).json, "E_UNSUPPORTED_OPERATION"));
}
