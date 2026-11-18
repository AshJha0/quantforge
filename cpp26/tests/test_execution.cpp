// Stage H wave 1 (rulings HR-1 to HR-10): every golden row of the specs, the property tests they list, and the
// CLI wiring (HR-3 integer slices, HR-9 limits, HR-10 label).
#include <catch2/catch_test_macros.hpp>
#include <cmath>
#include <random>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/execution.hpp"

namespace ex = quantforge::execution;
using Vec = std::vector<double>;

namespace {
const ex::AcParams P{1e6, 5, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7};

template <class F>
std::string code_of(F f) {
    try {
        f();
    } catch (const quantforge::Error& e) {
        return e.code();
    }
    return "none";
}

bool close(double expected, double actual, double rel) {
    return std::fabs(expected - actual) <= rel * std::max(1.0, std::fabs(expected));
}

double sum(const Vec& v) {
    double s = 0;
    for (const double x : v) s += x;
    return s;
}

std::string run(const std::string& op, const std::string& inputs) {
    return quantforge::cli::run_case(R"({"schema_version":"1.0","case_id":"c","operation":")" + op +
                                     R"(","inputs":)" + inputs + "}")
        .json;
}
}  // namespace

TEST_CASE("schedule goldens sched_h-0001..0008", "[execution]") {
    CHECK(ex::twap(1000, 3, ex::Mode::Units) == Vec{334, 333, 333});
    CHECK(ex::twap(1000, 4, ex::Mode::Continuous) == Vec{250, 250, 250, 250});
    const Vec v3 = ex::vwap(1000, {1, 2, 3, 4}, ex::Mode::Continuous);
    for (std::size_t i = 0; i < 4; ++i) CHECK(close(100.0 * (double)(i + 1), v3[i], 1e-12));
    CHECK(ex::vwap(10, {1, 1, 1}, ex::Mode::Units) == Vec{4, 3, 3});
    const ex::Pov a = ex::pov(1000, 0.2, {1000, 2000, 4000}, ex::Mode::Units);
    CHECK(a.slices == Vec{250, 500, 250});
    CHECK(a.residual == 0);
    const ex::Pov b = ex::pov(1000, 0.1, {900, 900}, ex::Mode::Continuous);
    CHECK(close(100, b.slices[0], 1e-12));
    CHECK(close(100, b.slices[1], 1e-12));
    CHECK(close(800, b.residual, 1e-12));
    CHECK(code_of([] { ex::pov(1000, 1.0, {1}, ex::Mode::Units); }) == "E_DOMAIN");
    CHECK(code_of([] { ex::vwap(1000, {0, 0}, ex::Mode::Units); }) == "E_DOMAIN");
    CHECK(code_of([] { ex::twap(10.5, 3, ex::Mode::Units); }) == "E_INPUT");
    CHECK(code_of([] { ex::twap(10, 0, ex::Mode::Units); }) == "E_INPUT");
    CHECK(code_of([] { ex::vwap(10, {1, -1}, ex::Mode::Units); }) == "E_DOMAIN");
    CHECK(code_of([] { ex::vwap(10, {}, ex::Mode::Units); }) == "E_INPUT");
}

