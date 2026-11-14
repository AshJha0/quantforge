// Every stage J research.* and wave 2 risk.* CLI handler (src/cli/ops_research.inc) through run_case: the
// success shape with optional inputs present and absent, and each handler-level E_INPUT / E_LIMIT check.
#include <catch2/catch_test_macros.hpp>
#include <initializer_list>
#include <string>

#include "dispatch.hpp"
#include "quantforge/core/json.hpp"

namespace {

namespace json = quantforge::json;

json::Value run(const std::string& op, const std::string& inputs) {
    const auto r = quantforge::cli::run_case(R"({"schema_version":"1.0","case_id":"c","operation":")" + op +
                                             R"(","inputs":)" + inputs + "}");
    return json::parse(r.json).value;
}

void ok(const std::string& op, const std::string& inputs, std::initializer_list<const char*> keys) {
    const json::Value v = run(op, inputs);
    INFO(op << " " << inputs);
    REQUIRE(v.find("outputs") != nullptr);
    for (const char* k : keys) CHECK(v.find("outputs")->find(k) != nullptr);
}

std::string code(const std::string& op, const std::string& inputs) {
    const json::Value v = run(op, inputs);
    const auto* e = v.find("error");
    return e == nullptr ? std::string("ok") : e->find("code")->text;
}

const std::string cov = "[[0.04,0.01],[0.01,0.09]]";

}  // namespace

TEST_CASE("research.backtest.run: both engines, every cost input") {
    const std::string base =
        R"("prices":[100,101,102,101,103],"targets":[0,1,1,-1,0],"half_spread_bps":2,"commission_per_unit":0.01,)"
        R"("fixed_per_trade":1,"multiplier":10,"lag":1)";
    for (const std::string engine : {"", R"(,"engine":"EVENT")", R"(,"engine":"VECTOR")"})
        ok("research.backtest.run", "{" + base + engine + "}",
           {"positions", "trades", "pnl_gross", "cost", "pnl_net", "equity", "total_gross", "total_spread_cost",
            "total_commission", "total_fixed_cost", "total_net", "turnover", "trade_count", "max_drawdown"});
}

TEST_CASE("research.cv: purged k-fold and CPCV path counts") {
    ok("research.cv.purged_kfold",
       R"({"t0":[0,1,2,3,4,5],"t1":[0.5,1.5,2.5,3.5,4.5,5.5],"n_splits":3,"embargo_pct":0.1})",
       {"folds", "embargo_count"});
    ok("research.cv.cpcv_paths", R"({"n_groups":6,"n_test_groups":2})", {"n_splits", "n_paths"});
}

TEST_CASE("research.regime.viterbi: both emission forms and every input check") {
    const std::string base = R"("initial":[0.5,0.5],"transition":[[0.9,0.1],[0.2,0.8]])";
    const std::string op = "research.regime.viterbi";
    ok(op, "{" + base + R"(,"emission":[[0.9,0.1],[0.8,0.2],[0.1,0.9]]})", {"states", "log_probability"});
    ok(op, "{" + base + R"(,"observations":[-1.0,-0.8,1.1,0.9],"means":[-1,1],"sds":[0.5,0.5]})",
       {"states", "log_probability"});
    // Both forms, then neither.
    CHECK(code(op, "{" + base + R"(,"emission":[[0.5,0.5]],"means":[0,1]})") == "E_INPUT");
    CHECK(code(op, "{" + base + "}") == "E_INPUT");
    // Transition shape: wrong row count, then a ragged row.
    CHECK(code(op, R"({"initial":[0.5,0.5],"transition":[[1,0]],"emission":[[0.5,0.5]]})") == "E_INPUT");
    CHECK(code(op, R"({"initial":[0.5,0.5],"transition":[[1,0],[1]],"emission":[[0.5,0.5]]})") == "E_INPUT");
    // Direct emission: empty, then a row of the wrong width.
    CHECK(code(op, "{" + base + R"(,"emission":[]})") == "E_INPUT");
    CHECK(code(op, "{" + base + R"(,"emission":[[0.5,0.25,0.25]]})") == "E_INPUT");
    // Gaussian form: a missing sds, then K mismatches and no observations.
    CHECK(code(op, "{" + base + R"(,"observations":[1.0],"means":[0,1]})") == "E_INPUT");
    CHECK(code(op, "{" + base + R"(,"observations":[1.0],"means":[0],"sds":[1,1]})") == "E_INPUT");
    CHECK(code(op, "{" + base + R"(,"observations":[],"means":[0,1],"sds":[1,1]})") == "E_INPUT");
    // K above 32 (J-12).
    std::string init = "[1";
    for (int i = 1; i < 33; ++i) init += ",0";
    CHECK(code(op, R"({"initial":)" + init + R"(],"transition":[[1]],"emission":[[1]]})") == "E_LIMIT");
}

