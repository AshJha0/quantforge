// Stage I wave 1, hedge solvers. specifications/08-hedging/hedge-solvers.md, rulings I-1 to I-14.
//
// hedge.qp.solve works in the null space of the equalities: x = x_p + Z y, with x_p = E^+ e and Z an
// orthonormal basis from a Householder QR of E^T. The reduced problem in y is strictly convex once
// checks 4 and 5 pass, and is solved by the Goldfarb-Idnani dual active-set method, which starts from the
// unconstrained minimiser and either reaches the unique KKT point or proves that no feasible point exists.
// hedge.integer.solve enumerates the lattice points inside the ellipsoid {n : f(n) <= f(n_0)} around the
// continuous minimiser [FP85], with the box of lot bounds applied coordinate by coordinate.
#include "quantforge/core/hedging.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <string>

#include "quantforge/core/error.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge::hedging {
namespace {

constexpr double inf = std::numeric_limits<double>::infinity();

void input_if(bool bad, const char* field, const std::string& why) {
    if (bad) throw Error("E_INPUT", std::string(field) + ": " + why, field);
}
void domain_if(bool bad, const char* field, const std::string& why) {
    if (bad) throw Error("E_DOMAIN", std::string(field) + ": " + why, field);
}

double dot(const Vec& u, const Vec& v) {
    double s = 0.0;
    for (std::size_t i = 0; i < u.size(); ++i) s += u[i] * v[i];
    return s;
}

Matrix identity(std::size_t n) {
    Matrix m(n, Vec(n, 0.0));
    for (std::size_t i = 0; i < n; ++i) m[i][i] = 1.0;
    return m;
}

// Shapes common to the least-squares operations (QP check 1, integer check 1): returns n.
std::size_t check_ls_shapes(const Matrix& a, const Vec& b, const Vec& weights) {
    input_if(a.empty(), "a", "needs at least one row");
    const std::size_t n = a[0].size();
    input_if(n == 0, "a", "needs at least one column");
    for (const Vec& row : a) input_if(row.size() != n, "a", "rows of unequal length");
    input_if(b.size() != a.size(), "b", "length differs from the rows of a");
    input_if(weights.size() != a.size(), "weights", "length differs from the rows of a");
    return n;
}

void check_ls_domain(const Vec& weights, double ridge) {
    for (const double w : weights) domain_if(w <= 0.0, "weights", "each weight must be above 0");
    domain_if(ridge < 0.0, "ridge", "must be at least 0");
}

// H = A^T W A + ridge I and c = A^T W b, so that f(x) = x'Hx + 2c'x + b'Wb.
struct Normal {
    Matrix h;
    Vec c;
};
Normal normal_equations(const Matrix& a, const Vec& b, const Vec& w, double ridge) {
    const std::size_t m = a.size(), n = a[0].size();
    Normal q{Matrix(n, Vec(n, 0.0)), Vec(n, 0.0)};
    for (std::size_t r = 0; r < m; ++r)
        for (std::size_t i = 0; i < n; ++i) {
            const double wa = w[r] * a[r][i];
            q.c[i] += wa * b[r];
            for (std::size_t j = 0; j < n; ++j) q.h[i][j] += wa * a[r][j];
        }
    for (std::size_t i = 0; i < n; ++i) q.h[i][i] += ridge;
    return q;
}

Vec residual_of(const Matrix& a, const Vec& b, const Vec& x) {
    Vec r(b);
    for (std::size_t i = 0; i < a.size(); ++i) r[i] += dot(a[i], x);
    return r;
}

double objective_of(const Vec& residual, const Vec& w, double ridge, const Vec& x) {
    double f = 0.0;
    for (std::size_t i = 0; i < residual.size(); ++i) f += w[i] * residual[i] * residual[i];
    return f + ridge * dot(x, x);
}

double largest_abs(const Vec& v) {
    double m = 0.0;
    for (const double x : v) m = std::max(m, std::fabs(x));
    return m;
}

// Lower Cholesky factor of a positive definite matrix. unchecked: callers have checked definiteness.
Matrix cholesky_lower(const Matrix& g) {
    const std::size_t n = g.size();
    Matrix l(n, Vec(n, 0.0));
    for (std::size_t j = 0; j < n; ++j) {
        double d = g[j][j];
        for (std::size_t k = 0; k < j; ++k) d -= l[j][k] * l[j][k];
        l[j][j] = std::sqrt(std::max(d, std::numeric_limits<double>::min()));
        for (std::size_t i = j + 1; i < n; ++i) {
            double s = g[i][j];
            for (std::size_t k = 0; k < j; ++k) s -= l[i][k] * l[j][k];
            l[i][j] = s / l[j][j];
        }
    }
    return l;
}

// Solves L L^T x = v.
Vec cholesky_solve(const Matrix& l, Vec v) {
    const std::size_t n = l.size();
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t k = 0; k < i; ++k) v[i] -= l[i][k] * v[k];
        v[i] /= l[i][i];
    }
    for (std::size_t i = n; i-- > 0;) {
        for (std::size_t k = i + 1; k < n; ++k) v[i] -= l[k][i] * v[k];
        v[i] /= l[i][i];
    }
    return v;
}

// ---- null space of the equalities ----

// x_p = E^+ e (minimum norm, orthogonal to the null space) and Z, an n x (n-k) orthonormal null-space basis,
// from a Householder QR of E^T. E has full row rank here (check 4 passed).
struct NullSpace {
    Vec xp;
    Matrix z;  // n rows, n - k columns
};
// R6-6.2: Jacobi scaling before every I-3 decision. D_jj = 1 / sqrt(H_jj) (1 where H_jj <= 0, a column the
// test then finds singular anyway); returns D.
Vec jacobi_scale(const Matrix& h) {
    Vec d(h.size(), 1.0);
    for (std::size_t j = 0; j < h.size(); ++j)
        if (h[j][j] > 0.0) d[j] = 1.0 / std::sqrt(h[j][j]);
    return d;
}
Matrix scaled(Matrix h, const Vec& d) {
    for (std::size_t i = 0; i < h.size(); ++i)
        for (std::size_t j = 0; j < h.size(); ++j) h[i][j] *= d[i] * d[j];
    return h;
}

NullSpace null_space(const Matrix& e, const Vec& rhs, std::size_t n) {
    const std::size_t k = e.size();
    Matrix m(n, Vec(k, 0.0));  // E^T
    for (std::size_t i = 0; i < k; ++i)
        for (std::size_t j = 0; j < n; ++j) m[j][i] = e[i][j];
    Matrix q = identity(n);
    for (std::size_t j = 0; j < k; ++j) {
        double norm = 0.0;
        for (std::size_t i = j; i < n; ++i) norm += m[i][j] * m[i][j];
        norm = std::sqrt(norm);
        if (norm == 0.0) continue;
        const double alpha = m[j][j] > 0.0 ? -norm : norm;
        Vec v(n, 0.0);
        for (std::size_t i = j; i < n; ++i) v[i] = m[i][j];
        v[j] -= alpha;
        double vv = 0.0;
        for (std::size_t i = j; i < n; ++i) vv += v[i] * v[i];
        if (vv == 0.0) continue;
        for (std::size_t c = j; c < k; ++c) {
            double s = 0.0;
            for (std::size_t i = j; i < n; ++i) s += v[i] * m[i][c];
            s *= 2.0 / vv;
            for (std::size_t i = j; i < n; ++i) m[i][c] -= s * v[i];
        }
        for (std::size_t r = 0; r < n; ++r) {
            double s = 0.0;
            for (std::size_t i = j; i < n; ++i) s += q[r][i] * v[i];
            s *= 2.0 / vv;
            for (std::size_t i = j; i < n; ++i) q[r][i] -= s * v[i];
        }
    }
    // E^T = Q [R; 0], so E = R^T Q1^T and x_p = Q1 R^{-T} e.
    Vec w(k, 0.0);
    for (std::size_t i = 0; i < k; ++i) {
        double s = rhs[i];
        for (std::size_t j = 0; j < i; ++j) s -= m[j][i] * w[j];
        w[i] = s / m[i][i];
    }
    NullSpace ns{Vec(n, 0.0), Matrix(n, Vec(n - k, 0.0))};
    for (std::size_t r = 0; r < n; ++r) {
        for (std::size_t i = 0; i < k; ++i) ns.xp[r] += q[r][i] * w[i];
        for (std::size_t c = k; c < n; ++c) ns.z[r][c - k] = q[r][c];
    }
    return ns;
}