TEST_CASE("slices sum exactly; POV participation holds where not capped", "[execution]") {
    std::mt19937_64 g(7);
    std::uniform_real_distribution<double> u(0, 1);
    for (int trial = 0; trial < 300; ++trial) {
        const auto n = (std::size_t)(1 + g() % 40);
        const double x = (double)(1 + g() % 1000000);
        Vec w(n);
        for (double& v : w) v = g() % 4 == 0 ? 0 : u(g) * 10;
        w[g() % n] += 1;
        for (const ex::Mode m : {ex::Mode::Units, ex::Mode::Continuous}) {
            const double tol = m == ex::Mode::Units ? 0 : 1e-12 * x;
            CHECK(std::fabs(sum(ex::twap(x, (long long)n, m)) - x) <= tol);
            const Vec v = ex::vwap(x, w, m);
            CHECK(std::fabs(sum(v) - x) <= tol);
            for (const double s : v) CHECK((s >= 0 && (m == ex::Mode::Continuous || s == std::rint(s))));
        }
        const double p = 0.01 + 0.9 * u(g);
        Vec mv(n);
        for (double& v : mv) v = u(g) * 1e5;
        const ex::Pov r = ex::pov(x, p, mv, ex::Mode::Continuous);
        double left = x;
        for (std::size_t i = 0; i < n; ++i) {
            if (r.slices[i] < left - 1e-9 * x && mv[i] > 0) CHECK(close(p, r.slices[i] / (r.slices[i] + mv[i]), 1e-12));
            left -= r.slices[i];
        }
        const ex::Pov ru = ex::pov(x, p, mv, ex::Mode::Units);
        CHECK(ru.filled + ru.residual == x);
    }
}

TEST_CASE("Almgren-Chriss goldens ac_h-0001..0005", "[execution]") {
    const ex::AcTrajectory r1 = ex::ac_trajectory(P, 0);
    CHECK(r1.holdings == Vec{1e6, 8e5, 6e5, 4e5, 2e5, 0});
    CHECK(close(662500, r1.expected_cost, 1e-12));
    CHECK(close(1.083e12, r1.variance, 1e-12));
    CHECK(r1.kappa == 0);
    const ex::AcTrajectory r2 = ex::ac_trajectory(P, 1e-6);
    CHECK(close(0.6070761632, r2.kappa, 1e-10));
    const Vec h{1e6, 541955.5544, 289854.2194, 147897.4878, 62141.8016, 0};
    for (std::size_t j = 0; j < h.size(); ++j) CHECK(close(h[j], r2.holdings[j], 1e-9));
    CHECK(close(911226.986, r2.expected_cost, 1e-9));
    CHECK(close(3.641285721e11, r2.variance, 1e-9));
    CHECK(close(1275355.558, r2.objective, 1e-9));
    CHECK(code_of([] { ex::ac_trajectory({1e6, 5, 5, 0.95, 0.0625, 2.5e-6, 5e-6}, 1e-6); }) == "E_DOMAIN");
    const ex::AcTrajectory r4 = ex::ac_trajectory({1e6, 5, 1, 0.95, 0.0625, 2.5e-6, 2.5e-7}, 1e-6);
    CHECK(r4.holdings == Vec{1e6, 0});
    CHECK(close(562500, r4.expected_cost, 1e-12));
    CHECK(std::fabs(r2.kappa - 0.6) <= 0.05);  // ac_h-0005, [AC00] p. 24
    CHECK(std::fabs(r2.kappa * 5 - 3) <= 0.25);
    CHECK(close(3.0353808, r2.kappa * 5, 1e-8));
    CHECK(code_of([] { ex::ac_trajectory({1e6, 5, 0, 1, 0, 1e-6, 0}, 0); }) == "E_INPUT");
    CHECK(code_of([] { ex::ac_trajectory({1e6, 0, 5, 1, 0, 1e-6, 0}, 0); }) == "E_DOMAIN");
    CHECK(code_of([] { ex::ac_trajectory({1e6, 5, 5, -1, 0, 1e-6, 0}, 0); }) == "E_DOMAIN");
    CHECK(code_of([] { ex::ac_frontier(P, {}); }) == "E_INPUT");
}

