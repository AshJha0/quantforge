#pragma once
// Sensitivity-based IR delta margin of the stage G xVA layer, operation `xva.sbim.ir_delta`
// (specifications/06-risk/xva-framework.md, ruling G-43; renamed by KR-152, the old id `xva.simm.ir_delta` is a
// deprecated alias that runs this same function until v1.0.0). Weights and correlations are caller inputs; the
// goldens feed it specifications/tables/stage_k/sbim-ir-delta-g.json (placeholder weights, KR-150).
// Before KR-153 this computation lived inside the CLI handler; it is now the library function the name map names.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <vector>

#include "quantforge/core/error.hpp"

namespace quantforge::xva {

struct SbimIrDelta {
    std::vector<double> weighted_sensitivities;
    double concentration_factor = 1.0;
    double margin = 0.0;
};

/// `CR = max(1, sqrt(|sum s| / T))`, `WS_k = RW_k s_k CR`, `margin = sqrt(max(0, sum_k sum_l rho_kl WS_k WS_l))`
/// with `rho_kk = 1`. Checks, in this order: lengths (E_INPUT), risk weights >= 0, correlations in [-1, 1],
/// threshold > 0 (E_DOMAIN). Non-finite inputs are rejected by the caller's F-2 gate before this is called.
inline SbimIrDelta sbim_ir_delta(const std::vector<double>& s, const std::vector<double>& rw,
                                 const std::vector<std::vector<double>>& rho, double threshold) {
    const std::size_t n = s.size();
    if (n == 0 || rw.size() != n || rho.size() != n) throw Error("E_INPUT", "lengths differ", "risk_weights");
    for (const auto& r : rho)
        if (r.size() != n) throw Error("E_INPUT", "correlations is not square", "correlations");
    for (double x : rw)
        if (!(x >= 0)) throw Error("E_DOMAIN", "a risk weight is negative", "risk_weights");
    for (const auto& r : rho)
        for (double x : r)
            if (!(x >= -1 && x <= 1)) throw Error("E_DOMAIN", "a correlation is outside [-1, 1]", "correlations");
    if (!(threshold > 0))
        throw Error("E_DOMAIN", "concentration_threshold is not positive", "concentration_threshold");
    double net = 0.0;
    for (double x : s) net += x;
    SbimIrDelta out;
    out.concentration_factor = std::max(1.0, std::sqrt(std::fabs(net) / threshold));
    out.weighted_sensitivities.resize(n);
    for (std::size_t k = 0; k < n; ++k) out.weighted_sensitivities[k] = rw[k] * s[k] * out.concentration_factor;
    const auto& ws = out.weighted_sensitivities;
    double m = 0.0;
    for (std::size_t k = 0; k < n; ++k)
        for (std::size_t l = 0; l < n; ++l) m += (k == l ? 1.0 : rho[k][l]) * ws[k] * ws[l];
    out.margin = std::sqrt(std::max(0.0, m));
    return out;
}

}  // namespace quantforge::xva
