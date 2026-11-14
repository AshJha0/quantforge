// Stage J wave 1 property tests (program/STAGE_J_HANDOVER.md "Property tests"), on this language's own data.
#include <catch2/catch_test_macros.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <random>
#include <string>
#include <vector>

#include "dispatch.hpp"
#include "quantforge/core/error.hpp"
#include "quantforge/core/research.hpp"

namespace rs = quantforge::research;
using Vec = std::vector<double>;
using Mat = std::vector<Vec>;

namespace {

bool close_rel(double a, double b, double tol) { return std::fabs(a - b) <= tol * std::max({1.0, std::fabs(a), std::fabs(b)}); }

bool same(const rs::Backtest& a, const rs::Backtest& b, double tol) {
    const auto vec = [tol](const Vec& x, const Vec& y) {
        if (x.size() != y.size()) return false;
        for (std::size_t i = 0; i < x.size(); ++i)
            if (!close_rel(x[i], y[i], tol)) return false;
        return true;
    };
    return vec(a.positions, b.positions) && vec(a.trades, b.trades) && vec(a.pnl_gross, b.pnl_gross) &&
           vec(a.cost, b.cost) && vec(a.pnl_net, b.pnl_net) && vec(a.equity, b.equity) &&
           close_rel(a.total_gross, b.total_gross, tol) && close_rel(a.total_spread, b.total_spread, tol) &&
           close_rel(a.total_commission, b.total_commission, tol) && close_rel(a.total_fixed, b.total_fixed, tol) &&
           close_rel(a.total_net, b.total_net, tol) && close_rel(a.turnover, b.turnover, tol) &&
           a.trade_count == b.trade_count && close_rel(a.max_drawdown, b.max_drawdown, tol);
}

Vec random_walk(std::mt19937_64& g, std::size_t n) {
    std::normal_distribution<double> z(0.0, 1.0);
    Vec p{100.0};
    for (std::size_t i = 1; i < n; ++i) p.push_back(p.back() * std::exp(0.01 * z(g)));
    return p;
}

double brute_log_prob(const Vec& init, const Mat& a, const Mat& e, const std::vector<long long>& path) {
    double lp = std::log(init[path[0]]) + std::log(e[0][path[0]]);
    for (std::size_t t = 1; t < path.size(); ++t) lp += std::log(a[path[t - 1]][path[t]]) + std::log(e[t][path[t]]);
    return lp;
}

}  // namespace

TEST_CASE("backtest: EVENT equals VECTOR, attribution identity, zero and doubled costs") {
    std::mt19937_64 g(20261114);
    std::uniform_int_distribution<int> pos(-5, 5), len(2, 60);
    std::uniform_real_distribution<double> u(0.0, 3.0);
    for (int trial = 0; trial < 200; ++trial) {
        rs::BacktestInput in;
        const auto n = static_cast<std::size_t>(len(g));
        in.prices = random_walk(g, n);
        for (std::size_t i = 0; i < n; ++i) in.targets.push_back(static_cast<double>(pos(g)) * 0.5);
        in.lag = static_cast<long long>(g() % n);
        in.half_spread_bps = u(g);
        in.commission_per_unit = u(g) / 100;
        in.fixed_per_trade = u(g);
        in.multiplier = 1 + u(g);
        const rs::Backtest ev = rs::backtest(in, rs::Engine::Event), ve = rs::backtest(in, rs::Engine::Vector);
        REQUIRE(same(ev, ve, 1e-10));
        const double big = std::max({std::fabs(ev.total_gross), ev.total_spread, ev.total_commission, ev.total_fixed, 1e-300});
        CHECK(std::fabs(ev.total_gross - ev.total_spread - ev.total_commission - ev.total_fixed - ev.total_net) <= 1e-12 * big);
        rs::BacktestInput dbl = in;
        dbl.half_spread_bps *= 2;
        dbl.commission_per_unit *= 2;
        dbl.fixed_per_trade *= 2;
        const rs::Backtest d = rs::backtest(dbl, rs::Engine::Event);
        CHECK(d.total_spread == 2 * ev.total_spread);
        CHECK(d.total_commission == 2 * ev.total_commission);
        CHECK(d.total_fixed == 2 * ev.total_fixed);
        rs::BacktestInput free = in;
        free.half_spread_bps = free.commission_per_unit = free.fixed_per_trade = 0;
        const rs::Backtest z = rs::backtest(free, rs::Engine::Vector);
        CHECK(z.pnl_net == z.pnl_gross);
        CHECK(z.total_net == z.total_gross);
    }
}