// Z^T M Z and Z^T v.
Matrix project(const Matrix& z, const Matrix& h) {
    const std::size_t n = z.size(), r = n ? z[0].size() : 0;
    Matrix hz(n, Vec(r, 0.0));
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t k = 0; k < n; ++k)
            if (h[i][k] != 0.0)
                for (std::size_t c = 0; c < r; ++c) hz[i][c] += h[i][k] * z[k][c];
    Matrix out(r, Vec(r, 0.0));
    for (std::size_t a = 0; a < r; ++a)
        for (std::size_t c = 0; c < r; ++c) {
            double s = 0.0;
            for (std::size_t i = 0; i < n; ++i) s += z[i][a] * hz[i][c];
            out[a][c] = s;
        }
    for (std::size_t a = 0; a < r; ++a)  // exact symmetry for the eigen-solver
        for (std::size_t c = a + 1; c < r; ++c) out[a][c] = out[c][a] = 0.5 * (out[a][c] + out[c][a]);
    return out;
}
Vec project(const Matrix& z, const Vec& v) {
    const std::size_t n = z.size(), r = n ? z[0].size() : 0;
    Vec out(r, 0.0);
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t c = 0; c < r; ++c) out[c] += z[i][c] * v[i];
    return out;
}

// ---- Goldfarb-Idnani dual active set ----

// Minimises y'Gy/2 + g'y subject to normals[i] . y >= rhs[i], G positive definite. Returns the minimiser, or
// nothing when the constraints have no common point. active receives the indices of the active constraints.
class DualActiveSet {
public:
    DualActiveSet(const Matrix& g, const Vec& g0, const Matrix& normals, const Vec& rhs)
        : n_(g.size()), normals_(normals), rhs_(rhs), j_(n_, Vec(n_, 0.0)), r_(n_, Vec(n_, 0.0)) {
        const Matrix l = cholesky_lower(g);
        // J = L^{-T}: column c of J solves L^T j = e_c.
        for (std::size_t c = 0; c < n_; ++c) {
            Vec col(n_, 0.0);
            col[c] = 1.0;
            for (std::size_t i = n_; i-- > 0;) {
                for (std::size_t k = i + 1; k < n_; ++k) col[i] -= l[k][i] * col[k];
                col[i] /= l[i][i];
            }
            for (std::size_t i = 0; i < n_; ++i) j_[i][c] = col[i];
        }
        y_ = cholesky_solve(l, g0);
        for (double& v : y_) v = -v;
    }

    bool solve() {
        const auto max_steps = std::size_t(detail::effort_cap(10 * (long long)n_ + 100));  // R6-6.1
        std::vector<char> in_active(normals_.size(), 0);
        for (std::size_t step = 0; step < max_steps;) {
            // Step 1: the most violated constraint not yet active.
            std::size_t p = normals_.size();
            double worst = 0.0;
            for (std::size_t i = 0; i < normals_.size(); ++i) {
                if (in_active[i]) continue;
                const double s = slack(i);
                if (s < -tolerance(i) && s < worst) {
                    worst = s;
                    p = i;
                }
            }
            if (p == normals_.size()) return true;
            double up = 0.0, sp = worst;
            // Step 2: move until p is active, dropping blocking constraints on the way.
            for (;; ++step) {
                if (step >= max_steps) break;
                const Vec d = jt_times(normals_[p]);
                Vec z(n_, 0.0);
                double d2 = 0.0, dall = 0.0;
                for (std::size_t c = 0; c < n_; ++c) {
                    dall += d[c] * d[c];
                    if (c < iq()) continue;
                    d2 += d[c] * d[c];
                    for (std::size_t i = 0; i < n_; ++i) z[i] += j_[i][c] * d[c];
                }
                const Vec r = r_solve(d);
                double t1 = inf;
                std::size_t drop = 0;
                for (std::size_t k = 0; k < iq(); ++k)
                    if (r[k] > 0.0 && u_[k] / r[k] < t1) {
                        t1 = u_[k] / r[k];
                        drop = k;
                    }
                const bool step_in_primal = d2 > 1e-24 * dall;
                const double t2 = step_in_primal ? -sp / d2 : inf;  // n_p . z = |d2|^2
                if (t1 == inf && t2 == inf) return false;           // no feasible point
                if (t2 == inf) {                                     // dual step only
                    for (std::size_t k = 0; k < iq(); ++k) u_[k] -= t1 * r[k];
                    up += t1;
                    in_active[active_[drop]] = 0;
                    remove(drop);
                    continue;
                }
                const double t = std::min(t1, t2);
                for (std::size_t i = 0; i < n_; ++i) y_[i] += t * z[i];
                for (std::size_t k = 0; k < iq(); ++k) u_[k] -= t * r[k];
                up += t;
                if (t2 <= t1) {
                    add(p, d, up);
                    in_active[p] = 1;
                    ++step;
                    break;
                }
                in_active[active_[drop]] = 0;
                remove(drop);
                sp = slack(p);
            }
        }
        throw Error("E_NO_CONVERGENCE", "the active-set method did not terminate");
    }

    const Vec& y() const { return y_; }
    const std::vector<std::size_t>& active() const { return active_; }
    const Vec& multipliers() const { return u_; }  // of active(), for y'Gy/2 + g'y

private:
    std::size_t iq() const { return active_.size(); }
    double slack(std::size_t i) const { return dot(normals_[i], y_) - rhs_[i]; }
    double tolerance(std::size_t i) const {
        double scale = std::fabs(rhs_[i]);
        for (std::size_t k = 0; k < n_; ++k) scale += std::fabs(normals_[i][k] * y_[k]);
        return 1e-12 * scale;
    }
    Vec jt_times(const Vec& v) const {
        Vec d(n_, 0.0);
        for (std::size_t c = 0; c < n_; ++c)
            for (std::size_t i = 0; i < n_; ++i) d[c] += j_[i][c] * v[i];
        return d;
    }
    Vec r_solve(const Vec& d) const {
        Vec r(iq(), 0.0);
        for (std::size_t i = iq(); i-- > 0;) {
            double s = d[i];
            for (std::size_t k = i + 1; k < iq(); ++k) s -= r_[i][k] * r[k];
            r[i] = s / r_[i][i];
        }
        return r;
    }
    // Rotates columns a, b of J (and the matching entries of d, when given) so that d_b becomes 0.
    static void reflect(double& cc, double& ss, double& first, double& second) {
        const double h = std::hypot(cc, ss);
        cc /= h;
        ss /= h;
        second = 0.0;
        if (cc < 0.0) {
            cc = -cc;
            ss = -ss;
            first = -h;
        } else {
            first = h;
        }
    }
    void add(std::size_t p, Vec d, double up) {
        for (std::size_t c = n_ - 1; c > iq(); --c) {
            double cc = d[c - 1], ss = d[c];
            if (std::hypot(cc, ss) == 0.0) continue;
            reflect(cc, ss, d[c - 1], d[c]);
            const double xny = ss / (1.0 + cc);
            for (std::size_t k = 0; k < n_; ++k) {
                const double t1 = j_[k][c - 1], t2 = j_[k][c];
                j_[k][c - 1] = t1 * cc + t2 * ss;
                j_[k][c] = xny * (t1 + j_[k][c - 1]) - t2;
            }
        }
        active_.push_back(p);
        u_.push_back(up);
        for (std::size_t i = 0; i < iq(); ++i) r_[i][iq() - 1] = d[i];
    }
    void remove(std::size_t q) {
        const std::size_t last = iq() - 1;
        for (std::size_t c = q; c < last; ++c)
            for (std::size_t i = 0; i < n_; ++i) r_[i][c] = r_[i][c + 1];
        for (std::size_t i = 0; i < n_; ++i) r_[i][last] = 0.0;
        active_.erase(active_.begin() + std::ptrdiff_t(q));
        u_.erase(u_.begin() + std::ptrdiff_t(q));
        for (std::size_t c = q; c < iq(); ++c) {
            double cc = r_[c][c], ss = r_[c + 1][c];
            if (std::hypot(cc, ss) == 0.0) continue;
            reflect(cc, ss, r_[c][c], r_[c + 1][c]);
            const double xny = ss / (1.0 + cc);
            for (std::size_t k = c + 1; k < iq(); ++k) {
                const double t1 = r_[c][k], t2 = r_[c + 1][k];
                r_[c][k] = t1 * cc + t2 * ss;
                r_[c + 1][k] = xny * (t1 + r_[c][k]) - t2;
            }
            for (std::size_t k = 0; k < n_; ++k) {
                const double t1 = j_[k][c], t2 = j_[k][c + 1];
                j_[k][c] = t1 * cc + t2 * ss;
                j_[k][c + 1] = xny * (j_[k][c] + t1) - t2;
            }
        }
    }

    std::size_t n_;
    const Matrix& normals_;
    const Vec& rhs_;
    Matrix j_, r_;
    Vec y_, u_;
    std::vector<std::size_t> active_;
};

// One bound constraint of the reduced problem: sign * x_j >= sign * bound, x_j = xp_j + Z_j y.
struct BoundRow {
    std::size_t index;
    bool lower;
    double bound;
};

