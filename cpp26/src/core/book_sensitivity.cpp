#include "quantforge/core/book_sensitivity.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>
#include <set>
#include <utility>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"

namespace quantforge {
namespace {

constexpr double bp = 1e-4;

// d ln D(t) / d x_k for the pillar unknowns x_k = ln D(p_k), k = 0..n-1, as (k, weight) pairs. Exact for the
// methods whose ln D is linear in x (Curve::plain_discount): LOG_LINEAR_DF and LINEAR_ZERO, no jumps.
using Weights = std::vector<std::pair<std::size_t, double>>;

// times[0] = 0 is the node at as_of (no unknown); times[k + 1] is pillar k.
Weights log_df_weights(const std::vector<double>& times, CurveInterpolation m, double t) {
    Weights w;
    const std::size_t n = times.size() - 1;
    const auto add = [&](std::size_t node, double weight) {
        if (node > 0 && weight != 0.0) w.emplace_back(node - 1, weight);
    };
    if (t <= 0.0) return w;
    if (t >= times[n]) {
        if (t == times[n]) {
            add(n, 1.0);
            return w;
        }
        const double r = (t - times[n]) / (times[n] - times[n - 1]);
        add(n, 1.0 + r);
        add(n - 1, -r);
        return w;
    }
    const auto i = std::size_t(std::upper_bound(times.begin(), times.end(), t) - times.begin()) - 1;
    const double u = (t - times[i]) / (times[i + 1] - times[i]);
    if (m != CurveInterpolation::LinearZero) {
        add(i, 1.0 - u);
        add(i + 1, u);
        return w;
    }
    // ln D = t ((1 - u) x_i / t_i + u x_{i+1} / t_{i+1}), with the first segment flat in zero rate.
    if (i == 0) {
        add(1, t / times[1]);
    } else {
        add(i, (1.0 - u) * t / times[i]);
        add(i + 1, u * t / times[i + 1]);
    }
    return w;
}

struct Pricing {
    const Curve& curve;
    const RateConvention& c;
    std::vector<double> times;

    void accumulate(Date d, double scale, std::vector<double>& g) const {
        for (const auto& [k, w] : log_df_weights(times, curve.interpolation(), curve.time(d))) g[k] += scale * w;
    }