TEST_CASE("Almgren-Chriss properties and limits", "[execution]") {
    for (const double l : {1e-8, 1e-6, 1e-5}) {
        const ex::AcTrajectory r = ex::ac_trajectory(P, l);
        CHECK(close(1e6, sum(r.trades), 1e-12));
        for (int j = 1; j < 5; ++j) CHECK(r.holdings[(std::size_t)j] < 1e6 * (5 - j) / 5.0);
    }
    const ex::AcTrajectory tiny = ex::ac_trajectory(P, 1e-15);
    for (int j = 0; j <= 5; ++j) CHECK(std::fabs(tiny.holdings[(std::size_t)j] - 1e6 * (5 - j) / 5.0) <= 1e-3);
    const double limit = std::sqrt(1e-6 * 0.95 * 0.95 / 2.5e-6);
    double prev = 1e300;
    for (const long long n : {10LL, 100LL, 1000LL}) {
        const double err = std::fabs(ex::ac_trajectory({1e6, 5, n, 0.95, 0.0625, 2.5e-6, 2.5e-7}, 1e-6).kappa - limit);
        CHECK(err < prev / 5);
        prev = err;
    }
    const double y = 1e-14;
    CHECK(close(std::sqrt(2 * y), ex::ac_kappa(2 * y, 1, 1, 1), 1e-12 * std::sqrt(2 * y)));
    const ex::AcTrajectory big =
        ex::ac_trajectory({1e6, 5, 50, 0.95, 0, 2.5e-6, 0}, (std::cosh(20.0) - 1) * 2 * 2.5e-6 / (0.95 * 0.95 * 0.01));
    CHECK(big.kappa * 5 > 700);
    for (std::size_t j = 1; j <= 50; ++j)
        CHECK((std::isfinite(big.holdings[j]) && big.holdings[j] <= big.holdings[j - 1]));
    CHECK(close(1e6, sum(big.trades), 1e-12));
    const Vec ls{0, 1e-8, 1e-7, 1e-6, 3e-6, 1e-5, 1e-4};
    const ex::AcFrontier f = ex::ac_frontier(P, ls);
    for (std::size_t i = 1; i < ls.size(); ++i) {
        CHECK(f.expected_cost[i] >= f.expected_cost[i - 1]);
        CHECK(f.variance[i] <= f.variance[i - 1]);
    }
    CHECK(f.expected_cost[3] == ex::ac_trajectory(P, 1e-6).expected_cost);
}

TEST_CASE("impact goldens imp_h-0001..0004", "[execution]") {
    CHECK(close(0.002, ex::impact_sqrt(1e5, 1e7, 0.02, 1), 1e-15));
    CHECK(close(0.004, ex::impact_sqrt(4e5, 1e7, 0.02, 1), 1e-15));
    const ex::OwOptimal a = ex::ow_optimal(1000, 1, 8);
    CHECK(close(100, a.initial_block, 1e-14));
    CHECK(close(100, a.final_block, 1e-14));
    CHECK(close(800, a.rate, 1e-14));
    const ex::OwOptimal b = ex::ow_optimal(100000, 1, 2.231);
    CHECK(close(23635.0744504845, b.initial_block, 1e-13));
    CHECK(close(52729.8510990310, b.rate, 1e-13));
    CHECK(close(100000, 2 * b.initial_block + b.rate, 1e-14));
    CHECK(std::fabs(ex::ow_optimal(1000, 1, 1e-9).initial_block - 500) <= 1e-6);
    CHECK(code_of([] { ex::impact_sqrt(-1, 1e7, 0.02, 1); }) == "E_DOMAIN");
    CHECK(code_of([] { ex::impact_sqrt(1, 0, 0.02, 1); }) == "E_DOMAIN");
    CHECK(code_of([] { ex::ow_optimal(1, 1, 0); }) == "E_DOMAIN");
}

