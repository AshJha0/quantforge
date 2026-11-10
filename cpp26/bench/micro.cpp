// G2 microbenchmarks: bootstrap, swap_pv, implied_vol. Built only with -DQF_BENCH=ON.
// QF_BENCH_INJECT_NS=<n> adds an n-ns busy wait to each timed op (proves the regression gate fails).
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <new>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <benchmark/benchmark.h>

#include "quantforge/core/black.hpp"
#include "quantforge/core/json.hpp"
#include "quantforge/core/rates.hpp"

#ifndef QF_REPO_ROOT
#define QF_REPO_ROOT "."
#endif

// ---- allocation counting ----
static std::atomic<long long> g_allocs{0};

void* operator new(std::size_t n) {
    g_allocs.fetch_add(1, std::memory_order_relaxed);
    if (void* p = std::malloc(n ? n : 1)) return p;
    throw std::bad_alloc();
}
void* operator new[](std::size_t n) { return ::operator new(n); }
void* operator new(std::size_t n, const std::nothrow_t&) noexcept {
    g_allocs.fetch_add(1, std::memory_order_relaxed);
    return std::malloc(n ? n : 1);
}
void* operator new[](std::size_t n, const std::nothrow_t& t) noexcept { return ::operator new(n, t); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }
void operator delete(void* p, const std::nothrow_t&) noexcept { std::free(p); }
void operator delete[](void* p, const std::nothrow_t&) noexcept { std::free(p); }

namespace qf = quantforge;

namespace {

long long inject_ns() {
    static const long long ns = [] {
        const char* s = std::getenv("QF_BENCH_INJECT_NS");
        if (!s || !*s) return 0LL;
        char* end = nullptr;
        long long v = std::strtoll(s, &end, 10);
        return (end && *end == '\0' && v > 0) ? v : 0LL;
    }();
    return ns;
}

inline void spin() {
    const long long ns = inject_ns();
    if (ns <= 0) return;
    const auto until = std::chrono::steady_clock::now() + std::chrono::nanoseconds(ns);
    while (std::chrono::steady_clock::now() < until) {
    }
}

struct OisSetup {
    const qf::RateConvention* conv;
    qf::Date as_of;
    std::vector<qf::OisQuote> quotes;
    qf::CurveInterpolation interp;
    qf::SolveMethod method;
};

// Parsed once, outside any timed loop, from examples/ois_bootstrap_sofr.json with the library's JSON reader.
const OisSetup& ois_setup() {
    static const OisSetup s = [] {
        std::ifstream f(QF_REPO_ROOT "/examples/ois_bootstrap_sofr.json", std::ios::binary);
        if (!f) throw std::runtime_error("cannot open examples/ois_bootstrap_sofr.json");
        std::stringstream ss;
        ss << f.rdbuf();
        const auto doc = qf::json::parse(ss.str());
        const auto& in = *doc.value.find("inputs");
        OisSetup o{};
        o.conv = qf::rate_convention(in.find("convention")->text);
        o.as_of = *qf::parse_date(in.find("as_of")->text);
        for (const auto& q : in.find("quotes")->items) {
            const std::string& t = q.find("tenor")->text;
            o.quotes.push_back({qf::Tenor{std::stoi(t.substr(0, t.size() - 1)), t.back()}, q.find("rate")->number});
        }
        o.interp = in.find("interpolation")->text == "LINEAR_ZERO" ? qf::CurveInterpolation::LinearZero
                                                                   : qf::CurveInterpolation::LogLinearDf;
        o.method = in.find("method")->text == "GLOBAL" ? qf::SolveMethod::Global : qf::SolveMethod::Sequential;
        return o;
    }();
    return s;
}

qf::SolvedCurve build_curve() {
    const auto& s = ois_setup();
    return qf::ois_bootstrap(*s.conv, s.as_of, s.quotes, s.interp, s.method);
}

void report_allocs(benchmark::State& state, long long before) {
    const long long n = g_allocs.load(std::memory_order_relaxed) - before;
    state.counters["allocs_per_op"] =
        benchmark::Counter(state.iterations() ? double(n) / double(state.iterations()) : 0.0);
}

void bootstrap(benchmark::State& state) {
    (void)ois_setup();
    const long long before = g_allocs.load();
    for (auto _ : state) {
        auto c = build_curve();
        benchmark::DoNotOptimize(c.max_repricing_error);
        spin();
    }
    report_allocs(state, before);
}

void swap_pv(benchmark::State& state) {
    const auto solved = build_curve();
    const qf::OisTrade trade{ois_setup().conv, qf::Tenor{5, 'Y'}, 0.035, 10'000'000.0, qf::FixedSide::Pay};
    const long long before = g_allocs.load();
    for (auto _ : state) {
        auto p = qf::ois_price(trade, solved.curve);
        benchmark::DoNotOptimize(p.valuation.pv);
        spin();
    }
    report_allocs(state, before);
}

void implied_vol(benchmark::State& state) {
    qf::OptionInput in{};
    in.model = qf::VolModel::Black76;
    in.type = qf::OptionType::Call;
    in.strike = 105.0;
    in.expiry_years = 1.0;
    in.forward = 100.0;
    in.discount_factor = 1.0;
    const double price = qf::option_price(in, 0.2);
    const long long before = g_allocs.load();
    for (auto _ : state) {
        double p = price;
        benchmark::DoNotOptimize(p);
        double v = qf::implied_vol(in, p);
        benchmark::DoNotOptimize(v);
        spin();
    }
    report_allocs(state, before);
}

}  // namespace

BENCHMARK(bootstrap);
BENCHMARK(swap_pv);
BENCHMARK(implied_vol);

BENCHMARK_MAIN();