    // Legs and their gradients in x.
    Legs legs(const std::vector<Period>& periods, std::vector<double>& d_annuity, std::vector<double>& d_floating) const {
        const std::size_t n = times.size() - 1;
        d_annuity.assign(n, 0.0);
        d_floating.assign(n, 0.0);
        Legs v{0.0, 0.0};
        for (const Period& p : periods) {
            const double pay = curve.discount(p.payment);
            const double tau = year_fraction(c.fixed_day_count, p.start, p.end);
            const double ratio = curve.discount(p.start) / curve.discount(p.end);
            v.annuity += tau * pay;
            v.floating += (ratio - 1.0) * pay;
            accumulate(p.payment, tau * pay, d_annuity);
            accumulate(p.payment, (ratio - 1.0) * pay, d_floating);
            accumulate(p.start, ratio * pay, d_floating);
            accumulate(p.end, -ratio * pay, d_floating);
        }
        return v;
    }
};

bool linear_in_x(CurveInterpolation m) { return m == CurveInterpolation::LogLinearDf || m == CurveInterpolation::LinearZero; }

void require_finite_quotes(const std::vector<OisQuote>& quotes) {
    for (const OisQuote& q : quotes) require_finite(q.rate, "quotes");
}

struct Ift {
    Curve curve;
    std::vector<double> times;
    Matrix dx_dq;
};

Ift solve_ift(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes, CurveInterpolation interpolation) {
    require_finite_quotes(quotes);
    if (!linear_in_x(interpolation))
        throw Error("E_DOMAIN", "exact sensitivities need LOG_LINEAR_DF or LINEAR_ZERO", "interpolation");
    Curve curve = ois_bootstrap(c, as_of, quotes, interpolation, SolveMethod::Sequential).curve;
    std::vector<double> times{0.0};
    for (const Pillar& p : curve.pillars()) times.push_back(curve.time(p.date));
    const std::size_t n = quotes.size();
    const Pricing pricing{curve, c, times};
    // J[j][k] = d par_j / d x_k = (dF - par dA) / A.
    Matrix j(n, std::vector<double>(n, 0.0));
    std::vector<double> da, df;
    for (std::size_t r = 0; r < n; ++r) {
        const Legs v = pricing.legs(ois_periods(c, as_of, quotes[r].tenor), da, df);
        const double par = v.par();
        for (std::size_t k = 0; k < n; ++k) j[r][k] = (df[k] - par * da[k]) / v.annuity;
    }
    bool lower = true;
    for (std::size_t r = 0; r < n && lower; ++r)
        for (std::size_t k = r + 1; k < n && lower; ++k) lower = j[r][k] == 0.0;
    Matrix inv(n, std::vector<double>(n, 0.0));
    if (lower) {
        // Forward substitution per column: entries above the diagonal are never touched (ruling F-30).
        for (std::size_t col = 0; col < n; ++col)
            for (std::size_t r = col; r < n; ++r) {
                double s = r == col ? 1.0 : 0.0;
                for (std::size_t k = col; k < r; ++k) s -= j[r][k] * inv[k][col];
                inv[r][col] = s / j[r][r];
            }
    } else {
        for (std::size_t col = 0; col < n; ++col) {
            std::vector<double> e(n, 0.0);
            e[col] = 1.0;
            const std::vector<double> x = lu_solve(j, e);
            for (std::size_t r = 0; r < n; ++r) inv[r][col] = x[r];
        }
    }
    return {std::move(curve), std::move(times), std::move(inv)};
}

}  // namespace

Matrix ois_curve_ift(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                     CurveInterpolation interpolation) {
    return solve_ift(c, as_of, quotes, interpolation).dx_dq;
}

BookSensitivity ois_book_sensitivity(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                                     CurveInterpolation interpolation, const std::vector<BookSwap>& swaps) {
    require_finite_quotes(quotes);
    for (const BookSwap& s : swaps) require_finite(s.fixed_rate, "fixed_rate");
    if (swaps.empty()) throw Error("E_INPUT", "the book has no swaps", "swaps");
    std::set<std::string> ids;
    for (const BookSwap& s : swaps)
        if (!ids.insert(s.id).second) throw Error("E_INPUT", "swap ids must be unique", "swaps");
    for (const BookSwap& s : swaps)
        if (s.tenor_years < 1 || s.tenor_years > 100) throw Error("E_DOMAIN", "tenor_years must be in [1, 100]", "tenor_years");
    const Ift ift = solve_ift(c, as_of, quotes, interpolation);
    const std::size_t n = quotes.size();
    const Pricing pricing{ift.curve, c, ift.times};
    BookSensitivity out{{}, 0.0, {}, std::vector<double>(n, 0.0), {}, {}};
    std::vector<double> da, df, dpv(n);
    for (const BookSwap& s : swaps) {
        const double sign = s.side == FixedSide::Pay ? 1.0 : -1.0;
        const Legs v = pricing.legs(ois_periods(c, as_of, Tenor{int(s.tenor_years), 'Y'}), da, df);
        const double pv = sign * (v.floating - s.fixed_rate * v.annuity);
        out.pv.push_back(pv);
        out.book_pv += pv;
        for (std::size_t k = 0; k < n; ++k) dpv[k] = sign * (df[k] - s.fixed_rate * da[k]);
        std::vector<double> row(n, 0.0);
        for (std::size_t q = 0; q < n; ++q) {
            double sum = 0.0;
            for (std::size_t k = 0; k < n; ++k)
                if (dpv[k] != 0.0 && ift.dx_dq[k][q] != 0.0) sum += dpv[k] * ift.dx_dq[k][q];
            row[q] = sum;
            out.book_sensitivity[q] += sum;
        }
        out.quote_sensitivity.push_back(std::move(row));
    }
    for (const Pillar& p : ift.curve.pillars()) out.pillars.push_back(p.date);
    for (std::size_t i = 0; i < n; ++i) {
        std::vector<double> row(n, 0.0);
        for (std::size_t q = 0; q < n; ++q)
            if (ift.dx_dq[i][q] != 0.0) row[q] = -ift.dx_dq[i][q] / ift.times[i + 1];
        out.zero_jacobian.push_back(std::move(row));
    }
    return out;
}

void eigen_vectors_symmetric(Matrix a, std::vector<double>& values, Matrix& vectors) {
    const std::size_t n = a.size();
    Matrix v(n, std::vector<double>(n, 0.0));
    for (std::size_t i = 0; i < n; ++i) v[i][i] = 1.0;
    for (int sweep = 0; sweep < 100; ++sweep) {
        double off = 0.0, scale = 0.0;
        for (std::size_t p = 0; p < n; ++p) {
            scale += a[p][p] * a[p][p];
            for (std::size_t q = p + 1; q < n; ++q) off += a[p][q] * a[p][q];
        }
        if (off == 0.0 || off <= 1e-64 * scale) break;
        for (std::size_t p = 0; p < n; ++p)
            for (std::size_t q = p + 1; q < n; ++q) {
                if (a[p][q] == 0.0) continue;
                const double theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
                const double t = (theta >= 0 ? 1.0 : -1.0) / (std::fabs(theta) + std::sqrt(theta * theta + 1.0));
                const double cs = 1.0 / std::sqrt(t * t + 1.0), sn = t * cs;
                for (std::size_t k = 0; k < n; ++k) {
                    const double akp = a[k][p], akq = a[k][q];
                    a[k][p] = cs * akp - sn * akq;
                    a[k][q] = sn * akp + cs * akq;
                }
                for (std::size_t k = 0; k < n; ++k) {
                    const double apk = a[p][k], aqk = a[q][k];
                    a[p][k] = cs * apk - sn * aqk;
                    a[q][k] = sn * apk + cs * aqk;
                }
                for (std::size_t k = 0; k < n; ++k) {
                    const double vkp = v[k][p], vkq = v[k][q];
                    v[k][p] = cs * vkp - sn * vkq;
                    v[k][q] = sn * vkp + cs * vkq;
                }
            }
    }
    std::vector<std::size_t> order(n);
    std::iota(order.begin(), order.end(), std::size_t(0));
    std::stable_sort(order.begin(), order.end(), [&](std::size_t x, std::size_t y) { return a[x][x] > a[y][y]; });
    values.clear();
    vectors.clear();
    for (const std::size_t i : order) {
        values.push_back(a[i][i]);
        std::vector<double> col(n);
        for (std::size_t k = 0; k < n; ++k) col[k] = v[k][i];
        vectors.push_back(std::move(col));
    }
}

CurvePca curve_pca(const Matrix& changes, long long components) {
    for (const auto& row : changes) require_finite(row, "changes");
    if (changes.size() < 2) throw Error("E_INPUT", "at least two observations are needed", "changes");
    const std::size_t n = changes[0].size();
    for (const auto& row : changes)
        if (row.size() != n || n == 0) throw Error("E_INPUT", "every row must have the same length", "changes");
    if (components < 1) throw Error("E_DOMAIN", "components must be at least 1", "components");
    if (std::size_t(components) > n) throw Error("E_INPUT", "components is above the tenor count", "components");
    const std::size_t k = std::size_t(components);
    const double t = double(changes.size());
    std::vector<double> mean(n, 0.0);
    for (const auto& row : changes)
        for (std::size_t j = 0; j < n; ++j) mean[j] += row[j];
    for (double& m : mean) m /= t;
    Matrix cov(n, std::vector<double>(n, 0.0));
    for (const auto& row : changes)
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t j = i; j < n; ++j) cov[i][j] += (row[i] - mean[i]) * (row[j] - mean[j]);
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = i; j < n; ++j) cov[j][i] = cov[i][j] /= t - 1.0;
    CurvePca out;
    Matrix vectors;
    eigen_vectors_symmetric(cov, out.eigenvalues, vectors);
    const std::size_t checked = std::min(k + 1, n);
    for (std::size_t i = 0; i + 1 < checked; ++i)
        if (out.eigenvalues[i] - out.eigenvalues[i + 1] < 1e-6 * out.eigenvalues[0])
            throw Error("E_DOMAIN", "repeated eigenvalues: the loadings are not unique", "changes");
    const double total = std::accumulate(out.eigenvalues.begin(), out.eigenvalues.end(), 0.0);
    for (std::size_t i = 0; i < k; ++i) {
        std::vector<double> l = vectors[i];
        std::size_t big = 0;
        for (std::size_t j = 1; j < n; ++j)
            if (std::fabs(l[j]) > std::fabs(l[big])) big = j;
        if (l[big] < 0)
            for (double& x : l) x = -x;
        out.loadings.push_back(std::move(l));
        out.explained_ratio.push_back(out.eigenvalues[i] / total);
    }
    return out;
}