TEST_CASE("backtest: look-ahead canary caught at lag 0, absent at lag 1") {
    std::mt19937_64 g(7);
    const std::size_t n = 2000;
    rs::BacktestInput in;
    in.prices = random_walk(g, n);
    // Decided at the close of t from p_{t+1}: the sign of the next move (look-ahead).
    for (std::size_t t = 0; t < n; ++t) in.targets.push_back(t + 1 < n ? (in.prices[t + 1] > in.prices[t] ? 1.0 : -1.0) : 0.0);
    double abs_moves = 0;
    for (std::size_t t = 1; t < n; ++t) abs_moves += std::fabs(in.prices[t] - in.prices[t - 1]);
    in.lag = 0;  // held over bar t+1 exactly the sign of its move
    const rs::Backtest c0 = rs::backtest(in, rs::Engine::Event);
    in.lag = 1;
    const rs::Backtest c1 = rs::backtest(in, rs::Engine::Event);
    CHECK(c0.total_gross > 0.9 * abs_moves);       // detected: earns nearly every move
    CHECK(std::fabs(c1.total_gross) < 0.2 * abs_moves);  // with the lag it is noise
}

TEST_CASE("backtest: drawdown peak starts at 0 (J-6) and checks") {
    rs::BacktestInput in{{100, 99, 98}, {1, 1, 1}, 0, 0, 0, 0, 1};
    const rs::Backtest b = rs::backtest(in, rs::Engine::Event);
    CHECK(b.max_drawdown == 2.0);
    CHECK(b.trade_count == 1);
    in.lag = 3;
    CHECK_THROWS_AS(rs::backtest(in, rs::Engine::Event), quantforge::Error);
}

TEST_CASE("purged k-fold: no overlap, and t1 = t0 without embargo is plain k-fold") {
    std::mt19937_64 g(11);
    for (int trial = 0; trial < 200; ++trial) {
        const std::size_t n = 3 + g() % 40;
        Vec t0, t1;
        double t = 0;
        for (std::size_t i = 0; i < n; ++i) {
            t += static_cast<double>(g() % 3);
            t0.push_back(t);
            t1.push_back(t + static_cast<double>(g() % 5));
        }
        const long long k = 2 + static_cast<long long>(g() % (n - 1));
        const double pct = static_cast<double>(g() % 20) / 100;
        const rs::PurgedKFold r = rs::purged_kfold(t0, t1, k, pct);
        REQUIRE(r.folds.size() == static_cast<std::size_t>(k));
        for (const rs::Fold& f : r.folds) {
            const double lo = t0[f.test.front()];
            double hi = -1e300;
            for (const long long i : f.test) hi = std::max(hi, t1[i]);
            for (const long long j : f.train) {
                CHECK((t1[j] < lo || t0[j] > hi));
                CHECK(!std::ranges::binary_search(f.test, j));
            }
            CHECK(std::ranges::is_sorted(f.train));
        }
        const rs::PurgedKFold plain = rs::purged_kfold(t0, t0, k, 0.0);
        std::size_t a = 0;
        for (std::size_t f = 0; f < plain.folds.size(); ++f) {
            const std::size_t b = a + n / static_cast<std::size_t>(k) + (f < n % static_cast<std::size_t>(k) ? 1 : 0);
            std::vector<long long> test, train;
            for (std::size_t j = 0; j < n; ++j) (j >= a && j < b ? test : train).push_back(static_cast<long long>(j));
            // Equal t0 values across the block edge overlap by the closed rule, so compare on strictly increasing t0 only.
            bool strict = true;
            for (std::size_t j = 1; j < n; ++j) strict = strict && t0[j] > t0[j - 1];
            if (strict) {
                CHECK(plain.folds[f].test == test);
                CHECK(plain.folds[f].train == train);
            }
            a = b;
        }
    }
    CHECK(rs::cpcv_paths(6, 2).n_splits == 15);
    CHECK(rs::cpcv_paths(6, 2).n_paths == 5);
    CHECK(rs::cpcv_paths(64, 32).n_splits == 1832624140942590534LL);
}

