// The CLI layer's own paths: F-1 non-finite tokens, typed reads that refuse the wrong JSON kind,
// the named root functions, and the operations and version documents.
#include <catch2/catch_test_macros.hpp>
#include <algorithm>
#include <cmath>
#include <string>

#include "dispatch.hpp"
#include "quantforge/core/json.hpp"

namespace {

namespace json = quantforge::json;

std::string code_of(const std::string& op, const std::string& inputs) {
    const auto r = quantforge::cli::run_case(R"({"schema_version":"1.0","case_id":"c","operation":")" + op +
                                             R"(","inputs":)" + inputs + "}");
    if (r.ok) return "ok";
    return json::parse(r.json).value.find("error")->find("code")->text;
}

double root_of(const std::string& fn, double a, double b) {
    const auto r = quantforge::cli::run_case(
        R"({"schema_version":"1.0","case_id":"c","operation":"core.root.bisection","inputs":{"function":")" + fn +
        R"(","a":)" + std::to_string(a) + R"(,"b":)" + std::to_string(b) + "}}");
    REQUIRE(r.ok);
    return json::parse(r.json).value.find("outputs")->find("root")->number;
}

}  // namespace

TEST_CASE("F-1: the strings NaN, Infinity and -Infinity are Real values, refused as E_DOMAIN") {
    for (const char* bad : {R"("NaN")", R"("Infinity")", R"("-Infinity")"})
        CHECK(code_of("core.root.bisection", std::string(R"({"function":"cubic_wallis","a":)") + bad + R"(,"b":3})") ==
              "E_DOMAIN");
    CHECK(code_of("core.root.bisection", R"({"function":"cubic_wallis","a":"two","b":3})") == "E_SCHEMA");
}

TEST_CASE("typed reads refuse the wrong JSON kind") {
    CHECK(code_of("usecase.factor_attribution", R"({"portfolio_returns":[0.01],"factor_returns":5,"factor_names":["A"]})") ==
          "E_SCHEMA");
    CHECK(code_of("calib.fit", R"({"model":"LINEAR","x":[1,2],"y":[1,2],"start":[0,0],"method":"BFGS","report_parameters":1})") ==
          "E_SCHEMA");
}

TEST_CASE("named root functions: the at-the-money Black-Scholes vol and an unknown name") {
    // 100 N(d1) - 100 e^{-0.01} N(d2) = 10 at sigma about 0.2416 (one year, r = 1 %).
    const double vol = root_of("bs_vol_atm", 0.01, 2.0);
    CHECK(std::fabs(vol - 0.24) < 0.01);
    CHECK(std::fabs(root_of("cubic_wallis", 2.0, 3.0) - 2.0945514815423265) < 1e-9);
    CHECK(code_of("core.root.bisection", R"({"function":"no_such","a":0,"b":1})") == "E_SCHEMA");
}

TEST_CASE("operations and version documents") {
    const auto ops = quantforge::cli::operations();
    REQUIRE(ops.size() > 100);
    CHECK(std::is_sorted(ops.begin(), ops.end()));
    const json::Parsed list = json::parse(quantforge::cli::operations_json());
    REQUIRE(list.value.kind == json::Kind::Array);
    CHECK(list.value.items.size() == ops.size());
    CHECK(list.value.items.front().text == ops.front());
    const json::Parsed v = json::parse(quantforge::cli::version_json());
    CHECK(v.value.find("language")->text == "cpp");
    CHECK(!v.value.find("implementation_version")->text.empty());
    CHECK(!v.value.find("contract_version")->text.empty());
    const std::string& toolchain = v.value.find("toolchain")->text;
    CHECK((toolchain.rfind("GCC", 0) == 0 || toolchain.rfind("Clang", 0) == 0));
}
