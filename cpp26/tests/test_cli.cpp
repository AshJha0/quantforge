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
    CHECK(ops.size() == 84);
    CHECK(std::is_sorted(ops.begin(), ops.end()));
    for (const auto& op : ops) CHECK_FALSE(has(run_case(wrap(op, "{}")).json, "E_UNSUPPORTED_OPERATION"));
}

TEST_CASE("the store: corrections, withdrawals, the inclusive limit") {
    const std::string records = R"({"records":[
      {"sequence":1,"series_id":"S","event_time":"2024-01-01T00:00:00Z","knowledge_time":"2024-01-02T00:00:00Z","value":1},
      {"sequence":2,"series_id":"S","event_time":"2024-01-01T01:00:00+01:00","knowledge_time":"2024-01-03T00:00:00Z","value":2},
      {"sequence":3,"series_id":"S","event_time":"2024-01-01T00:00:00Z","knowledge_time":"2024-01-04T00:00:00Z","value":null,"deleted":true}],)";
    const auto at = [&](const std::string& t) {
        return run_case(wrap("core.store.latest", records + R"("series_id":"S","as_of":")" + t + R"("})")).json;
    };
    CHECK(has(at("2024-01-02T00:00:00Z"), R"("value":1)"));
    CHECK(has(at("2024-01-03T00:00:00Z"), R"("value":2)"));
    CHECK(has(at("2024-01-04T00:00:00Z"), R"("row":null)"));
    CHECK(has(at("2024-01-01T23:59:59Z"), R"("row":null)"));
    const auto bad = R"({"records":[{"sequence":2,"series_id":"S","event_time":"2024-01-01T00:00:00Z","knowledge_time":"2024-01-02T00:00:00Z","value":1},
      {"sequence":2,"series_id":"S","event_time":"2024-01-01T00:00:00Z","knowledge_time":"2024-01-02T00:00:00Z","value":1}]})";
    CHECK(has(run_case(wrap("core.store.chain", bad)).json, "E_INPUT"));
    CHECK(has(run_case(wrap("core.store.chain", R"({"records":[]})")).json, std::string(64, '0')));
}

TEST_CASE("limits come after schema and before rules") {
    CHECK(has(run_case(wrap("core.integrate.simpson", R"({"function":"exp","a":0,"b":1,"n":10000001})")).json, "E_LIMIT"));
    CHECK(has(run_case(wrap("core.integrate.simpson", R"({"function":"nope","a":0,"b":1,"n":10000001})")).json, "E_SCHEMA"));
    CHECK(has(run_case(wrap("core.mc.gbm_european", R"({"option":"CALL","spot":-1,"strike":1,"r":0,"q":0,"sigma":1,"t":1,"paths":1000001,"seed":"1","method":"PLAIN"})")).json, "E_LIMIT"));
    std::string big = "[0";
    for (int i = 0; i < 100000; ++i) big += ",0";
    big += "]";
    CHECK(has(run_case(wrap("core.stats.quantile", R"({"x":)" + big + R"(,"p":[0.5]})")).json, "E_LIMIT"));
    CHECK(has(run_case(wrap("core.stats.quantile", R"({"x":)" + big + "}")).json, "E_SCHEMA"));
}

TEST_CASE("a case nested above 80 levels stops before parsing") {
    const auto r = run_case(wrap("a.b", std::string(81, '[')));
    CHECK(has(r.json, "E_LIMIT"));
    CHECK(has(r.json, R"("case_id":"unknown")"));
}

TEST_CASE("nesting limit covers every record key") {
    const std::string deep = std::string(65, '[') + std::string(65, ']');
    CHECK(has(run_case(wrap("core.store.chain", R"({"records":[{"sequence":1,"series_id":"S","event_time":"2024-01-01T00:00:00Z","knowledge_time":"2024-01-01T00:00:00Z","value":1,"extra":)" + deep + "}]}")).json, "E_LIMIT"));
}

TEST_CASE("splines take the largest legal knot count") {
    std::string x = "[0", y = "[0";
    for (int i = 1; i < 100000; ++i) {
        x += "," + std::to_string(i);
        y += ",1";
    }
    CHECK(run_case(wrap("core.interp.evaluate", R"({"method":"cubic_not_a_knot","x":)" + x + R"(],"y":)" + y + R"(],"at":[5.5]})")).ok);
}