TEST_CASE("research.regime.baum_welch: a two-state fit and its iteration limit") {
    const std::string base = R"("initial":[0.5,0.5],"transition":[[0.9,0.1],[0.2,0.8]])";
    ok("research.regime.baum_welch",
       "{" + base +
           R"(,"observations":[-1.1,-0.9,-1.2,-0.8,1.0,1.2,0.9,1.1,-1.0,-0.95,1.05,0.85],"means":[-0.5,0.5],)"
           R"("sds":[1,1],"tolerance":1e-8,"max_iterations":200})",
       {"initial", "transition", "means", "sds", "log_likelihood", "iterations", "converged"});
    CHECK(code("research.regime.baum_welch",
               "{" + base + R"(,"observations":[1,2],"means":[0,1],"sds":[1,1],"max_iterations":10001})") ==
          "E_LIMIT");
}

TEST_CASE("research.stats: PSR, DSR, power with and without a target, PBO by metric") {
    ok("research.stats.psr", R"({"sr":0.1,"n_obs":252,"skew":-0.2,"kurtosis":4,"sr_benchmark":0.0})", {"z", "psr"});
    ok("research.stats.dsr", R"({"sr":0.1,"n_obs":252,"n_trials":10,"sr_variance":0.01})", {"sr0", "z", "dsr"});
    ok("research.stats.power", R"({"years":5})", {"z_sum", "mds", "se_at_zero"});
    ok("research.stats.power", R"({"years":5,"alpha":0.05,"power":0.8,"sr_target":1.0})",
       {"years_required", "se_at_target"});
    const std::string perf =
        "[[0.1,0.2],[0.3,-0.1],[0.0,0.1],[0.2,0.0],[-0.1,0.3],[0.05,0.15],[0.25,-0.05],[0.1,0.1]]";
    for (const std::string metric : {"", R"(,"metric":"SHARPE")", R"(,"metric":"MEAN")"})
        ok("research.stats.pbo", R"({"performance":)" + perf + R"(,"n_partitions":4)" + metric + "}",
           {"pbo", "logits", "n_combinations"});
    CHECK(code("research.stats.pbo", R"({"performance":)" + perf + R"(,"n_partitions":4,"metric":"SORTINO"})") ==
          "E_SCHEMA");
}

TEST_CASE("research.portfolio: mean-variance bounds and risk-parity budgets, with their length checks") {
    const std::string mv = R"({"expected_returns":[0.08,0.05],"covariance":)" + cov + R"(,"risk_aversion":3)";
    ok("research.portfolio.mean_variance", mv + R"(,"lower":[0,0],"upper":[1,1]})",
       {"weights", "expected_return", "volatility", "objective", "at_bound"});
    ok("research.portfolio.mean_variance", mv + "}", {"weights"});
    CHECK(code("research.portfolio.mean_variance", mv + R"(,"lower":[0]})") == "E_INPUT");
    CHECK(code("research.portfolio.mean_variance", mv + R"(,"upper":[1]})") == "E_INPUT");
    ok("research.portfolio.risk_parity", R"({"covariance":)" + cov + "}", {"weights", "volatility", "contributions"});
    ok("research.portfolio.risk_parity", R"({"covariance":)" + cov + R"(,"budgets":[0.6,0.4]})", {"weights"});
    CHECK(code("research.portfolio.risk_parity", R"({"covariance":)" + cov + R"(,"budgets":[1]})") == "E_INPUT");
}

TEST_CASE("research.estimate: Ledoit-Wolf and Black-Litterman") {
    ok("research.estimate.ledoit_wolf",
       R"({"returns":[[0.01,0.02],[-0.01,0.0],[0.02,0.01],[0.0,-0.02],[0.015,0.005],[-0.005,0.01]]})",
       {"covariance", "shrinkage", "mu"});
    ok("research.estimate.black_litterman",
       R"({"covariance":)" + cov +
           R"(,"prior_returns":[0.05,0.07],"pick":[[1,-1]],"views":[0.01],"view_covariance":[[0.001]],"tau":0.05})",
       {"posterior_returns", "posterior_covariance", "predictive_covariance"});
}

TEST_CASE("risk wave 2: Euler contributions and the Z2 ES backtest") {
    ok("risk.contrib.euler", R"({"weights":[0.5,0.5],"covariance":)" + cov + "}",
       {"volatility", "marginal", "contributions", "shares"});
    const std::string base = R"("losses":[1.0,3.0,0.5,4.0],"var":[2.0,2.0,2.0,2.0],"es":[2.5,2.5,2.5,2.5])";
    ok("risk.backtest.es_z2", "{" + base + R"(,"alpha":0.025})", {"z2", "exceptions", "expected_exceptions"});
    CHECK(code("risk.backtest.es_z2", "{" + base + R"(,"alpha":1.5})") == "E_DOMAIN");
}