TEST_CASE("TCA goldens tca_h-0001..0003 and decomposition", "[execution]") {
    const std::vector<ex::Fill> fills{{600, 100.20}, {200, 100.30}};
    const ex::Shortfall a = ex::shortfall(ex::Side::Buy, 100, 100.10, 101, 1000, fills, 5, std::nullopt);
    CHECK(close(80, a.delay, 1e-12));
    CHECK(close(100, a.execution, 1e-12));
    CHECK(close(200, a.opportunity, 1e-12));
    CHECK(close(385, a.total, 1e-12));
    CHECK(close(38.5, a.total_bps, 1e-12));
    CHECK(!a.vwap_slippage);
    const ex::Shortfall b = ex::shortfall(ex::Side::Sell, 100, 100.10, 101, 1000, fills, 0, std::nullopt);
    CHECK(close(-80, b.delay, 1e-12));
    CHECK(close(-100, b.execution, 1e-12));
    CHECK(close(-200, b.opportunity, 1e-12));
    CHECK(close(-380, b.total, 1e-12));
    CHECK(code_of([] {
              ex::shortfall(ex::Side::Buy, 100, 100.1, 101, 1000, {{600, 100.2}, {600, 100.3}}, 0, std::nullopt);
          }) == "E_INPUT");
    CHECK(code_of([] { ex::shortfall(ex::Side::Buy, 0, 1, 1, 10, {}, 0, std::nullopt); }) == "E_DOMAIN");
    CHECK(close(800 * 0.225, *ex::shortfall(ex::Side::Buy, 100, 100.10, 101, 1000, fills, 0, 100.0).vwap_slippage, 1e-12));
    std::mt19937_64 g(11);
    std::uniform_real_distribution<double> u(0, 1);
    for (int trial = 0; trial < 500; ++trial) {
        const auto n = (std::size_t)(g() % 8);
        std::vector<ex::Fill> f(n);
        double x = 0;
        for (auto& fi : f) {
            fi = {(double)(1 + g() % 1000), 50 + 100 * u(g)};
            x += fi.quantity;
        }
        const bool full = n > 0 && g() % 2 == 0;
        if (!full) x += (double)(1 + g() % 1000);
        const double fees = 10 * u(g), pd = 50 + 100 * u(g);
        const ex::Side side = g() % 2 ? ex::Side::Buy : ex::Side::Sell;
        const ex::Shortfall r = ex::shortfall(side, pd, 50 + 100 * u(g), 50 + 100 * u(g), x, f, fees, std::nullopt);
        CHECK(std::fabs(r.total - (r.delay + r.execution + r.opportunity + fees)) <=
              1e-10 * std::max(1.0, std::fabs(r.total)));
        if (full) CHECK(r.opportunity == 0);
    }
}

TEST_CASE("Avellaneda-Stoikov goldens as_h-0001..0007 and properties", "[execution]") {
    const ex::Quotes a = ex::as_quotes(100, 2, 0.1, 2, 1, 1.5);
    CHECK(close(99.2, a.reservation, 1e-12));
    CHECK(close(1.6907704228, a.spread, 1e-10));
    CHECK(close(98.3546147886, a.bid, 1e-10));
    CHECK(close(100.0453852114, a.ask, 1e-10));
    const ex::Quotes b = ex::as_quotes(100, 0, 0.1, 2, 1, 1.5);
    CHECK(b.reservation == 100);
    CHECK(close(99.1546147886, b.bid, 1e-10));
    CHECK(close(100.8453852114, b.ask, 1e-10));
    const ex::Quotes c = ex::as_quotes(100, 2, 0.1, 2, 0, 1.5);
    CHECK(c.reservation == 100);
    CHECK(close(1.2907704228, c.spread, 1e-10));
    CHECK(code_of([] { ex::as_quotes(100, 2, 0, 2, 1, 1.5); }) == "E_DOMAIN");
    const double s5 = ex::as_quotes(100, 0, 0.1, 2, 0.5, 1.5).spread;
    const double s6 = ex::as_quotes(100, 0, 0.01, 2, 0.5, 1.5).spread;
    const double s7 = ex::as_quotes(100, 0, 1, 2, 0.5, 1.5).spread;
    CHECK(close(1.4907704228, s5, 1e-10));
    CHECK(close(1.3489085437, s6, 1e-10));
    CHECK(close(3.0216512475, s7, 1e-10));
    CHECK(std::fabs(s5 - 1.49) <= 0.005);
    CHECK(std::fabs(s6 - 1.35) <= 0.005);
    CHECK(std::fabs(s7 - 3.02) <= 0.005);
    CHECK(std::fabs(ex::as_quotes(100, 0, 1e-12, 2, 1, 1.5).spread - 2 / 1.5) <= 1e-10);
    double prev = 1e300;
    for (int q = -5; q <= 5; ++q) {
        const ex::Quotes r = ex::as_quotes(100, q, 0.1, 2, 1, 1.5);
        CHECK(r.reservation < prev);
        prev = r.reservation;
    }
}