TEST_CASE("viterbi: path equals brute force on small random models; ties take the smallest index") {
    std::mt19937_64 g(3);
    std::uniform_real_distribution<double> u(0.05, 1.0);
    for (int trial = 0; trial < 300; ++trial) {
        const std::size_t k = 1 + g() % 3, n = 1 + g() % 6;
        const auto row = [&] {
            Vec r(k);
            double s = 0;
            for (double& x : r) s += x = u(g);
            for (double& x : r) x /= s;
            return r;
        };
        const Vec init = row();
        Mat a, e;
        for (std::size_t i = 0; i < k; ++i) a.push_back(row());
        for (std::size_t t = 0; t < n; ++t) {
            Vec r(k);
            for (double& x : r) x = u(g);
            e.push_back(r);
        }
        const rs::ViterbiResult v = rs::viterbi(init, a, rs::log_emission(e));
        std::size_t total = 1;
        for (std::size_t t = 0; t < n; ++t) total *= k;
        double best = -std::numeric_limits<double>::infinity();
        for (std::size_t code = 0; code < total; ++code) {
            std::vector<long long> p(n);
            std::size_t c = code;
            for (std::size_t t = 0; t < n; ++t) {
                p[t] = static_cast<long long>(c % k);
                c /= k;
            }
            best = std::max(best, brute_log_prob(init, a, e, p));
        }
        CHECK(close_rel(v.log_probability, best, 1e-12));
        CHECK(close_rel(brute_log_prob(init, a, e, v.states), best, 1e-12));
    }
    // A symmetric model: every path ties, so the smallest index wins everywhere.
    const rs::ViterbiResult tie = rs::viterbi({0.5, 0.5}, {{0.5, 0.5}, {0.5, 0.5}}, rs::log_emission({{1, 1}, {1, 1}, {1, 1}}));
    CHECK(tie.states == std::vector<long long>{0, 0, 0});
    CHECK_THROWS_AS(rs::viterbi({1, 0}, {{0, 1}, {1, 0}}, rs::log_emission({{0, 1}, {0, 1}})), quantforge::Error);
}

TEST_CASE("dsr decreases in n_trials and sr_variance; psr at its own benchmark is 0.5") {
    double prev = 2;
    for (long long n = 1; n <= 1000; n = n * 3 + 1) {
        const double d = rs::dsr(0.1, 1250, -0.5, 5, n, 0.002).dsr;
        CHECK(d < prev);
        prev = d;
    }
    prev = 2;
    for (double v = 0.0; v < 0.02; v += 0.002) {
        const double d = rs::dsr(0.1, 1250, 0, 3, 50, v).dsr;
        CHECK(d <= prev);
        if (v > 0) CHECK(d < prev);
        prev = d;
    }
    CHECK(rs::psr(0.13, 500, 0.4, 6, 0.13).psr == 0.5);
    CHECK(rs::dsr(0.1, 100, 0, 3, 1, 0.5).sr0 == 0.0);
}

