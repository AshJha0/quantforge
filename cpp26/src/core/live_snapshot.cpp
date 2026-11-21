// Stage K, K-5 (KR-283, KR-287, confirmed 2026-11-20): the writer's per-publish hedge computation. Latency-aware analytics on
// simulated data.
#include "quantforge/core/live_snapshot.hpp"

#include <cmath>

#include "quantforge/core/research.hpp"

namespace quantforge::live {

double book_delta(const std::vector<stage_k::ZeroPosition>& positions, double shift) {
    std::vector<double> terms;
    terms.reserve(positions.size());
    for (const auto& p : positions) terms.push_back(-p.maturity * (p.notional * std::exp(-(p.yield + shift) * p.maturity)));
    return research::fsum(terms);
}

double hedge_unit_delta(const HedgeInstrument& hedge, double shift) {
    return -hedge.maturity * std::exp(-(hedge.yield + shift) * hedge.maturity);
}

HedgeSnapshot build(std::uint64_t version, std::uint64_t as_of, const std::vector<stage_k::ZeroPosition>& positions,
                    const HedgeInstrument& hedge, double shift) {
    const auto risk = stage_k::delta_gamma_bound(positions, shift);
    const double d = book_delta(positions, shift);
    const double u = hedge_unit_delta(hedge, shift);
    HedgeSnapshot s{version, as_of, shift, risk.estimate_pnl, risk.bound, d, u, -d / u, 0};
    const auto w = s.words();
    s.check = checksum(w.data(), w.size());
    return s;
}

double scenario_shift(std::uint64_t k) {
    if (k == 0) return 0.0;
    const auto m = static_cast<std::int64_t>((k * 7919u) % 401u) - 200;
    return static_cast<double>(m) * 5e-5;
}

}  // namespace quantforge::live