// Multipliers of the active rows, on the scale of x'Hx/2 + c'x (half of f): per instrument for its lower and
// upper row, and for the general row.
struct Multipliers {
    Vec lower, upper;
    double general = 0.0;
};

// Minimises the strictly convex quadratic y'Gy/2 + g'y over the bounds on x = xp + Z y and, when given, one
// general row: general . x >= general_rhs (the 4a margin within an orthant). Throws E_INFEASIBLE.
Vec bounded_minimiser(const Matrix& reduced, const Vec& g0, const NullSpace& ns, const std::vector<Bound>& lower,
                      const std::vector<Bound>& upper, const Vec* general = nullptr, double general_rhs = 0.0,
                      Multipliers* mult = nullptr) {
    const std::size_t n = ns.xp.size(), r = reduced.size();
    std::vector<BoundRow> rows;
    for (std::size_t j = 0; j < n; ++j) {
        if (!lower.empty() && lower[j]) rows.push_back({j, true, *lower[j]});
        if (!upper.empty() && upper[j]) rows.push_back({j, false, *upper[j]});
    }
    Vec x = ns.xp;
    if (r == 0) {  // k = n: the equalities fix x
        for (const BoundRow& b : rows) {
            const double gap = b.lower ? x[b.index] - b.bound : b.bound - x[b.index];
            if (gap < -1e-12 * (std::fabs(b.bound) + std::fabs(x[b.index])))
                throw Error("E_INFEASIBLE", "the equalities fix x outside the bounds");
        }
        if (mult) *mult = Multipliers{Vec(n, 0.0), Vec(n, 0.0), 0.0};
        if (general) {
            double lhs = 0.0, scale = std::fabs(general_rhs);
            for (std::size_t j = 0; j < n; ++j) {
                lhs += (*general)[j] * x[j];
                scale += std::fabs((*general)[j] * x[j]);
            }
            if (lhs - general_rhs < -1e-12 * scale) throw Error("E_INFEASIBLE", "the equalities break the margin limit");
        }
        return x;
    }
    Matrix normals;
    Vec rhs;
    for (const BoundRow& b : rows) {
        const double sign = b.lower ? 1.0 : -1.0;
        Vec row(r);
        for (std::size_t c = 0; c < r; ++c) row[c] = sign * ns.z[b.index][c];
        normals.push_back(std::move(row));
        rhs.push_back(sign * (b.bound - ns.xp[b.index]));
    }
    if (general) {
        Vec row(r, 0.0);
        double at_xp = 0.0;
        for (std::size_t j = 0; j < n; ++j) {
            at_xp += (*general)[j] * ns.xp[j];
            for (std::size_t c = 0; c < r; ++c) row[c] += (*general)[j] * ns.z[j][c];
        }
        normals.push_back(std::move(row));
        rhs.push_back(general_rhs - at_xp);
    }
    DualActiveSet qp(reduced, g0, normals, rhs);
    if (!qp.solve()) throw Error("E_INFEASIBLE", "no point satisfies the equalities and the bounds");
    for (std::size_t j = 0; j < n; ++j)
        for (std::size_t c = 0; c < r; ++c) x[j] += ns.z[j][c] * qp.y()[c];
    if (r == n)  // Z = I: an active bound holds exactly
        for (const std::size_t i : qp.active())
            if (i < rows.size()) x[rows[i].index] = rows[i].bound;
    if (mult) {
        *mult = Multipliers{Vec(n, 0.0), Vec(n, 0.0), 0.0};
        for (std::size_t a = 0; a < qp.active().size(); ++a) {
            const std::size_t i = qp.active()[a];
            if (i == rows.size()) mult->general = qp.multipliers()[a];
            else (rows[i].lower ? mult->lower : mult->upper)[rows[i].index] = qp.multipliers()[a];
        }
    }
    return x;
}

}  // namespace

// ---- Jacobi eigen-decomposition ----

Eigen jacobi_eigen(Matrix a) {
    const std::size_t n = a.size();
    Matrix v = identity(n);
    double total = 0.0;
    for (const Vec& row : a)
        for (const double x : row) total += x * x;
    for (int sweep = 0; sweep < 100; ++sweep) {
        double off = 0.0;
        for (std::size_t p = 0; p < n; ++p)
            for (std::size_t q = p + 1; q < n; ++q) off += a[p][q] * a[p][q];
        if (off <= 1e-34 * total || off == 0.0) break;
        for (std::size_t p = 0; p < n; ++p)
            for (std::size_t q = p + 1; q < n; ++q) {
                if (a[p][q] == 0.0) continue;
                const double theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
                const double t = std::fabs(theta) > 1e150 ? 0.5 / theta
                                                          : std::copysign(1.0, theta) /
                                                                (std::fabs(theta) + std::sqrt(theta * theta + 1.0));
                const double c = 1.0 / std::sqrt(t * t + 1.0), s = t * c;
                for (std::size_t k = 0; k < n; ++k) {
                    const double kp = a[k][p], kq = a[k][q];
                    a[k][p] = c * kp - s * kq;
                    a[k][q] = s * kp + c * kq;
                }
                for (std::size_t k = 0; k < n; ++k) {
                    const double pk = a[p][k], qk = a[q][k];
                    a[p][k] = c * pk - s * qk;
                    a[q][k] = s * pk + c * qk;
                }
                a[p][q] = a[q][p] = 0.0;
                for (std::size_t k = 0; k < n; ++k) {
                    const double kp = v[k][p], kq = v[k][q];
                    v[k][p] = c * kp - s * kq;
                    v[k][q] = s * kp + c * kq;
                }
            }
    }
    std::vector<std::size_t> order(n);
    std::iota(order.begin(), order.end(), std::size_t{0});
    std::ranges::sort(order, [&](std::size_t i, std::size_t j) { return a[i][i] < a[j][j]; });
    Eigen e{Vec(n), Matrix(n, Vec(n))};
    for (std::size_t k = 0; k < n; ++k) {
        e.values[k] = a[order[k]][order[k]];
        for (std::size_t i = 0; i < n; ++i) e.vectors[i][k] = v[i][order[k]];
    }
    return e;
}

// ---- hedge.qp.solve ----

namespace {

double trading_cost(const QpProblem& p, const Vec& x) {
    double c = 0.0;
    for (std::size_t j = 0; j < x.size(); ++j) {
        if (p.half_spreads) c += (*p.half_spreads)[j] * std::fabs(x[j]);
        if (p.impact) c += (*p.impact)[j] * x[j] * x[j];
    }
    return c;
}

double margin_used(const QpProblem& p, const Vec& x) {
    double m = 0.0;
    if (p.margin_rates)
        for (std::size_t j = 0; j < x.size(); ++j) m += (*p.margin_rates)[j] * std::fabs(x[j]);
    return m;
}

// Wave 4a with a spread or margin term, by sign states (ruling I-48). f = x'Hx + 2c'x + 2 sum k_j |x_j|, with
// k = cost_weight half_spreads / 2, and optionally sum m_j |x_j| <= limit. A sign state fixes s_j = +1 or -1 for
// each instrument whose sign is open; in its closed orthant |x_j| = s_j x_j, so f is a smooth strictly convex QP
// and the margin one linear row, solved by the dual active-set method. At the orthant's minimiser, an instrument
// held at 0 by its sign row has multiplier nu; the subgradient condition of the whole problem there is
// nu <= 2 (k_j + mu m_j) (mu the margin multiplier). If every such test holds, the KKT conditions of the whole
// (convex) problem hold and x is its minimiser. Otherwise the worst violator's sign flips: x (with x_j = 0) stays
// feasible in the new orthant, so f does not rise. A repeated sign state is reported as E_NO_CONVERGENCE; the
// property tests compare the result with the orthant enumeration.
class SignStates {
public:
    SignStates(const QpProblem& p, const Normal& q, const Matrix& reduced, const NullSpace& ns,
               const std::vector<Bound>& lower, const std::vector<Bound>& upper, double cost_weight)
        : q_(q), reduced_(reduced), ns_(ns), lower_(lower), upper_(upper), n_(q.c.size()), k_(n_, 0.0), m_(n_, 0.0),
          sign_(n_, 0) {
        if (p.half_spreads)
            for (std::size_t j = 0; j < n_; ++j) k_[j] = 0.5 * cost_weight * (*p.half_spreads)[j];
        if (p.margin_rates) {
            m_ = *p.margin_rates;
            limit_ = *p.margin_limit;
            margined_ = true;
        }
        for (std::size_t j = 0; j < n_; ++j) {
            if (k_[j] == 0.0 && m_[j] == 0.0) continue;
            if (!lower.empty() && lower[j] && *lower[j] >= 0.0) sign_[j] = 1;
            else if (!upper.empty() && upper[j] && *upper[j] <= 0.0) sign_[j] = -1;
            else free_.push_back(j);
        }
    }

