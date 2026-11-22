#pragma once
// Reverse-mode (adjoint) sensitivities of the G-41 valuation adjustments, written by hand
// (specifications/06-risk/xva-aad-adjustments.md, rulings KR-262 to KR-268). Port of
// python/quantforge_core/xva_aad.py: the same backward pass, bucket by bucket from the first.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "quantforge/core/error.hpp"

namespace quantforge::xva_aad {

using Vec = std::vector<double>;

/// A validated G-41 request (lengths and domains checked by the caller); `im` and `capital` are empty when absent.
struct Request {
    Vec t, df, ee, ene;
    double hc = 0, rc = 0, hb = 0, rb = 0, sb = 0, sl = 0;
    bool exclude_overlap = false;
    bool has_im = false, has_capital = false;
    Vec im;
    double im_spread = 0;
    Vec capital;
    double hurdle = 0;
};

/// One gradient entry: a scalar, or one value per bucket.
struct Entry {
    std::string key;
    bool scalar = true;
    double s = 0.0;
    Vec v;
};

using Gradient = std::vector<Entry>;

/// Keys in canonical order (KR-263): the base keys, then im and capital when given.
inline std::vector<std::string> keys(bool has_im, bool has_capital) {
    std::vector<std::string> k = {"counterparty.hazard_rate", "counterparty.hazard_buckets", "counterparty.recovery",
                                  "own.hazard_rate", "own.hazard_buckets", "own.recovery", "discount_factors", "ee",
                                  "ene", "funding.borrow_spread", "funding.lend_spread"};
    if (has_im) k.insert(k.end(), {"im", "im_spread"});
    if (has_capital) k.insert(k.end(), {"capital", "hurdle_rate"});
    return k;
}

/// KR-267 step 4: the reported keys in canonical order; E_INPUT for an empty, repeating or unknown wrt.
inline std::vector<std::string> check_wrt(const std::optional<std::vector<std::string>>& wrt,
                                          const std::vector<std::string>& allowed) {
    if (!wrt) return allowed;
    if (wrt->empty()) throw Error("E_INPUT", "wrt is empty", "wrt");
    for (std::size_t i = 0; i < wrt->size(); ++i) {
        const std::string& k = (*wrt)[i];
        if (std::find(wrt->begin(), wrt->begin() + static_cast<std::ptrdiff_t>(i), k) !=
            wrt->begin() + static_cast<std::ptrdiff_t>(i))
            throw Error("E_INPUT", "wrt names a key twice", "wrt");
        if (std::find(allowed.begin(), allowed.end(), k) == allowed.end())
            throw Error("E_INPUT", "wrt names a key that is not differentiated", "wrt");
    }
    std::vector<std::string> out;
    for (const auto& a : allowed)
        if (std::find(wrt->begin(), wrt->end(), a) != wrt->end()) out.push_back(a);
    return out;
}

namespace detail {

struct Bar {
    Vec sc, sb, pc, pb, df, ee, ene, prof, hb_direct;
    double rc = 0, rb = 0, spread = 0;
    explicit Bar(std::size_t n)
        : sc(n + 1), sb(n + 1), pc(n), pb(n), df(n), ee(n), ene(n), prof(n), hb_direct(n) {}
};

struct Tape {
    std::size_t n;
    Vec t, dt, df, sc, sb, bc, bb, w;
    explicit Tape(const Request& r) : n(r.t.size()), t(n + 1), dt(n), df(r.df), sc(n + 1), sb(n + 1), bc(n), bb(n), w(n) {
        for (std::size_t i = 0; i < n; ++i) t[i + 1] = r.t[i];
        for (std::size_t k = 0; k <= n; ++k) {
            sc[k] = std::exp(-r.hc * t[k]);
            sb[k] = std::exp(-r.hb * t[k]);
        }
        for (std::size_t i = 0; i < n; ++i) {
            dt[i] = r.t[i] - t[i];
            bc[i] = sc[i] * -std::expm1(-r.hc * dt[i]);  // cancellation free (PT-6)
            bb[i] = sb[i] * -std::expm1(-r.hb * dt[i]);
            w[i] = df[i] * sc[i] * sb[i] * dt[i];
        }
    }
    void through_w(Bar& bar, std::size_t i, double gw) const {
        bar.df[i] += gw * sc[i] * sb[i] * dt[i];
        bar.sc[i] += gw * df[i] * sb[i] * dt[i];
        bar.sb[i] += gw * df[i] * sc[i] * dt[i];
    }
};

inline Bar cva(const Tape& tp, const Request& r) {
    Bar bar(tp.n);
    const double lc = 1 - r.rc;
    for (std::size_t i = 0; i < tp.n; ++i) {
        const double b = tp.bc[i], e = r.ee[i];
        bar.rc -= tp.df[i] * e * b * tp.sb[i];
        bar.df[i] += lc * e * b * tp.sb[i];
        bar.ee[i] += lc * tp.df[i] * b * tp.sb[i];
        bar.pc[i] += lc * tp.df[i] * e * tp.sb[i];
        bar.sb[i] += lc * tp.df[i] * e * b;
    }
    return bar;
}

inline Bar dva(const Tape& tp, const Request& r) {
    Bar bar(tp.n);
    const double lb = 1 - r.rb;
    for (std::size_t i = 0; i < tp.n; ++i) {
        const double x = -r.ene[i], b = tp.bb[i];
        bar.rb -= tp.df[i] * x * b * tp.sc[i];
        bar.df[i] += lb * x * b * tp.sc[i];
        bar.ene[i] -= lb * tp.df[i] * b * tp.sc[i];
        bar.pb[i] += lb * tp.df[i] * x * tp.sc[i];
        bar.sc[i] += lb * tp.df[i] * x * b;
    }
    return bar;
}

// FCA (to_ee), MVA and KVA: coef sum W_i x_i.
inline Bar funding(const Tape& tp, double coef, const Vec& prof, bool to_ee) {
    Bar bar(tp.n);
    for (std::size_t i = 0; i < tp.n; ++i) {
        (to_ee ? bar.ee : bar.prof)[i] += coef * tp.w[i];
        bar.spread += tp.w[i] * prof[i];
        tp.through_w(bar, i, coef * prof[i]);
    }
    return bar;
}

// FBA; branch 0: no overlap rule, 1: linear branch, -1: the floor (KR-264).
inline Bar fba(const Tape& tp, const Request& r, int branch) {
    Bar bar(tp.n);
    const double lb = 1 - r.rb;
    const double coef = branch == 0 ? r.sl : (branch > 0 ? r.sl - r.hb * lb : 0.0);
    for (std::size_t i = 0; i < tp.n; ++i) {
        const double x = -r.ene[i];
        bar.ene[i] -= coef * tp.w[i];
        const double g = tp.w[i] * x;
        if (branch >= 0) bar.spread += g;
        if (branch > 0) {
            bar.rb += g * r.hb;
            bar.hb_direct[i] -= g * lb;
        }
        tp.through_w(bar, i, coef * x);
    }
    return bar;
}

// Survival adjoints to hazard adjoints: flat, then the buckets (spec, backward pass; the bucket difference is
// kept whole so that a zero difference gives an exact zero).
inline std::pair<double, Vec> hazards(const Vec& s, const Vec& gs, const Vec& b, const Vec& gp, const Vec& t,
                                      const Vec& dt) {
    const std::size_t n = dt.size();
    double single = 0.0, pairs = 0.0;
    for (std::size_t k = 0; k <= n; ++k) single += gs[k] * t[k] * s[k];
    for (std::size_t i = 0; i < n; ++i) pairs += gp[i] * (t[i] * b[i] - dt[i] * s[i + 1]);
    Vec buckets(n);
    double tail = 0.0;
    for (std::size_t j = n; j-- > 0;) {
        tail += gs[j + 1] * s[j + 1];
        buckets[j] = -dt[j] * (tail - gp[j] * s[j + 1]);
        tail += gp[j] * b[j];
    }
    return {-single - pairs, buckets};
}

inline Gradient gradient_of(const Tape& tp, const Bar& bar, std::string_view spread_key, std::string_view prof_key) {
    auto [hc, hc_b] = hazards(tp.sc, bar.sc, tp.bc, bar.pc, tp.t, tp.dt);
    auto [hb, hb_b] = hazards(tp.sb, bar.sb, tp.bb, bar.pb, tp.t, tp.dt);
    double direct = 0.0;
    for (std::size_t i = 0; i < tp.n; ++i) {
        direct += bar.hb_direct[i];
        hb_b[i] += bar.hb_direct[i];
    }
    auto sc = [](std::string k, double v) { return Entry{std::move(k), true, v, {}}; };
    auto pr = [](std::string k, Vec v) { return Entry{std::move(k), false, 0.0, std::move(v)}; };
    const Vec zero(tp.n, 0.0);
    auto spread = [&](const char* k) { return sc(k, spread_key == k ? bar.spread : 0.0); };
    auto prof = [&](const char* k) { return pr(k, prof_key == k ? bar.prof : zero); };
    return {sc("counterparty.hazard_rate", hc),
            pr("counterparty.hazard_buckets", hc_b),
            sc("counterparty.recovery", bar.rc),
            sc("own.hazard_rate", hb + direct),
            pr("own.hazard_buckets", hb_b),
            sc("own.recovery", bar.rb),
            pr("discount_factors", bar.df),
            pr("ee", bar.ee),
            pr("ene", bar.ene),
            spread("funding.borrow_spread"),
            spread("funding.lend_spread"),
            prof("im"),
            spread("im_spread"),
            prof("capital"),
            spread("hurdle_rate")};
}

inline Gradient minus(const Gradient& a, const Gradient& b) {
    Gradient out = a;
    for (std::size_t k = 0; k < a.size(); ++k) {
        out[k].s = a[k].s - b[k].s;
        for (std::size_t i = 0; i < a[k].v.size(); ++i) out[k].v[i] = a[k].v[i] - b[k].v[i];
    }
    return out;
}

}  // namespace detail

/// The gradient of every output of a validated request, restricted to `names` (canonical order):
/// (output name, gradient) in output order.
inline std::vector<std::pair<std::string, Gradient>> gradient(const Request& r, const std::vector<std::string>& names) {
    using namespace detail;
    const Tape tp(r);
    const int branch = !r.exclude_overlap ? 0 : (r.sl - r.hb * (1 - r.rb) >= 0 ? 1 : -1);
    const Gradient fca = gradient_of(tp, funding(tp, r.sb, r.ee, true), "funding.borrow_spread", "");
    const Gradient fb = gradient_of(tp, fba(tp, r, branch), "funding.lend_spread", "");
    std::vector<std::pair<std::string, Gradient>> raw = {{"cva", gradient_of(tp, cva(tp, r), "", "")},
                                                         {"dva", gradient_of(tp, dva(tp, r), "", "")},
                                                         {"fca", fca},
                                                         {"fba", fb},
                                                         {"fva", minus(fca, fb)}};
    if (r.has_im) raw.emplace_back("mva", gradient_of(tp, funding(tp, r.im_spread, r.im, false), "im_spread", "im"));
    if (r.has_capital)
        raw.emplace_back("kva", gradient_of(tp, funding(tp, r.hurdle, r.capital, false), "hurdle_rate", "capital"));
    for (auto& [o, g] : raw) {
        Gradient kept;
        for (auto& e : g)
            if (std::find(names.begin(), names.end(), e.key) != names.end()) kept.push_back(std::move(e));
        g = std::move(kept);
    }
    return raw;
}

}  // namespace quantforge::xva_aad