CrossGamma cross_gamma(const Curve& curve, const CurvePricer& price, double bump_bp) {
    check_bump(bump_bp);
    const auto pillars = curve.pillars();
    const std::size_t n = pillars.size();
    std::vector<double> t(n);
    for (std::size_t i = 0; i < n; ++i) t[i] = curve.time(pillars[i].date);
    const double h = bump_bp * bp;
    // Pillar zero rates moved by h times the signs (ruling: PILLAR bump of par-and-key-rate.md).
    const auto value = [&](std::size_t i, double si, std::size_t j, double sj) {
        Curve c = curve;
        c.set_log_df(i, curve.log_df(i) - si * h * t[i]);
        if (j != i) c.set_log_df(j, curve.log_df(j) - sj * h * t[j]);
        return price(c);
    };
    CrossGamma out{price(curve), Matrix(n, std::vector<double>(n, 0.0))};
    const double b2 = bump_bp * bump_bp;
    for (std::size_t i = 0; i < n; ++i) {
        out.gamma[i][i] = (value(i, 1, i, 0) - 2.0 * out.value + value(i, -1, i, 0)) / b2;
        for (std::size_t j = i + 1; j < n; ++j) {
            const double g = (value(i, 1, j, 1) - value(i, 1, j, -1) - value(i, -1, j, 1) + value(i, -1, j, -1)) / (4.0 * b2);
            out.gamma[i][j] = out.gamma[j][i] = g;
        }
    }
    return out;
}