    Vec solve() {
        if (reduced_.empty()) return fixed();
        Vec x = run(k_, false, std::nullopt);
        if (!margined_ || margin(x) <= limit_ + 1e-12 * (limit_ + margin(x))) return x;
        // The margin binds. Start from the orthant of a margin-minimising point: the problem with a margin
        // penalty far above every gradient. Its margin is the least possible to O(1/penalty); above the limit by
        // more than the I-46 tolerance, no point is feasible.
        double scale = 1.0, least = std::numeric_limits<double>::infinity();
        for (std::size_t j = 0; j < n_; ++j) {
            scale = std::max(scale, std::fabs(q_.c[j]) + std::fabs(dot(q_.h[j], x)));
            if (m_[j] > 0.0) least = std::min(least, m_[j]);
        }
        Vec heavy = k_;
        for (std::size_t j = 0; j < n_; ++j) heavy[j] += 1e9 * scale / least * m_[j];
        const Vec start = run(heavy, false, std::nullopt);
        if (margin(start) > limit_ + 1e-9 * std::max(1.0, limit_))
            throw Error("E_INFEASIBLE", "no point satisfies the equalities, the bounds and the margin limit");
        std::vector<int> from = sign_;
        for (const std::size_t j : free_) from[j] = start[j] < 0.0 ? -1 : 1;
        return run(k_, true, from);
    }

private:
    double margin(const Vec& x) const {
        double s = 0.0;
        for (std::size_t j = 0; j < n_; ++j) s += m_[j] * std::fabs(x[j]);
        return s;
    }

    // k = n: the equalities fix x; only feasibility is left.
    Vec fixed() const {
        Vec x = bounded_minimiser(reduced_, {}, ns_, lower_, upper_);
        if (margined_ && margin(x) > limit_ + 1e-9 * std::max(1.0, limit_))
            throw Error("E_INFEASIBLE", "the equalities break the margin limit");
        return x;
    }

    // The orthant QP for the current signs: sign rows as bounds, the linear cost s_j k_j, the margin row.
    Vec orthant(const Vec& k, bool with_margin, Multipliers& mult) const {
        std::vector<Bound> lo(n_), up(n_);
        Vec c = q_.c, row;
        for (std::size_t j = 0; j < n_; ++j) {
            if (!lower_.empty()) lo[j] = lower_[j];
            if (!upper_.empty()) up[j] = upper_[j];
            if (sign_[j] > 0) lo[j] = std::max(lo[j].value_or(0.0), 0.0);
            if (sign_[j] < 0) up[j] = std::min(up[j].value_or(0.0), 0.0);
            c[j] += k[j] * double(sign_[j]);
        }
        if (with_margin) {  // -sum m_j s_j x_j >= -limit
            row.assign(n_, 0.0);
            for (std::size_t j = 0; j < n_; ++j) row[j] = -m_[j] * double(sign_[j]);
        }
        Vec hxp(c);
        for (std::size_t i = 0; i < n_; ++i) hxp[i] += dot(q_.h[i], ns_.xp);
        return bounded_minimiser(reduced_, project(ns_.z, hxp), ns_, lo, up, with_margin ? &row : nullptr, -limit_,
                                 &mult);
    }

    Vec run(const Vec& k, bool with_margin, std::optional<std::vector<int>> from) {
        if (from) {
            sign_ = *from;
        } else {  // signs of the smooth minimiser, which lies in its own orthant
            const Vec smooth = bounded_minimiser(reduced_, project(ns_.z, gradient_at_xp(q_.c)), ns_, lower_, upper_);
            for (const std::size_t j : free_) sign_[j] = smooth[j] < 0.0 ? -1 : 1;
        }
        std::vector<std::vector<int>> seen;
        const long long cap = detail::effort_cap(10 * (long long)n_ + 100);  // R6-6.1
        for (long long iteration = 0;; ++iteration) {
            if (iteration >= cap) throw Error("E_NO_CONVERGENCE", "the sign-state method passed 10 n + 100 iterations (R6-6.1)");
            seen.push_back(sign_);
            Multipliers mult;
            Vec x = orthant(k, with_margin, mult);
            const double mu = with_margin ? mult.general : 0.0;
            double scale = 0.0;
            for (std::size_t j = 0; j < n_; ++j)
                scale = std::max(scale, std::fabs(q_.c[j] + dot(q_.h[j], x)) + k[j] + mu * m_[j]);
            std::size_t worst = n_;
            double excess = 1e-10 * scale;
            for (const std::size_t j : free_) {
                const double nu = sign_[j] > 0 ? mult.lower[j] : mult.upper[j];
                const double over = nu - 2.0 * (k[j] + mu * m_[j]);
                if (over > excess) {
                    excess = over;
                    worst = j;
                }
            }
            if (worst == n_) {
                for (const std::size_t j : free_)  // a coordinate held by its sign row is exactly 0
                    if ((sign_[j] > 0 ? mult.lower[j] : mult.upper[j]) > 0.0) x[j] = 0.0;
                double xmax = 1.0;  // R6-6.1 kink: |x_j| <= 1e-11 max(1, max |x|) is at its kink
                for (const double v : x) xmax = std::max(xmax, std::fabs(v));
                for (const std::size_t j : free_)
                    if (std::fabs(x[j]) <= 1e-11 * xmax) x[j] = 0.0;
                return x;
            }
            sign_[worst] = -sign_[worst];
            if (std::ranges::find(seen, sign_) != seen.end())
                throw Error("E_NO_CONVERGENCE", "the sign-state method revisited a state");
        }
    }

    Vec gradient_at_xp(const Vec& c) const {
        Vec g(c);
        for (std::size_t i = 0; i < n_; ++i) g[i] += dot(q_.h[i], ns_.xp);
        return g;
    }

    const Normal& q_;
    const Matrix& reduced_;
    const NullSpace& ns_;
    const std::vector<Bound>& lower_;
    const std::vector<Bound>& upper_;
    std::size_t n_;
    Vec k_, m_;
    double limit_ = 0.0;
    bool margined_ = false;
    std::vector<int> sign_;
    std::vector<std::size_t> free_;
};

// Test oracle only (ruling I-48 retired it from the operation). In each closed orthant (a sign for every instrument with such a term)
// |x_j| = s_j x_j, so the spread cost is linear and the margin one linear row: a strictly convex QP for the
// dual active-set method. The orthants cover the space, so the least of their minima is the minimiser of the
// whole problem, and no feasible orthant means no feasible point (E_INFEASIBLE, exactly). Signs fixed by the
// bounds are not enumerated; the rest are, up to 20 (the oracle's own cap).
Vec orthant_minimiser(const QpProblem& p, const Normal& q, const Matrix& reduced, const NullSpace& ns,
                      const std::vector<Bound>& lower, const std::vector<Bound>& upper, double cost_weight) {
    const std::size_t n = q.c.size();
    std::vector<std::size_t> free;
    std::vector<int> sign(n, 0);
    for (std::size_t j = 0; j < n; ++j) {
        const bool term = (p.half_spreads && (*p.half_spreads)[j] > 0.0) || (p.margin_rates && (*p.margin_rates)[j] > 0.0);
        if (!term) continue;
        const bool lo_pos = !lower.empty() && lower[j] && *lower[j] >= 0.0;
        const bool up_neg = !upper.empty() && upper[j] && *upper[j] <= 0.0;
        if (lo_pos) sign[j] = 1;
        else if (up_neg) sign[j] = -1;
        else free.push_back(j);
    }
    if (free.size() > 20) throw Error("E_LIMIT", "the test oracle enumerates at most 20 signs", "half_spreads");
    std::optional<Vec> best;
    double best_f = 0.0;
    for (std::size_t mask = 0; mask < (std::size_t{1} << free.size()); ++mask) {
        for (std::size_t i = 0; i < free.size(); ++i) sign[free[i]] = (mask >> i) & 1 ? -1 : 1;
        std::vector<Bound> lo(n), up(n);
        bool empty = false;
        Vec c = q.c;
        for (std::size_t j = 0; j < n; ++j) {
            if (!lower.empty()) lo[j] = lower[j];
            if (!upper.empty()) up[j] = upper[j];
            if (sign[j] > 0) lo[j] = std::max(lo[j].value_or(0.0), 0.0);
            if (sign[j] < 0) up[j] = std::min(up[j].value_or(0.0), 0.0);
            if (lo[j] && up[j] && *lo[j] > *up[j]) empty = true;
            if (p.half_spreads) c[j] += 0.5 * cost_weight * (*p.half_spreads)[j] * double(sign[j]);
        }
        if (empty) continue;
        Vec hxp(c);
        for (std::size_t i = 0; i < n; ++i) hxp[i] += dot(q.h[i], ns.xp);
        const Vec g0 = project(ns.z, hxp);
        Vec margin_row;  // -sum m_j s_j x_j >= -limit
        if (p.margin_rates) {
            margin_row.assign(n, 0.0);
            for (std::size_t j = 0; j < n; ++j) margin_row[j] = -(*p.margin_rates)[j] * double(sign[j]);
        }
        Vec x;
        try {
            x = bounded_minimiser(reduced, g0, ns, lo, up, p.margin_rates ? &margin_row : nullptr,
                                  p.margin_limit ? -*p.margin_limit : 0.0);
        } catch (const Error& e) {
            if (e.code() == "E_INFEASIBLE") continue;
            throw;
        }
        const double f = objective_of(residual_of(p.a, p.b, x), p.weights, p.ridge, x) + cost_weight * trading_cost(p, x);
        if (!best || f < best_f) {
            best = std::move(x);
            best_f = f;
        }
    }
    if (!best) throw Error("E_INFEASIBLE", "no point satisfies the equalities, the bounds and the margin limit");
    return *best;
}

}  // namespace