TEST_CASE("pbo lies in [0, 1] and is 0 with one dominating strategy") {
    std::mt19937_64 g(5);
    std::normal_distribution<double> z(0, 1);
    for (int trial = 0; trial < 50; ++trial) {
        const long long s = 2 * (1 + static_cast<long long>(g() % 4));
        const std::size_t rows = static_cast<std::size_t>(s) * (2 + g() % 3), n = 2 + g() % 5;
        Mat perf(rows, Vec(n));
        for (Vec& r : perf)
            for (double& x : r) x = z(g);
        const rs::Pbo p = rs::pbo(perf, s, trial % 2 ? rs::Metric::Mean : rs::Metric::Sharpe);
        CHECK(p.pbo >= 0.0);
        CHECK(p.pbo <= 1.0);
        for (Vec& r : perf) r[0] = 100 + std::fabs(r[0]);  // strategy 0 beats every other in every row
        CHECK(rs::pbo(perf, s, rs::Metric::Mean).pbo == 0.0);
    }
}

TEST_CASE("research verbs through the CLI: limits and enum checks") {
    const auto run = [](const std::string& op, const std::string& in) {
        return quantforge::cli::run_case(R"({"schema_version":"1.0","case_id":"c","operation":")" + op + R"(","inputs":)" + in + "}").json;
    };
    CHECK(run("research.backtest.run", R"({"prices":[1,2],"targets":[0,1],"engine":"FAST"})").find("E_SCHEMA") != std::string::npos);
    CHECK(run("research.stats.pbo", R"({"performance":[[1,2]],"n_partitions":18})").find("E_LIMIT") != std::string::npos);
    CHECK(run("research.regime.viterbi", R"({"initial":[1],"transition":[[1]]})").find("E_INPUT") != std::string::npos);
    CHECK(run("research.stats.power", R"({"years":4,"sr_target":0.5})").find("years_required") != std::string::npos);
}

TEST_CASE("rulings J-20 to J-23") {
    const auto run = [](const std::string& op, const std::string& in) {
        return quantforge::cli::run_case(R"({"schema_version":"1.0","case_id":"c","operation":")" + op + R"(","inputs":)" + in + "}").json;
    };
    const auto ones = [](std::size_t n, const char* v) {
        std::string s = "[";
        for (std::size_t i = 0; i < n; ++i) s += (i ? "," : "") + std::string(v);
        return s + "]";
    };
    // J-20: 100,001 bars is a valid run (page limit 1,000,000, not the general 100,000).
    const std::string p = ones(100001, "1");
    CHECK(run("research.backtest.run", R"({"prices":)" + p + R"(,"targets":)" + p + "}").find(R"("status":"ok")") != std::string::npos);
    CHECK(run("research.cv.purged_kfold", R"({"t0":)" + p + R"(,"t1":)" + p + R"(,"n_splits":2})").find(R"("status":"ok")") != std::string::npos);
    CHECK(run("research.regime.viterbi", R"({"initial":[1],"transition":[[1]],"observations":)" + p + R"(,"means":[0],"sds":[1]})").find("E_LIMIT") != std::string::npos);
    // J-21
    CHECK(run("research.stats.power", R"({"years":4,"alpha":0,"power":0.8})").find("E_DOMAIN") != std::string::npos);
    CHECK(run("research.stats.power", R"({"years":4,"alpha":0.05,"power":1})").find("E_DOMAIN") != std::string::npos);
    // J-22
    CHECK(run("research.regime.viterbi", R"({"initial":[1],"transition":[[1]],"emission":[]})").find("E_INPUT") != std::string::npos);
    CHECK(run("research.regime.viterbi", R"({"initial":[1],"transition":[[1]],"observations":[],"means":[0],"sds":[1]})").find("E_INPUT") != std::string::npos);
    // J-23: strategy 1 is flat in block 0 only; the combined samples are not flat, the block check still fires.
    CHECK(run("research.stats.pbo", R"({"performance":[[1,5],[2,5],[3,1],[4,2]],"n_partitions":2})").find("E_DOMAIN") != std::string::npos);
    CHECK(run("research.stats.pbo", R"({"performance":[[1,5],[2,6],[3,1],[4,2]],"n_partitions":2})").find(R"("status":"ok")") != std::string::npos);
}