CrossGamma cross_gamma(const Curve& curve, const OisTrade& trade, double bump_bp) {
    check_bump(bump_bp);
    require_finite(trade.fixed_rate, "fixed_rate");
    require_finite(trade.notional, "notional");
    if (!linear_in_x(curve.interpolation()) || curve.size() == 0)
        return cross_gamma(curve, [trade](const Curve& c) { return ois_price(trade, c).valuation.pv; }, bump_bp);
    // ln D is linear in the pillar log factors, so a bumped term is the base term times expm1 of an exact shift:
    // V(bump) - V(0) is summed directly and does not cancel against V(0).
    const RateConvention& c = *trade.convention;
    const auto pillars = curve.pillars();
    const std::size_t n = pillars.size();
    std::vector<double> times{0.0};
    for (const Pillar& p : pillars) times.push_back(curve.time(p.date));
    struct Flow {
        double ratio_term, pay_term;  // D_s D_p / D_e and (1 + K tau) D_p
        Weights s, e, p;
    };
    std::vector<Flow> flows;
    for (const Period& p : ois_periods(c, curve.as_of(), trade.tenor)) {
        const double pay = curve.discount(p.payment);
        const double tau = year_fraction(c.fixed_day_count, p.start, p.end);
        flows.push_back({curve.discount(p.start) / curve.discount(p.end) * pay, (1.0 + trade.fixed_rate * tau) * pay,
                         log_df_weights(times, curve.interpolation(), curve.time(p.start)),
                         log_df_weights(times, curve.interpolation(), curve.time(p.end)),
                         log_df_weights(times, curve.interpolation(), curve.time(p.payment))});
    }
    const double scale = (trade.side == FixedSide::Pay ? 1.0 : -1.0) * trade.notional;
    const double h = bump_bp * bp;
    // Change of ln D at weights w when pillar k's zero rate moves by shift[k] (ln D(p_k) moves by -shift t_k).
    std::vector<double> shift(n, 0.0);
    const auto moved = [&](const Weights& w) {
        double m = 0.0;
        for (const auto& [k, x] : w) m -= x * shift[k] * times[k + 1];
        return m;
    };
    const auto change = [&](std::size_t i, double si, std::size_t j, double sj) {
        std::fill(shift.begin(), shift.end(), 0.0);
        shift[i] += si * h;
        shift[j] += sj * h;
        double dv = 0.0;
        for (const Flow& f : flows)
            dv += f.ratio_term * std::expm1(moved(f.s) + moved(f.p) - moved(f.e)) - f.pay_term * std::expm1(moved(f.p));
        return scale * dv;
    };
    CrossGamma out{ois_price(trade, curve).valuation.pv, Matrix(n, std::vector<double>(n, 0.0))};
    const double b2 = bump_bp * bump_bp;
    for (std::size_t i = 0; i < n; ++i) {
        out.gamma[i][i] = (change(i, 1, i, 0) + change(i, -1, i, 0)) / b2;
        for (std::size_t j = i + 1; j < n; ++j) {
            const double g = (change(i, 1, j, 1) - change(i, 1, j, -1) - change(i, -1, j, 1) + change(i, -1, j, -1)) / (4.0 * b2);
            out.gamma[i][j] = out.gamma[j][i] = g;
        }
    }
    return out;
}

Jtd jump_to_default(const std::vector<JtdPosition>& positions) {
    for (const JtdPosition& p : positions) {
        require_finite(p.notional, "notional");
        require_finite(p.recovery, "recovery");
        require_finite(p.market_value, "market_value");
    }
    if (positions.empty()) throw Error("E_INPUT", "no positions", "positions");
    Jtd out{{}, 0.0};
    for (const JtdPosition& p : positions) {
        if (!(p.notional >= 0.0)) throw Error("E_DOMAIN", "notional must be at least 0", "notional");
        if (!(p.recovery >= 0.0 && p.recovery <= 1.0)) throw Error("E_DOMAIN", "recovery must be in [0, 1]", "recovery");
        double after = 0.0;
        switch (p.kind) {
            case JtdKind::Bond: after = p.recovery * p.notional; break;
            case JtdKind::CdsProtectionBuyer: after = (1.0 - p.recovery) * p.notional; break;
            case JtdKind::CdsProtectionSeller: after = -(1.0 - p.recovery) * p.notional; break;
        }
        out.jtd.push_back(after - p.market_value);
        out.total += out.jtd.back();
    }
    return out;
}

}  // namespace quantforge