namespace {
QpResult solve_qp_impl(const QpProblem& p, bool by_orthants);
}  // namespace

QpResult solve_qp(const QpProblem& p) { return solve_qp_impl(p, false); }
QpResult detail::solve_qp_by_orthants(const QpProblem& p) { return solve_qp_impl(p, true); }

namespace {
QpResult solve_qp_impl(const QpProblem& p, bool by_orthants) {
    // Check 1: shapes.
    const std::size_t n = check_ls_shapes(p.a, p.b, p.weights);
    input_if(p.eq_matrix.has_value() != p.eq_rhs.has_value(), "eq_matrix", "eq_matrix and eq_rhs go together");
    const Matrix no_rows;
    const Matrix& e = p.eq_matrix ? *p.eq_matrix : no_rows;
    if (p.eq_matrix) {
        for (const Vec& row : e) input_if(row.size() != n, "eq_matrix", "rows must have one entry per instrument");
        input_if(p.eq_rhs->size() != e.size(), "eq_rhs", "length differs from the rows of eq_matrix");
    }
    input_if(p.lower && p.lower->size() != n, "lower", "length differs from the instruments");
    input_if(p.upper && p.upper->size() != n, "upper", "length differs from the instruments");
    const std::vector<Bound> none;
    const std::vector<Bound>& lower = p.lower ? *p.lower : none;
    const std::vector<Bound>& upper = p.upper ? *p.upper : none;
    // Check 2: MIN_NORM refuses bounds (I-5).
    const auto any_bound = [](const std::vector<Bound>& v) { return std::ranges::any_of(v, [](const Bound& b) { return b.has_value(); }); };
    input_if(p.singular == Singular::MinNorm && (any_bound(lower) || any_bound(upper)), "singular",
             "MIN_NORM does not take bounds");
    // Check 3: domain.
    check_ls_domain(p.weights, p.ridge);
    for (std::size_t j = 0; j < lower.size() && j < upper.size(); ++j)
        domain_if(lower[j] && upper[j] && *lower[j] > *upper[j], "lower", "a lower bound is above its upper bound");
    // Wave 4a checks, after wave 1 checks 1 to 3 (I-25).
    const bool costed = p.half_spreads || p.impact || p.cost_weight || p.margin_rates || p.margin_limit;
    for (const auto& [v, field] : {std::pair{&p.half_spreads, "half_spreads"}, {&p.impact, "impact"},
                                   {&p.margin_rates, "margin_rates"}})
        input_if(*v && (*v)->size() != n, field, "length differs from the instruments");
    input_if(p.margin_rates.has_value() != p.margin_limit.has_value(), "margin_rates",
             "margin_rates and margin_limit go together");
    input_if(p.singular == Singular::MinNorm && costed, "singular", "MIN_NORM does not take costs or margin");
    for (const auto& [v, field] : {std::pair{&p.half_spreads, "half_spreads"}, {&p.impact, "impact"},
                                   {&p.margin_rates, "margin_rates"}})
        if (*v)
            for (const double x : **v) domain_if(x < 0.0, field, "entries must be at least 0");
    const double cost_weight = p.cost_weight.value_or(1.0);
    domain_if(cost_weight < 0.0, "cost_weight", "must be at least 0");
    domain_if(p.margin_limit && *p.margin_limit < 0.0, "margin_limit", "must be at least 0");
    // The Hessian first: its diagonal gives the R6-6.2 scaling of both rank decisions.
    Normal q = normal_equations(p.a, p.b, p.weights, p.ridge);
    if (p.impact)  // impact counts like a ridge (I-26)
        for (std::size_t j = 0; j < n; ++j) q.h[j][j] += cost_weight * (*p.impact)[j];
    const Vec dsc = jacobi_scale(q.h);
    // Check 4: equality rank, on E D with unit rows (R6-6.2).
    const std::size_t k = e.size();
    Matrix ed(k, Vec(n, 0.0));
    for (std::size_t i = 0; i < k; ++i) {
        double norm = 0.0;
        for (std::size_t j = 0; j < n; ++j) norm += (e[i][j] * dsc[j]) * (e[i][j] * dsc[j]);
        norm = std::sqrt(norm);
        for (std::size_t j = 0; j < n; ++j) ed[i][j] = norm > 0.0 ? e[i][j] * dsc[j] / norm : 0.0;
    }
    if (k > 0) {
        if (k > n) throw Error("E_SINGULAR", "more equalities than instruments", "eq_matrix");
        // One-sided Jacobi returns one value per column, so pass (E D)^T (n x k, k <= n): k singular values.
        Matrix et(n, Vec(k));
        for (std::size_t i = 0; i < k; ++i)
            for (std::size_t j = 0; j < n; ++j) et[j][i] = ed[i][j];
        const Vec sv = singular_values(et);
        if (sv.back() <= singular_threshold * sv.front())
            throw Error("E_SINGULAR", "the equality rows are linearly dependent", "eq_matrix");
    }
    // Check 5: reduced Hessian Z^T D H D Z, Z spanning the null space of E D, against the largest eigenvalue of
    // D H D (I-3 as amended by R6-6.2). The solve itself uses the unscaled form.
    const Matrix hs = scaled(q.h, dsc);
    const double hs_max = largest_abs(jacobi_eigen(hs).values);
    const NullSpace nss = null_space(ed, Vec(k, 0.0), n);
    const Vec res = jacobi_eigen(project(nss.z, hs)).values;
    const auto rank = std::ranges::count_if(res, [&](double v) { return v > singular_threshold * hs_max; });
    const double h_max = largest_abs(jacobi_eigen(q.h).values);
    const NullSpace ns = null_space(e, k ? *p.eq_rhs : Vec{}, n);
    const Matrix reduced = project(ns.z, q.h);
    const Eigen re = jacobi_eigen(reduced);
    const double threshold = singular_threshold * h_max;
    if (p.singular == Singular::Error && std::size_t(rank) < reduced.size())
        throw Error("E_SINGULAR", "the hedge has no unique minimiser", "a");
    // Gradient of the reduced objective at y = 0, halved: Z^T (H x_p + c).
    Vec hxp(q.c);
    for (std::size_t i = 0; i < n; ++i) hxp[i] += dot(q.h[i], ns.xp);
    const Vec g0 = project(ns.z, hxp);
    Vec x;
    if (p.singular == Singular::MinNorm) {
        // y = -(Z^T H Z)^+ g0, eigenvalues at or below the threshold dropped [GV13 5.5].
        Vec y(reduced.size(), 0.0);
        for (std::size_t c = 0; c < reduced.size(); ++c) {
            if (re.values[c] <= threshold) continue;
            double s = 0.0;
            for (std::size_t i = 0; i < reduced.size(); ++i) s += re.vectors[i][c] * g0[i];
            for (std::size_t i = 0; i < reduced.size(); ++i) y[i] -= re.vectors[i][c] * s / re.values[c];
        }
        x = ns.xp;
        for (std::size_t j = 0; j < n; ++j) x[j] += dot(ns.z[j], y);
    } else if (!p.half_spreads && !p.margin_rates) {
        // Check 6 (feasibility) happens inside: E_INFEASIBLE when no point exists (I-14).
        x = bounded_minimiser(reduced, g0, ns, lower, upper);
    } else {
        x = by_orthants ? orthant_minimiser(p, q, reduced, ns, lower, upper, cost_weight)
                        : SignStates(p, q, reduced, ns, lower, upper, cost_weight).solve();
    }
    for (double& v : x) v += 0.0;  // no negative zero in outputs (F-3)
    QpResult out;
    out.residual = residual_of(p.a, p.b, x);
    out.risk = objective_of(out.residual, p.weights, p.ridge, x);
    out.cost = trading_cost(p, x);
    out.margin = margin_used(p, x);
    out.objective = out.risk + cost_weight * out.cost;
    out.costed = costed;
    out.margined = p.margin_rates.has_value();
    out.x = std::move(x);
    out.rank = rank;
    return out;
}

}  // namespace

