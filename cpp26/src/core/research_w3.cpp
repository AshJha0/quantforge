// Stage J wave 3 (rulings J-W3-1 to J-W3-14): the scenario stress engine (06-risk/scenario-stress.md),
// the interpolation backtests (11-research/interp-backtest.md) and the drift detectors
// (11-research/drift-detectors.md). Inputs are already finite (the CLI's E1 check).
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdlib>
#include <limits>
#include <string>

#include "quantforge/core/error.hpp"
#include "quantforge/core/interp.hpp"
#include "quantforge/core/research.hpp"

namespace quantforge::research {
namespace {

using Vec = std::vector<double>;

[[noreturn]] void input(const std::string& why, const std::string& field = {}) { throw Error("E_INPUT", why, field); }
[[noreturn]] void domain(const std::string& why, const std::string& field = {}) { throw Error("E_DOMAIN", why, field); }

bool increasing(const Vec& x) {
    for (std::size_t i = 1; i < x.size(); ++i)
        if (!(x[i] > x[i - 1])) return false;
    return true;
}

void tenors(const Vec& t, const char* field) {
    bool ok = increasing(t);
    for (const double v : t) ok = ok && v > 0;
    if (!ok) domain(std::string(field) + " must be positive and strictly increasing", field);
}

double flat_linear(const Vec& x, const Vec& y, double t) {
    const std::size_t l = x.size() - 1;
    if (t <= x[0]) return y[0];
    if (t >= x[l]) return y[l];
    const std::size_t i = static_cast<std::size_t>(std::upper_bound(x.begin(), x.end(), t) - x.begin()) - 1;
    const double u = (t - x[i]) / (x[i + 1] - x[i]);
    return y[i] + u * (y[i + 1] - y[i]);
}

InterpMethod interp_method(int m) {
    switch (m) {
        case 0: return InterpMethod::Linear;
        case 1: return InterpMethod::LogLinear;
        case 2: return InterpMethod::CubicNatural;
        default: return InterpMethod::MonotonePchip;
    }
}

std::size_t min_knots(int m) { return m == 2 ? 3 : 2; }

void summary(const Vec& e, double& mx, double& rmse) {
    mx = 0;
    Vec sq;
    sq.reserve(e.size());
    for (const double v : e) {
        mx = std::max(mx, std::fabs(v));
        sq.push_back(v * v);
    }
    rmse = std::sqrt(fsum(sq) / static_cast<double>(e.size()));
}

}  // namespace

double fsum(const std::vector<double>& v) {
    Vec p;
    for (double x : v) {
        std::size_t k = 0;
        for (double y : p) {
            if (std::fabs(x) < std::fabs(y)) std::swap(x, y);
            const double hi = x + y;
            const double lo = y - (hi - x);
            if (lo != 0.0) p[k++] = lo;
            x = hi;
        }
        p.resize(k);
        p.push_back(x);
    }
    if (p.empty()) return 0.0;
    std::size_t n = p.size();
    double hi = p[--n], lo = 0.0;
    while (n > 0) {
        const double x = hi, y = p[--n];
        hi = x + y;
        lo = y - (hi - x);
        if (lo != 0.0) break;
    }
    if (n > 0 && ((lo < 0 && p[n - 1] < 0) || (lo > 0 && p[n - 1] > 0))) {
        const double y = lo * 2.0, x = hi + y;
        if (y == x - hi) hi = x;
    }
    return hi;
}

// ---- scenarios (J-W3-2 to J-W3-5) ----

Shock historical_shock(const std::vector<long long>& dates, const Vec& t, const Matrix2& yields, long long start,
                       long long end) {
    const std::size_t n = t.size();
    bool bad = dates.empty() || n == 0 || yields.size() != dates.size();
    for (const Vec& r : yields) bad = bad || r.size() != n;
    if (bad) input("need one row per date and one column per tenor", "yields");
    for (std::size_t i = 1; i < dates.size(); ++i)
        if (dates[i] <= dates[i - 1]) throw Error("E_DATE_ORDER", "dates must be strictly increasing", "dates");
    tenors(t, "tenors");
    if (end <= start) throw Error("E_DATE_ORDER", "end_date must be after start_date", "end_date");
    const auto find = [&](long long d, const char* f) {
        const auto it = std::lower_bound(dates.begin(), dates.end(), d);
        if (it == dates.end() || *it != d) domain(std::string(f) + " is not in dates", f);
        return static_cast<std::size_t>(it - dates.begin());
    };
    const std::size_t a = find(start, "start_date"), b = find(end, "end_date");
    Shock s{yields[a], yields[b], Vec(n), 0, 0};
    for (std::size_t i = 0; i < n; ++i) s.shift_bp[i] = 100.0 * (s.end_yields[i] - s.start_yields[i]);
    s.level_bp = fsum(s.shift_bp) / static_cast<double>(n);
    s.slope_bp = s.shift_bp[n - 1] - s.shift_bp[0];
    return s;
}

Replay replay(const Vec& bt, const Vec& by, const Vec& st, const Vec& sb, double scale,
              const std::optional<Vec>& dv01) {
    if (bt.empty() || by.size() != bt.size()) input("base_yields must match base_tenors", "base_yields");
    if (st.empty() || sb.size() != st.size()) input("shock_bp must match shock_tenors", "shock_bp");
    if (dv01 && dv01->size() != bt.size()) input("dv01 must match base_tenors", "dv01");
    tenors(bt, "base_tenors");
    tenors(st, "shock_tenors");
    Replay r;
    for (std::size_t i = 0; i < bt.size(); ++i) {
        r.applied_bp.push_back(scale * flat_linear(st, sb, bt[i]));
        r.shocked_yields.push_back(by[i] + r.applied_bp[i] / 100.0);
    }
    if (dv01) {
        Vec t;
        for (std::size_t i = 0; i < bt.size(); ++i) t.push_back((*dv01)[i] * r.applied_bp[i]);
        r.pnl = -fsum(t);
    }
    return r;
}

// ---- interpolation backtests (J-W3-8, J-W3-9) ----

LooBacktest interp_loo(int method, const Vec& x, const Vec& y) {
    const std::size_t n = x.size();
    if (y.size() != n || n < 3 || n - 1 < min_knots(method))
        input("need equal lengths, n >= 3 and n - 1 at the method's minimum knots", "x");
    if (!increasing(x)) input("knots must be strictly increasing", "x");
    LooBacktest r;
    for (std::size_t i = 1; i + 1 < n; ++i) {
        Vec xs, ys;
        for (std::size_t j = 0; j < n; ++j)
            if (j != i) {
                xs.push_back(x[j]);
                ys.push_back(y[j]);
            }
        r.errors.push_back(interpolate(interp_method(method), xs, ys, {x[i]}).values[0] - y[i]);
    }
    summary(r.errors, r.max_abs_error, r.rmse);
    return r;
}

SurfaceBacktest surface_holdout(int method, const Vec& expiries, const Vec& strikes, const Matrix2& vols,
                                const std::vector<long long>& holdout) {
    const std::size_t m = strikes.size();
    bool bad = expiries.empty() || vols.size() != expiries.size();
    for (const Vec& r : vols) bad = bad || r.size() != m;
    if (bad) input("vols must have one row per expiry and one column per strike", "vols");
    if (!increasing(strikes)) input("strikes must be strictly increasing", "strikes");
    bool bad_hold = holdout.empty();
    for (std::size_t i = 0; i < holdout.size(); ++i)
        bad_hold = bad_hold || !(holdout[i] > 0 && holdout[i] < static_cast<long long>(m) - 1) ||
                   (i > 0 && holdout[i] <= holdout[i - 1]);
    if (bad_hold) input("holdout must be distinct sorted interior strike indices", "holdout");
    std::vector<bool> held(m, false);
    for (const long long h : holdout) held[static_cast<std::size_t>(h)] = true;
    Vec ks, at;
    for (std::size_t j = 0; j < m; ++j)
        if (!held[j]) ks.push_back(strikes[j]);
    for (const long long h : holdout) at.push_back(strikes[static_cast<std::size_t>(h)]);
    if (ks.size() < min_knots(method)) input("too few kept strikes for the method", "holdout");
    for (const double t : expiries)
        if (!(t > 0)) domain("expiries must be positive", "expiries");
    for (const Vec& r : vols)
        for (const double v : r)
            if (!(v > 0)) domain("vols must be positive", "vols");
    SurfaceBacktest r;
    Vec flat;
    for (std::size_t e = 0; e < expiries.size(); ++e) {
        const double t = expiries[e];
        Vec w;
        for (std::size_t j = 0; j < m; ++j)
            if (!held[j]) w.push_back(vols[e][j] * vols[e][j] * t);
        const Vec fit = interpolate(interp_method(method), ks, w, at).values;
        for (const double v : fit)
            if (!(v > 0)) domain("interpolated total variance is not positive", "vols");
        Vec row;
        for (std::size_t h = 0; h < holdout.size(); ++h) {
            row.push_back(std::sqrt(fit[h] / t) - vols[e][static_cast<std::size_t>(holdout[h])]);
            flat.push_back(row.back());
        }
        r.errors.push_back(row);
    }
    summary(flat, r.max_abs_error, r.rmse);
    return r;
}

// ---- drift detectors (J-W3-10 to J-W3-13) ----

Alarms cusum(const Vec& x, double k, double h, double mu0, double sigma, bool reset) {
    if (x.empty()) input("x must not be empty", "x");
    if (!(k > 0) || !(h > 0) || !(sigma > 0)) domain("k, h and sigma must be positive", "k");
    Alarms a;
    double sp = 0, sm = 0;
    for (std::size_t t = 0; t < x.size(); ++t) {
        const double z = (x[t] - mu0) / sigma;
        sp = std::max(0.0, sp + z - k);
        sm = std::max(0.0, sm - z - k);
        if (sp > h || sm > h) {
            a.alarms.push_back(static_cast<long long>(t));
            a.directions.push_back(sp > h ? 1 : -1);
            if (!reset) break;
            sp = sm = 0;
        }
    }
    a.s_plus = sp;
    a.s_minus = sm;
    return a;
}

Alarms page_hinkley(const Vec& x, double delta, double lambda, int direction, bool reset) {
    if (x.empty()) input("x must not be empty", "x");
    if (!(delta >= 0) || !(lambda > 0)) domain("delta must be >= 0 and lambda > 0", "delta");
    Alarms a;
    double n = 0, total = 0, up = 0, up_min = 0, dn = 0, dn_min = 0;
    for (std::size_t t = 0; t < x.size(); ++t) {
        n += 1;
        total += x[t];
        const double mean = total / n;
        up += x[t] - mean - delta;
        dn += mean - x[t] - delta;
        up_min = std::min(up_min, up);
        dn_min = std::min(dn_min, dn);
        const bool hit_up = direction != -1 && up - up_min > lambda;
        const bool hit_dn = direction != 1 && dn - dn_min > lambda;
        if (hit_up || hit_dn) {
            a.alarms.push_back(static_cast<long long>(t));
            a.directions.push_back(hit_up ? 1 : -1);
            if (!reset) break;
            n = total = up = up_min = dn = dn_min = 0;
        }
    }
    return a;
}

Psi psi(const Vec& reference, const Vec& test, long long bins, double threshold) {
    if (bins < 2) input("bins must be at least 2", "bins");
    if (static_cast<long long>(reference.size()) < bins || static_cast<long long>(test.size()) < bins)
        input("reference and test need at least bins values each", "reference");
    if (!(threshold > 0)) domain("threshold must be positive", "threshold");
    const auto b = static_cast<std::size_t>(bins);
    Vec r = reference;
    std::sort(r.begin(), r.end());
    const std::size_t n = r.size();
    Vec edges;
    for (std::size_t j = 1; j < b; ++j) edges.push_back(r[(j * n + b - 1) / b - 1]);
    const auto shares = [&](const Vec& s) {
        std::vector<std::size_t> c(b, 0);
        for (const double v : s) c[static_cast<std::size_t>(std::lower_bound(edges.begin(), edges.end(), v) - edges.begin())]++;
        Vec out;
        for (const std::size_t k : c) out.push_back(std::max(static_cast<double>(k) / static_cast<double>(s.size()), 1e-4));
        return out;
    };
    Psi p{0, shares(reference), shares(test), false};
    Vec terms;
    for (std::size_t i = 0; i < b; ++i)
        terms.push_back((p.test_shares[i] - p.reference_shares[i]) * std::log(p.test_shares[i] / p.reference_shares[i]));
    p.psi = fsum(terms);
    p.alarm = p.psi > threshold;
    return p;
}

double ks_p_count(long long n, long long m, long long d) {
    if (d <= 0) return 1.0;
    using U = unsigned __int128;
    const U top = ~U(0);
    U total = 1;
    for (long long k = 1; k <= std::min(n, m); ++k) {
        const U f = static_cast<U>(n + m - k + 1);
        if (total > top / f) return ks_p_walk(n, m, d);  // checked fallback: does not fit 128 bits
        total = total * f / static_cast<U>(k);
    }
    const auto inside = [&](long long i, long long j) { return std::llabs(i * m - j * n) < d; };
    std::vector<U> row(static_cast<std::size_t>(m) + 1, 0);
    row[0] = 1;
    for (long long j = 1; j <= m; ++j) row[j] = inside(0, j) ? row[j - 1] : 0;
    for (long long i = 1; i <= n; ++i) {
        if (!inside(i, 0)) row[0] = 0;
        for (long long j = 1; j <= m; ++j) row[j] = inside(i, j) ? row[j] + row[j - 1] : 0;
    }
    return static_cast<double>(total - row[static_cast<std::size_t>(m)]) / static_cast<double>(total);
}

// Fallback walk: sums the probability mass that steps outside the band (not 1 - stay), so tiny p-values keep a
// small relative error instead of cancelling to zero.
double ks_p_walk(long long n, long long m, long long d) {
    if (d <= 0) return 1.0;
    const auto inside = [&](long long i, long long j) { return std::llabs(i * m - j * n) < d; };
    double out = 0.0;
    Vec row(static_cast<std::size_t>(m) + 1, 0.0);
    row[0] = 1.0;
    for (long long i = 0; i <= n; ++i) {
        Vec next(static_cast<std::size_t>(m) + 1, 0.0);
        for (long long j = 0; j <= m; ++j) {
            const double r = row[static_cast<std::size_t>(j)];
            const auto left = static_cast<double>(n - i + m - j);
            if (r == 0.0 || left == 0.0) continue;
            if (i < n) {
                const double q = r * static_cast<double>(n - i) / left;
                (inside(i + 1, j) ? next[static_cast<std::size_t>(j)] : out) += q;
            }
            if (j < m) {
                const double q = r * static_cast<double>(m - j) / left;
                (inside(i, j + 1) ? row[static_cast<std::size_t>(j) + 1] : out) += q;
            }
        }
        row = std::move(next);
    }
    return std::min(out, 1.0);
}

Ks ks(const Vec& a, const Vec& b, double level) {
    if (a.empty() || b.empty()) input("a and b must not be empty", "a");
    if (!(level > 0 && level < 1)) domain("level must lie in (0, 1)", "level");
    Vec xa = a, xb = b;
    std::sort(xa.begin(), xa.end());
    std::sort(xb.begin(), xb.end());
    const auto n = static_cast<long long>(xa.size()), m = static_cast<long long>(xb.size());
    long long i = 0, j = 0, best = 0;
    constexpr double inf = std::numeric_limits<double>::infinity();
    while (i < n || j < m) {
        const double v = std::min(i < n ? xa[i] : inf, j < m ? xb[j] : inf);
        while (i < n && xa[i] == v) ++i;
        while (j < m && xb[j] == v) ++j;
        best = std::max(best, std::llabs(i * m - j * n));
    }
    const double p = ks_p_count(n, m, best);
    return {static_cast<double>(best) / (static_cast<double>(n) * static_cast<double>(m)), p, p <= level};
}

}  // namespace quantforge::research
