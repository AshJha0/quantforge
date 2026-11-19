// H-5 p50/p99 harness (specifications/10-execution/library-interfaces.md section 3), C++ entries. Not a test; built
// only with -DQF_H5_BENCH=ON (no download). Run as `qf_h5_latency [machine label]`; prints one JSON object.
// Same workloads as java25/.../bench/H5Latency.java, including its two marked deviations (B1*: the unjittered
// 13-quote example; B2*: one 5Y PAY trade). B4 is not run here.
// Thread safety: not safe to share; single-threaded main.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <functional>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "quantforge/core/black.hpp"
#include "quantforge/core/exec_api.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/rates.hpp"

#ifndef QF_REPO_ROOT
#define QF_REPO_ROOT "."
#endif

namespace qf = quantforge;
namespace api = quantforge::exec_api;
using Clock = std::chrono::steady_clock;

namespace {
volatile double g_sink = 0;  // result sink: every result feeds it, so the optimiser cannot drop the call

double ns(Clock::time_point a, Clock::time_point b) {
    return (double)std::chrono::duration_cast<std::chrono::nanoseconds>(b - a).count();
}

double rank(const std::vector<double>& sorted, double q) {
    return sorted[(std::size_t)std::ceil(q * (double)sorted.size()) - 1];  // nearest rank
}

struct Row {
    std::string id;
    double p50, p99;
    int batch;
};

Row run(const std::string& id, const std::function<double()>& f, int n, int batch) {
    std::vector<double> p50, p99;
    for (int r = 0; r < 5; ++r) {
        double acc = 0;
        for (int i = 0; i < 20000; ++i) acc += f();  // warm-up, as the Java harness
        std::vector<double> t((std::size_t)n);
        for (int i = 0; i < n; ++i) {
            const auto a = Clock::now();
            for (int j = 0; j < batch; ++j) acc += f();
            t[(std::size_t)i] = ns(a, Clock::now());
        }
        g_sink = g_sink + acc;
        std::sort(t.begin(), t.end());
        p50.push_back(rank(t, 0.50) / batch);
        p99.push_back(rank(t, 0.99) / batch);
    }
    std::sort(p50.begin(), p50.end());
    std::sort(p99.begin(), p99.end());
    return {id, p50[2], p99[2], batch};
}
}  // namespace

int main(int argc, char** argv) {
    const std::string machine = argc > 1 ? argv[1] : "unlabelled machine, not the acceptance machine";
    std::mt19937_64 rng(20261118);
    std::uniform_real_distribution<double> u(0.0, 1.0);
    std::vector<double> profile(390);
    for (double& w : profile) w = 0.5 + u(rng);
    const api::AcParams ac(1e6, 5, 100, 0.95, 0.0625, 2.5e-6, 2.5e-7);
    std::vector<api::Fill> fills;
    double fx = 0;
    for (int i = 0; i < 1000; ++i) {
        const double q = 1 + std::floor(u(rng) * 100);
        fills.emplace_back(q, 100 + u(rng));
        fx += q;
    }

    std::ifstream file(QF_REPO_ROOT "/examples/ois_bootstrap_sofr.json", std::ios::binary);
    if (!file) throw std::runtime_error("cannot open examples/ois_bootstrap_sofr.json");
    std::stringstream ss;
    ss << file.rdbuf();
    const auto doc = qf::json::parse(ss.str());
    const auto& in = *doc.value.find("inputs");
    const qf::RateConvention* conv = qf::rate_convention(in.find("convention")->text);
    const qf::Date as_of = *qf::parse_date(in.find("as_of")->text);
    std::vector<qf::OisQuote> quotes;
    for (const auto& q : in.find("quotes")->items) {
        const std::string& t = q.find("tenor")->text;
        quotes.push_back({qf::Tenor{std::stoi(t.substr(0, t.size() - 1)), t.back()}, q.find("rate")->number});
    }
    const auto interp = qf::CurveInterpolation::LogLinearDf;
    const auto method = qf::SolveMethod::Sequential;
    const auto solved = qf::ois_bootstrap(*conv, as_of, quotes, interp, method);
    const qf::OisTrade trade{conv, qf::Tenor{5, 'Y'}, 0.035, 1'000'000.0, qf::FixedSide::Pay};
    qf::OptionInput opt{};
    opt.model = qf::VolModel::Black76;
    opt.type = qf::OptionType::Call;
    opt.strike = 105.0;
    opt.expiry_years = 1.0;
    opt.forward = 100.0;
    opt.discount_factor = 1.0;
    const double price = qf::option_price(opt, 0.2);

    std::vector<double> clock(10000);
    for (double& c : clock) {
        const auto a = Clock::now();
        c = ns(a, Clock::now());
    }
    std::sort(clock.begin(), clock.end());

    const std::vector<Row> rows{
        run("E1", [] { return api::twap(1'000'003, 100, api::FillMode::Units).slices()[0]; }, 100000, 1),
        run("E2", [&] { return api::vwap(1'000'003, profile, api::FillMode::Units).slices()[0]; }, 100000, 1),
        run("E3", [&] { return api::ac_trajectory(ac, 1e-6).objective(); }, 100000, 1),
        run("E4", [&] { return api::shortfall(api::Side::Buy, 100, 100.2, 100.5, fx, fills, 0, 100.4).total(); },
            100000, 1),
        run("E5", [] { return api::as_quotes(100, 3, 0.1, 2, 0.5, 1.5).bid(); }, 100000, 100),
        run("E6", [] { return api::impact_sqrt(1e5, 1e7, 0.02, 0.5); }, 100000, 100),
        run("B1*", [&] { return qf::ois_bootstrap(*conv, as_of, quotes, interp, method).max_repricing_error; },
            10000, 1),
        run("B2*", [&] { return qf::ois_price(trade, solved.curve).valuation.pv; }, 100000, 1),
        run("B3", [&] { return qf::implied_vol(opt, price); }, 100000, 1),
    };

    std::printf("{\"machine\":\"%s\",\"language\":\"C++\",\"clock\":\"std::chrono::steady_clock\","
                "\"clock_overhead_ns_p50\":%.1f,\"unit\":\"ns per call, median of 5 repeats\",\"rows\":[",
                machine.c_str(), clock[5000]);
    for (std::size_t i = 0; i < rows.size(); ++i)
        std::printf("%s{\"id\":\"%s\",\"p50\":%.1f,\"p99\":%.1f,\"batch\":%d}", i ? "," : "", rows[i].id.c_str(),
                    rows[i].p50, rows[i].p99, rows[i].batch);
    std::printf("],\"sink\":%s}\n", g_sink != 0 ? "true" : "false");
}