// ---- hedge.integer.solve ----

namespace {

struct Candidate {
    std::vector<long long> lots;
    double objective;
};

// Depth-first enumeration of the integer points n with |R (n - centre)|^2 <= radius, R upper triangular with
// L H L = R^T R, coordinates from the last to the first [FP85], clipped to the lot bounds.
class LatticeSearch {
public:
    LatticeSearch(const Matrix& r, const Vec& centre, const std::vector<double>& lo, const std::vector<double>& hi,
                  double radius, double slack_scale, const IntegerProblem& p)
        : r_(r), centre_(centre), lo_(lo), hi_(hi), radius_(radius), slack_scale_(slack_scale), p_(p),
          lots_(centre.size(), 0) {}

    std::vector<Candidate> run() {
        visit(centre_.size(), 0.0);
        return std::move(found_);
    }

private:
    void visit(std::size_t level, double partial) {
        // R6-6.1: at most 1,000,000 lattice points or nodes, then E_NO_CONVERGENCE.
        if (++nodes_ > detail::effort_cap(1000000))
            throw Error("E_NO_CONVERGENCE", "the lattice search passed 1,000,000 nodes (R6-6.1)");
        if (level == 0) {
            leaf(partial);
            return;
        }
        const std::size_t i = level - 1;
        double shift = 0.0;
        for (std::size_t j = i + 1; j < centre_.size(); ++j) shift += r_[i][j] * (double(lots_[j]) - centre_[j]);
        const double c = centre_[i] - shift / r_[i][i];
        const double room = radius_ - partial;
        if (room < 0.0) return;
        const double half = std::sqrt(room) / std::fabs(r_[i][i]);
        const double from = std::max(std::ceil(c - half), lo_[i]), to = std::min(std::floor(c + half), hi_[i]);
        if (!(from <= to)) return;
        for (double v = from; v <= to; v += 1.0) {
            lots_[i] = (long long)v;
            const double term = r_[i][i] * (v - c);
            const double next = partial + term * term;
            if (next <= radius_) visit(i, next);
        }
    }

    void leaf(double distance) {
        Vec x(lots_.size());
        for (std::size_t j = 0; j < x.size(); ++j) x[j] = p_.lot_sizes[j] * double(lots_[j]);
        const double f = objective_of(residual_of(p_.a, p_.b, x), p_.weights, p_.ridge, x);
        found_.push_back({lots_, f});
        radius_ = std::min(radius_, distance + 1e-9 * (distance + slack_scale_) + 1e-300);
    }

    const Matrix& r_;
    const Vec& centre_;
    const std::vector<double>& lo_;
    const std::vector<double>& hi_;
    double radius_, slack_scale_;
    const IntegerProblem& p_;
    std::vector<long long> lots_;
    std::vector<Candidate> found_;
    long long nodes_ = 0;
};

}  // namespace

IntegerResult solve_integer(const IntegerProblem& p) {
    const std::size_t n = check_ls_shapes(p.a, p.b, p.weights);
    input_if(p.lot_sizes.size() != n, "lot_sizes", "length differs from the instruments");
    input_if(p.lower_lots && p.lower_lots->size() != n, "lower_lots", "length differs from the instruments");
    input_if(p.upper_lots && p.upper_lots->size() != n, "upper_lots", "length differs from the instruments");
    check_ls_domain(p.weights, p.ridge);
    for (const double s : p.lot_sizes) domain_if(s <= 0.0, "lot_sizes", "each lot size must be above 0");
    std::vector<double> lo(n, -inf), hi(n, inf);
    std::vector<Bound> lower(n), upper(n);
    for (std::size_t j = 0; j < n; ++j) {
        if (p.lower_lots && (*p.lower_lots)[j]) lower[j] = lo[j] = double(*(*p.lower_lots)[j]);
        if (p.upper_lots && (*p.upper_lots)[j]) upper[j] = hi[j] = double(*(*p.upper_lots)[j]);
        domain_if(lo[j] > hi[j], "lower_lots", "a lower lot bound is above its upper bound");
    }
    // Check 3: strict convexity in lot units (I-6). Work in lot units throughout: A L.
    Matrix al = p.a;
    for (Vec& row : al)
        for (std::size_t j = 0; j < n; ++j) row[j] *= p.lot_sizes[j];
    const Normal q = normal_equations(al, p.b, p.weights, p.ridge);
    const Vec eig = jacobi_eigen(scaled(q.h, jacobi_scale(q.h))).values;  // R6-6.2
    if (eig.front() <= singular_threshold * largest_abs(eig))
        throw Error("E_SINGULAR", "the hedge in lot units has no unique minimiser", "a");
    // The continuous problem with the lot bounds as real bounds.
    const NullSpace free{Vec(n, 0.0), identity(n)};
    const Vec relaxed = bounded_minimiser(q.h, q.c, free, lower, upper);
    const Vec r_rel = residual_of(al, p.b, relaxed);
    IntegerResult out;
    out.continuous_objective = objective_of(r_rel, p.weights, p.ridge, relaxed);
    for (const double v : relaxed)  // I-49: beyond 2^52 the integers are not all representable
        if (std::fabs(v) > 4503599627370496.0) throw Error("E_LIMIT", "a lot count above 2^52", "lot_sizes");
    // Ellipsoid centre (the free minimiser) and Cholesky factor R = L^T.
    const Matrix l = cholesky_lower(q.h);
    Vec centre = cholesky_solve(l, q.c);
    for (double& v : centre) v = -v;
    Matrix r(n, Vec(n, 0.0));
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = i; j < n; ++j) r[i][j] = l[j][i];
    // Start point: the relaxed solution rounded into the box; its distance bounds the search.
    Vec start(n);
    double distance = 0.0;
    for (std::size_t j = 0; j < n; ++j) start[j] = std::clamp(std::round(relaxed[j]), lo[j], hi[j]);
    for (std::size_t i = 0; i < n; ++i) {
        double s = 0.0;
        for (std::size_t j = i; j < n; ++j) s += r[i][j] * (start[j] - centre[j]);
        distance += s * s;
    }
    const Vec r_free = residual_of(al, p.b, centre);
    const double scale = std::fabs(objective_of(r_free, p.weights, p.ridge, centre));
    const double radius = distance + 1e-9 * (distance + scale) + 1e-300;
    std::vector<Candidate> found = LatticeSearch(r, centre, lo, hi, radius, scale, p).run();
    // Ties (I-7, R6-11.5): within 1e-12 max(best, f(0)) of the best, then the smallest sum |n|, then lexicographic.
    double best = inf;
    for (const Candidate& c : found) best = std::min(best, c.objective);
    const Vec zero(n, 0.0);
    const double tie = 1e-12 * std::max(best, objective_of(residual_of(al, p.b, zero), p.weights, p.ridge, zero));
    const auto weight = [](const std::vector<long long>& v) {
        long long s = 0;
        for (const long long x : v) s += x < 0 ? -x : x;
        return s;
    };
    const Candidate* pick = nullptr;
    for (const Candidate& c : found) {
        if (c.objective - best > tie) continue;
        if (!pick || weight(c.lots) < weight(pick->lots) ||
            (weight(c.lots) == weight(pick->lots) && c.lots < pick->lots))
            pick = &c;
    }
    out.lots = pick->lots;
    out.x.resize(n);
    for (std::size_t j = 0; j < n; ++j) out.x[j] = p.lot_sizes[j] * double(out.lots[j]) + 0.0;
    out.residual = residual_of(p.a, p.b, out.x);
    out.objective = objective_of(out.residual, p.weights, p.ridge, out.x);
    out.rounding_cost = out.objective - out.continuous_objective;
    return out;
}

// ---- hedge.minvar.ratio ----

Matrix sample_covariance(const Vec& exposure, const Matrix& hedge_series) {
    const std::size_t k = hedge_series.size(), t = exposure.size();
    input_if(k < 1, "hedge_changes", "needs at least one series");
    for (const Vec& s : hedge_series) input_if(s.size() != t, "hedge_changes", "series of unequal length");
    input_if(t < k + 2, "exposure_changes", "needs at least k + 2 observations");
    std::vector<const Vec*> series{&exposure};
    for (const Vec& s : hedge_series) series.push_back(&s);
    Vec mean(k + 1, 0.0);
    for (std::size_t i = 0; i <= k; ++i) {
        for (const double v : *series[i]) mean[i] += v;
        mean[i] /= double(t);
    }
    Matrix s(k + 1, Vec(k + 1, 0.0));
    for (std::size_t i = 0; i <= k; ++i)
        for (std::size_t j = 0; j <= i; ++j) {
            double acc = 0.0;
            for (std::size_t o = 0; o < t; ++o) acc += ((*series[i])[o] - mean[i]) * ((*series[j])[o] - mean[j]);
            s[i][j] = s[j][i] = acc / double(t - 1);
        }
    return s;
}

