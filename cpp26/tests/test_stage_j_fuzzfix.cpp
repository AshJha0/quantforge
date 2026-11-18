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

// J-W3-18 to J-W3-20: fuzz run 43858847696 (seed 4). Before the fix the first input dereferenced a null candidate
// (UBSan) and the second looped about 2^63 times.
TEST_CASE("stage J fuzz fixes J-W3-18 to J-W3-20") {
    CHECK(has(run_case(wrap("hedge.integer.solve", R"({"a":[[1.0,9.5e+299],[0.95,1.0]],"b":[-1.265,-1.27],"weights":[1.0,1.0],"lot_sizes":[1.0,1.0]})")).json, "E_NON_FINITE"));
    CHECK(has(run_case(wrap("rates.shortrate.capfloor", R"({"model":"CIR","mean_reversion":0.25,"long_term_mean":0.04,"sigma":0.08,"short_rate":0.03,"period_times":[5e-324,2.0,3.0,4.0,5.0,6.0,7.0],"strike":0.03,"cap_floor":"CAP","notional":1000000.0})")).json, "E_NON_FINITE"));
    CHECK(has(run_case(wrap("rates.shortrate.capfloor", R"({"model":"CIR","mean_reversion":0.25,"long_term_mean":0.04,"sigma":0.08,"short_rate":0.03,"period_times":[1e-200,2.0,3.0,4.0,5.0,6.0,7.0],"strike":0.03,"cap_floor":"CAP","notional":1000000.0})")).json, "E_NON_FINITE"));
    const std::string mv = run_case(wrap("research.portfolio.mean_variance", R"({"expected_returns":[0.06771,0.098313,0.028432,0.05484,0.045746,0.009556,0.108223,0.055019],"covariance":[[0.048331,0.004555,-0.017935,0.016324,-0.006755,0.004188,0.012427,-0.006854],[0.004555,0.032681,-0.003512,-0.000217,-0.010136,0.022911,0.013417,-0.001925],[-0.017935,-0.003512,0.034533,-0.005937,0.014412,-0.007383,-0.004539,0.001099],[0.016324,-0.000217,-0.005937,0.036879,0.00083,-0.002874,-0.011025,-0.005214],[-0.006755,-0.010136,0.014412,0.00083,0.042148,-0.007134,-0.006968,-0.002897],[0.004188,0.022911,-0.007383,-0.002874,-0.007134,0.045017,0.009949,0.000445],[0.012427,0.013417,-0.004539,-0.011025,-0.006968,0.009949,0.055737,-0.002087],[-0.006854,-0.001925,0.001099,-0.005214,-0.002897,0.000445,-0.002087,0.030976]],"risk_aversion":3.0,"lower":[-9007199254740992.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0],"upper":[0.2375,0.2375,0.2375,0.2375,0.2375,0.2375,0.2375,0.2375]})")).json;
    CHECK(has(mv, R"("status":"ok")"));
    CHECK(has(mv, R"("weights":[0.0623952422762)"));
}

// J-W3-21: CIR at t_0 = 1e-10 (noncentrality about 1.9e11). Before the fix the upward Poisson loop stopped after
// 100,000 terms, under one Poisson standard deviation, and the first caplet was 3690.6.
TEST_CASE("stage J fuzz fix J-W3-21") {
    const std::string cap = R"({"model":"CIR","mean_reversion":0.25,"long_term_mean":0.04,"sigma":0.08,"short_rate":0.03,"period_times":[1e-10,2.0,3.0,4.0,5.0,6.0,7.0],"strike":0.03,"cap_floor":"CAP","notional":1000000.0})";
    const std::string r = run_case(wrap("rates.shortrate.capfloor", cap)).json;
    CHECK(has(r, R"("caplet_prices":[5790.06886878)"));
    std::string floor = cap;
    floor.replace(floor.find(R"("CAP")"), 5, R"("FLOOR")");
    CHECK(has(run_case(wrap("rates.shortrate.capfloor", floor)).json, R"("caplet_prices":[0)"));
    CHECK(has(run_case(wrap("rates.shortrate.capfloor", R"({"model":"CIR","mean_reversion":0.25,"long_term_mean":0.04,"sigma":0.08,"short_rate":0.0263,"period_times":[1e-06,2.0,3.0],"strike":0.03,"cap_floor":"CAP","notional":1000000.0})")).json, "E_LIMIT"));
}
