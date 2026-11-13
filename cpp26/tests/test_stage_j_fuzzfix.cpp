// Stage J lane J-0b: rulings J-0b.1 (horizon limit), J-0b.2 (overflowing squared return), J-0b.3 (ragged rows).
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

TEST_CASE("stage J fuzz fixes J-0b.1 to J-0b.3") {
    CHECK(has(run_case(wrap("vol.garch.forecast", R"({"omega":5e-06,"alpha":0.12,"beta":0.82,"next_variance":0.0003,"horizon":100001,"periods_per_year":252.0})")).json, "E_LIMIT"));
    CHECK(has(run_case(wrap("vol.garch.forecast", R"({"omega":5e-06,"alpha":0.12,"beta":0.82,"next_variance":0.0003,"horizon":2147483648,"periods_per_year":252.0})")).json, "E_LIMIT"));
    CHECK(has(run_case(wrap("vol.garch.estimate", R"({"returns":[0.01,-0.012,0.01,-0.012,0.01,-2.6755826e+297,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012],"initial_variance":1e-4,"distribution":"NORMAL","demean":true})")).json, "E_NON_FINITE"));
    CHECK(has(run_case(wrap("exotic.basket.moment", R"({"forwards":[100.0,100.0],"weights":[0.5,0.5],"vols":[0.2,0.2],"correlation":[[1.0,1.0],[]],"strike":100.0,"expiry_years":1.0,"rate":0.03,"option_type":"CALL"})")).json, "E_INPUT"));
    CHECK(has(run_case(wrap("exotic.basket.moment", R"({"forwards":[100.0,100.0],"weights":[0.5,0.5],"vols":[0.2,0.2],"correlation":[[1.0],[0.0,1.0]],"strike":100.0,"expiry_years":1.0,"rate":0.03,"option_type":"CALL"})")).json, "E_INPUT"));
    CHECK(has(run_case(wrap("exotic.basket.moment", R"({"forwards":[100.0,100.0],"weights":[0.5,0.5],"vols":[0.2,0.2],"correlation":[[1.0,0.0],[0.0,1.0,0.0]],"strike":100.0,"expiry_years":1.0,"rate":0.03,"option_type":"CALL"})")).json, "E_INPUT"));
    CHECK(has(run_case(wrap("vol.garch.forecast", R"({"omega":5e-06,"alpha":0.12,"beta":0.82,"next_variance":0.0003,"horizon":100000,"periods_per_year":252.0})")).json, R"("status":"ok")"));
}