MinVarResult min_variance(const Matrix& cov) {
    const std::size_t size = cov.size();
    input_if(size < 2, "covariance", "needs at least 2 x 2");
    double biggest = 0.0;
    for (const Vec& row : cov) {
        input_if(row.size() != size, "covariance", "must be square");
        biggest = std::max(biggest, largest_abs(row));
    }
    for (std::size_t i = 0; i < size; ++i)
        for (std::size_t j = 0; j < i; ++j)
            input_if(std::fabs(cov[i][j] - cov[j][i]) > singular_threshold * biggest, "covariance", "not symmetric");
    domain_if(cov[0][0] <= 0.0, "covariance", "the position must have a positive variance");
    const std::size_t k = size - 1;
    Matrix l(k, Vec(k, 0.0));
    for (std::size_t j = 0; j < k; ++j) {
        double d = cov[j + 1][j + 1];
        for (std::size_t m = 0; m < j; ++m) d -= l[j][m] * l[j][m];
        // R6-11.7 and R6-6.2: a negative pivot is an indefinite hedge block; a small pivot is judged on the
        // correlation (Jacobi-scaled) form, whose pivots are d / S_jj.
        const double sjj = cov[j + 1][j + 1];
        if (d < 0.0 || sjj < 0.0)
            throw Error("E_NOT_POSITIVE_DEFINITE", "the hedge covariance block is indefinite", "covariance");
        if (!(sjj > 0.0) || d / sjj <= singular_threshold)
            throw Error("E_SINGULAR", "the hedge instruments are linearly dependent", "covariance");
        l[j][j] = std::sqrt(d);
        for (std::size_t i = j + 1; i < k; ++i) {
            double s = cov[i + 1][j + 1];
            for (std::size_t m = 0; m < j; ++m) s -= l[i][m] * l[j][m];
            l[i][j] = s / l[j][j];
        }
    }
    // w = L^{-1} S_he; hedge = -L^{-T} w; variance after = S_00 - |w|^2.
    Vec w(k);
    double explained = 0.0;
    for (std::size_t i = 0; i < k; ++i) {
        double s = cov[i + 1][0];
        for (std::size_t m = 0; m < i; ++m) s -= l[i][m] * w[m];
        w[i] = s / l[i][i];
        explained += w[i] * w[i];
    }
    Vec h(k);
    for (std::size_t i = k; i-- > 0;) {
        double s = w[i];
        for (std::size_t m = i + 1; m < k; ++m) s -= l[m][i] * h[m];
        h[i] = s / l[i][i];
    }
    // I-44: below -1e-12 S_00 the covariance is not positive semi-definite; between that and 0 the hedged
    // variance is rounding and is returned as 0.
    double after = cov[0][0] - explained;
    if (after < -singular_threshold * cov[0][0])
        throw Error("E_NOT_POSITIVE_DEFINITE", "the hedged variance is below zero", "covariance");
    after = std::max(after, 0.0);
    MinVarResult out;
    for (const double v : h) out.hedge.push_back(-v + 0.0);
    out.variance_before = cov[0][0];
    out.variance_after = after;
    out.effectiveness = 1.0 - out.variance_after / out.variance_before;
    return out;
}

// ---- hedge.greeks.neutralise ----

Greeks unit_greeks(const Market& m, const Position& p) {
    if (p.instrument == Instrument::Underlying) return {1.0, 0.0, 0.0};
    const double t = *p.expiry_years, k = *p.strike, v = m.volatility, s = m.spot;
    const double sq = std::sqrt(t);
    const double d1 = (std::log(s / k) + (m.rate - m.dividend_yield + 0.5 * v * v) * t) / (v * sq);
    const double carry = std::exp(-m.dividend_yield * t), density = normal_pdf(d1);
    Greeks g;
    g.delta = p.instrument == Instrument::Call ? carry * normal_cdf(d1) : -carry * normal_cdf(-d1);
    g.gamma = carry * density / (s * v * sq);
    g.vega = s * carry * density * sq;
    return g;
}

namespace {
double greek_of(const Greeks& g, Greek which) {
    return which == Greek::Delta ? g.delta : which == Greek::Gamma ? g.gamma : g.vega;
}
void check_position(const Position& p, const char* field) {
    if (p.instrument == Instrument::Underlying)
        input_if(p.strike || p.expiry_years, field, "the underlying has no strike or expiry_years");
    else
        input_if(!p.strike || !p.expiry_years, field, "an option needs strike and expiry_years");
}
void check_option_domain(const Position& p, const char* field) {
    if (p.instrument == Instrument::Underlying) return;
    domain_if(*p.strike <= 0.0, field, "strike must be above 0");
    domain_if(*p.expiry_years <= 0.0, field, "expiry_years must be above 0");
}
}  // namespace

GreekHedge neutralise(const Market& m, const std::vector<Position>& book, const std::vector<Position>& hedges,
                      const std::vector<Greek>& targets) {
    for (const Position& p : book) check_position(p, "portfolio");
    for (const Position& p : hedges) check_position(p, "hedges");
    input_if(hedges.empty(), "hedges", "needs at least one hedge instrument");
    input_if(targets.size() != hedges.size(), "targets", "one target per hedge instrument (I-9)");
    for (std::size_t i = 0; i < targets.size(); ++i)
        for (std::size_t j = 0; j < i; ++j) input_if(targets[i] == targets[j], "targets", "a target is repeated");
    domain_if(m.spot <= 0.0, "spot", "must be above 0");
    domain_if(m.volatility <= 0.0, "volatility", "must be above 0");
    for (const Position& p : book) check_option_domain(p, "portfolio");
    for (const Position& p : hedges) check_option_domain(p, "hedges");
    GreekHedge out;
    for (const Position& p : book) {
        const Greeks g = unit_greeks(m, p);
        out.before.delta += p.quantity * g.delta;
        out.before.gamma += p.quantity * g.gamma;
        out.before.vega += p.quantity * g.vega;
    }
    std::vector<Greeks> unit;
    for (const Position& p : hedges) unit.push_back(unit_greeks(m, p));
    const std::size_t n = hedges.size();
    Matrix g(n, Vec(n));
    Vec rhs(n);
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = 0; j < n; ++j) g[i][j] = greek_of(unit[j], targets[i]);
        rhs[i] = -greek_of(out.before, targets[i]);
    }
    const Vec sv = singular_values(g);
    if (sv.back() <= singular_threshold * sv.front())
        throw Error("E_SINGULAR", "the hedge instruments cannot set the targets independently", "hedges");
    out.quantities = lu_solve(g, rhs);
    out.after = out.before;
    for (std::size_t j = 0; j < n; ++j) {
        out.quantities[j] += 0.0;
        out.after.delta += out.quantities[j] * unit[j].delta;
        out.after.gamma += out.quantities[j] * unit[j].gamma;
        out.after.vega += out.quantities[j] * unit[j].vega;
    }
    return out;
}

// ---- usecase.option_hedge_lots (use case 6, ruling R6-11.20) ----