TEST_CASE("stage H operations through the CLI", "[execution]") {
    auto has = [](const std::string& s, const std::string& part) {
        INFO(s);
        CHECK(s.find(part) != std::string::npos);
    };
    has(run("exec.schedule.twap", R"({"quantity":1000,"n_buckets":3,"mode":"UNITS"})"), R"("slices":[334,333,333])");
    has(run("exec.schedule.pov", R"({"quantity":1000,"participation":0.2,"market_volume":[1000,2000,4000],"mode":"UNITS"})"),
        R"("slices":[250,500,250],"filled":1000,"residual":0)");
    has(run("exec.schedule.vwap", R"({"quantity":10,"profile":[1,1,1],"mode":"UNITS"})"), "[4,3,3]");
    const std::string ac = R"("quantity":1e6,"horizon":5,"n_steps":5,"sigma":0.95,"epsilon":0.0625,"eta":2.5e-6,"gamma":2.5e-7)";
    has(run("exec.ac.trajectory", "{" + ac + R"(,"risk_aversion":0})"), R"("expected_cost":662500)");
    has(run("exec.ac.frontier", "{" + ac + R"(,"risk_aversions":[0,1e-6]})"), R"("variances":[)");
    has(run("exec.impact.sqrt", R"({"quantity":1e5,"daily_volume":1e7,"daily_vol":0.02})"),
        R"("model":"assumed parameters; not calibrated to any venue")");
    has(run("exec.impact.ow_optimal", R"({"quantity":1000,"horizon":1,"resilience":8})"), R"("rate":800)");
    const std::string tca = R"({"side":"BUY","decision_price":100,"arrival_price":100.10,"end_price":101,"order_quantity":1000,"fills":[{"quantity":600,"price":100.20},{"quantity":200,"price":100.30}],"fees":5)";
    has(run("exec.tca.shortfall", tca + "}"), R"("total_bps")");
    CHECK(run("exec.tca.shortfall", tca + "}").find("vwap_slippage") == std::string::npos);
    has(run("exec.tca.shortfall", tca + R"(,"benchmark_vwap":100.2})"), "vwap_slippage");
    has(run("micro.mm.as_quotes", R"({"mid":100,"inventory":2,"risk_aversion":0.1,"sigma":2,"time_left":1,"k":1.5})"),
        R"("reservation":99.2)");
    has(run("exec.schedule.twap", R"({"quantity":1000,"n_buckets":100001,"mode":"UNITS"})"), "E_LIMIT");
    has(run("exec.schedule.twap", R"({"quantity":1000,"n_buckets":100001,"mode":"BAD"})"), "E_SCHEMA");
    has(run("exec.schedule.pov", R"({"quantity":1000,"participation":"NaN","market_volume":[1],"mode":"UNITS"})"),
        "E_DOMAIN");
    std::string many = R"({"side":"BUY","decision_price":100,"arrival_price":100,"end_price":100,"order_quantity":2e6,"fees":0,"fills":[)";
    for (int i = 0; i < 100001; ++i) many += std::string(i ? "," : "") + R"({"quantity":1,"price":100})";
    has(run("exec.tca.shortfall", many + "]}"), R"("status":"ok")");
}