LotHedgeResult option_hedge_lots(const Market& m, const std::vector<Position>& book, const std::vector<LotHedge>& hedges,
                                 const std::vector<Greek>& targets, long long max_lots) {
    for (const Position& p : book) check_position(p, "portfolio");
    for (const LotHedge& h : hedges) check_position(h.position, "hedges");
    input_if(hedges.empty(), "hedges", "needs at least one hedge instrument");
    input_if(targets.empty(), "targets", "needs at least one target");
    for (std::size_t i = 0; i < targets.size(); ++i)
        for (std::size_t j = 0; j < i; ++j) input_if(targets[i] == targets[j], "targets", "a target is repeated");
    domain_if(m.spot <= 0.0, "spot", "must be above 0");
    domain_if(m.volatility <= 0.0, "volatility", "must be above 0");
    for (const Position& p : book) check_option_domain(p, "portfolio");
    for (const LotHedge& h : hedges) {
        check_option_domain(h.position, "hedges");
        domain_if(!(h.lot_size > 0.0), "hedges", "lot_size must be above 0");
        domain_if(!(h.half_spread >= 0.0), "hedges", "half_spread must be at least 0");
    }
    domain_if(max_lots < 1, "max_lots", "must be at least 1");
    LotHedgeResult out;
    for (const Position& p : book) {
        const Greeks g = unit_greeks(m, p);
        out.before.delta += p.quantity * g.delta;
        out.before.gamma += p.quantity * g.gamma;
        out.before.vega += p.quantity * g.vega;
    }
    std::vector<Greeks> unit;
    for (const LotHedge& h : hedges) unit.push_back(unit_greeks(m, h.position));
    IntegerProblem ip;
    for (const Greek t : targets) {
        Vec row;
        for (std::size_t j = 0; j < hedges.size(); ++j) row.push_back(hedges[j].lot_size * greek_of(unit[j], t));
        ip.a.push_back(std::move(row));
        const double bt = greek_of(out.before, t);
        ip.b.push_back(bt);
        const double s = std::max(1.0, std::fabs(bt));
        ip.weights.push_back(1.0 / (s * s));
    }
    ip.lot_sizes.assign(hedges.size(), 1.0);
    ip.lower_lots = std::vector<std::optional<long long>>(hedges.size(), -max_lots);
    ip.upper_lots = std::vector<std::optional<long long>>(hedges.size(), max_lots);
    const IntegerResult r = solve_integer(ip);
    out.lots = r.lots;
    out.rounding_cost = r.rounding_cost;
    out.after = out.before;
    for (std::size_t j = 0; j < hedges.size(); ++j) {
        const double q = double(r.lots[j]) * hedges[j].lot_size;
        out.after.delta += q * unit[j].delta;
        out.after.gamma += q * unit[j].gamma;
        out.after.vega += q * unit[j].vega;
        out.hedge_cost += std::fabs(q) * hedges[j].half_spread;
    }
    return out;
}

// ---- hedge.beta.futures ----

BetaHedge beta_futures(double value, double beta, double target_beta, double futures_price, double multiplier,
                       Rounding rounding) {
    domain_if(value <= 0.0, "portfolio_value", "must be above 0");
    domain_if(futures_price <= 0.0, "futures_price", "must be above 0");
    domain_if(multiplier <= 0.0, "multiplier", "must be above 0");
    BetaHedge out;
    out.contracts = (target_beta - beta) * value / (futures_price * multiplier) + 0.0;
    // std::round rounds half away from zero (I-10).
    out.contracts_held = (rounding == Rounding::Nearest ? std::round(out.contracts) : out.contracts) + 0.0;
    out.beta_after = beta + out.contracts_held * futures_price * multiplier / value;
    return out;
}

// ---- hedge.residual.report ----

ResidualReport residual_report(const Matrix& a, const Vec& b, const Vec& x, const Matrix& cov) {
    input_if(a.empty(), "a", "needs at least one row");
    const std::size_t m = a.size(), n = a[0].size();
    input_if(n == 0, "a", "needs at least one column");
    for (const Vec& row : a) input_if(row.size() != n, "a", "rows of unequal length");
    input_if(b.size() != m, "b", "length differs from the rows of a");
    input_if(x.size() != n, "x", "length differs from the columns of a");
    input_if(cov.size() != m, "covariance", "must be m x m");
    double biggest = 0.0;
    for (const Vec& row : cov) {
        input_if(row.size() != m, "covariance", "must be m x m");
        biggest = std::max(biggest, largest_abs(row));
    }
    for (std::size_t i = 0; i < m; ++i)
        for (std::size_t j = 0; j < i; ++j)
            input_if(std::fabs(cov[i][j] - cov[j][i]) > singular_threshold * biggest, "covariance", "not symmetric");
    const Vec eig = jacobi_eigen(cov).values;
    if (eig.front() < -singular_threshold * largest_abs(eig))
        throw Error("E_NOT_POSITIVE_DEFINITE", "the covariance has a negative eigenvalue", "covariance");
    const auto quadratic = [&](const Vec& v, Vec* sv) {
        double q = 0.0;
        for (std::size_t i = 0; i < m; ++i) {
            const double si = dot(cov[i], v);
            if (sv) (*sv)[i] = si;
            q += v[i] * si;
        }
        return q;
    };
    ResidualReport out;
    out.variance_before = quadratic(b, nullptr);
    domain_if(out.variance_before <= 0.0, "b", "nothing to hedge: b'Sb is not above 0");
    out.residual = residual_of(a, b, x);
    Vec sr(m);
    out.variance_after = quadratic(out.residual, &sr);
    out.volatility_after = std::sqrt(std::max(out.variance_after, 0.0));
    out.effectiveness = 1.0 - out.variance_after / out.variance_before;
    for (std::size_t i = 0; i < m; ++i) out.contributions.push_back(out.residual[i] * sr[i] + 0.0);
    return out;
}

}  // namespace quantforge::hedging

namespace quantforge::hedging {

// ---- wave 4c: hedge.select.solve (08-hedging/instrument-selection.md, I-33 to I-35) ----

SelectResult select_instruments(const QpProblem& p, long long max_instruments, bool forbidden_keys) {
    // hedge.qp.solve checks 1 to 3.
    const std::size_t n = check_ls_shapes(p.a, p.b, p.weights);
    input_if(p.lower && p.lower->size() != n, "lower", "length differs from the instruments");
    input_if(p.upper && p.upper->size() != n, "upper", "length differs from the instruments");
    const std::vector<Bound> none;
    const std::vector<Bound>& lower = p.lower ? *p.lower : none;
    const std::vector<Bound>& upper = p.upper ? *p.upper : none;
    check_ls_domain(p.weights, p.ridge);
    for (std::size_t j = 0; j < lower.size() && j < upper.size(); ++j)
        domain_if(lower[j] && upper[j] && *lower[j] > *upper[j], "lower", "a lower bound is above its upper bound");
    // Check 3, 4 and 5.
    input_if(max_instruments < 1 || max_instruments > (long long)n, "max_instruments", "must be in 1..n");
    input_if(forbidden_keys, "eq_matrix", "selection takes no eq_matrix, eq_rhs or singular (I-33)");
    for (std::size_t j = 0; j < n; ++j) {
        domain_if(!lower.empty() && lower[j] && *lower[j] > 0.0, "lower", "a bound excludes 0 (I-33)");
        domain_if(!upper.empty() && upper[j] && *upper[j] < 0.0, "upper", "a bound excludes 0 (I-33)");
    }
    const Matrix hfull = normal_equations(p.a, p.b, p.weights, p.ridge).h;
    const Vec eig = jacobi_eigen(scaled(hfull, jacobi_scale(hfull))).values;  // R6-6.2
    if (eig.front() <= singular_threshold * largest_abs(eig))
        throw Error("E_SINGULAR", "the full hedge has no unique minimiser", "a");
    // Every subset of 1..K instruments, by size and then lexicographically, so the first one tied with the best
    // is the I-34 winner.
    std::vector<std::vector<std::size_t>> subsets;
    Vec objective;
    std::vector<QpResult> results;
    for (std::size_t size = 1; size <= std::size_t(max_instruments); ++size) {
        std::vector<std::size_t> s(size);
        std::iota(s.begin(), s.end(), std::size_t{0});
        for (;;) {
            QpProblem sub;
            sub.a.assign(p.a.size(), Vec(size));
            for (std::size_t r = 0; r < p.a.size(); ++r)
                for (std::size_t c = 0; c < size; ++c) sub.a[r][c] = p.a[r][s[c]];
            sub.b = p.b;
            sub.weights = p.weights;
            sub.ridge = p.ridge;
            if (!lower.empty()) {
                sub.lower = std::vector<Bound>(size);
                for (std::size_t c = 0; c < size; ++c) (*sub.lower)[c] = lower[s[c]];
            }
            if (!upper.empty()) {
                sub.upper = std::vector<Bound>(size);
                for (std::size_t c = 0; c < size; ++c) (*sub.upper)[c] = upper[s[c]];
            }
            results.push_back(solve_qp(sub));
            objective.push_back(results.back().objective);
            subsets.push_back(s);
            // Next combination in lexicographic order.
            std::size_t i = size;
            while (i > 0 && s[i - 1] == n - size + i - 1) --i;
            if (i == 0) break;
            ++s[i - 1];
            for (std::size_t j = i; j < size; ++j) s[j] = s[j - 1] + 1;
        }
    }
    const double best = *std::ranges::min_element(objective);
    std::size_t pick = 0;
    const Vec none(n, 0.0);  // R6-11.5: ties within 1e-12 max(best, f(0))
    const double f0 = objective_of(residual_of(p.a, p.b, none), p.weights, p.ridge, none);
    while (objective[pick] - best > 1e-12 * std::max(best, f0)) ++pick;
    SelectResult out;
    out.selected.assign(subsets[pick].begin(), subsets[pick].end());
    out.x.assign(n, 0.0);
    for (std::size_t c = 0; c < subsets[pick].size(); ++c) out.x[subsets[pick][c]] = results[pick].x[c];
    out.residual = results[pick].residual;
    out.objective = results[pick].objective;
    return out;
}

}  // namespace quantforge::hedging
