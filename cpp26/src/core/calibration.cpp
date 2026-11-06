#include "quantforge/core/calibration.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

using Vec = std::vector<double>;

std::size_t parameter_count(FitModel m) {
    switch (m) {
        case FitModel::NelsonSiegel: return 4;
        default: return 2;
    }
}

double dot(const Vec& a, const Vec& b) {
    double s = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i) s += a[i] * b[i];
    return s;
}

double norm(const Vec& a) { return std::sqrt(dot(a, a)); }

// Model value and its gradient in the parameters.
double model_at(FitModel m, double x, const Vec& p, Vec& grad) {
    if (m == FitModel::Linear) {
        grad = {1.0, x};
        return p[0] + p[1] * x;
    }
    if (m == FitModel::Exponential) {
        const double e = std::exp(-p[1] * x);
        grad = {e, -p[0] * x * e};
        return p[0] * e;
    }
    const double tau = p[3], a = x / tau, decay = std::exp(-a);
    if (a == 0.0) {
        grad = {1.0, 1.0, 0.0, 0.0};
        return p[0] + p[1];
    }
    const double e = (1.0 - decay) / a;
    const double de_da = (decay * a - (1.0 - decay)) / (a * a), da_dtau = -x / (tau * tau);
    const double de_dtau = de_da * da_dtau, ddecay_dtau = decay * x / (tau * tau);
    grad = {1.0, e, e - decay, (p[1] + p[2]) * de_dtau - p[2] * ddecay_dtau};
    return p[0] + p[1] * e + p[2] * (e - decay);
}

// The objective as a sum of squares, r . r, with its Jacobian.
class Problem {
public:
    explicit Problem(const FitInputs& in) : in_(in), prior_(in.prior.value_or(Vec(in.start.size(), 0.0))) {}

    void evaluate(const Vec& p, Vec& r, Matrix& j) const {
        const std::size_t n = p.size();
        r.clear();
        j.clear();
        if (in_.model == FitModel::Rosenbrock) {
            r = {1.0 - p[0], 10.0 * (p[1] - p[0] * p[0])};
            j = {{-1.0, 0.0}, {-20.0 * p[0], 10.0}};
        } else {
            Vec grad;
            for (std::size_t i = 0; i < in_.x.size(); ++i) {
                const double w = std::sqrt(in_.weights ? (*in_.weights)[i] : 1.0);
                const double m = model_at(in_.model, in_.x[i], p, grad);
                r.push_back(w * (m - in_.y[i]));
                for (double& g : grad) g *= w;
                j.push_back(grad);
            }
        }
        if (in_.regularisation > 0.0) {
            const double s = std::sqrt(in_.regularisation);
            for (std::size_t k = 0; k < n; ++k) {
                r.push_back(s * (p[k] - prior_[k]));
                Vec row(n, 0.0);
                row[k] = s;
                j.push_back(std::move(row));
            }
        }
    }

    double objective(const Vec& p) const {
        Vec r;
        Matrix j;
        evaluate(p, r, j);
        const double f = dot(r, r);
        return std::isfinite(f) ? f : std::numeric_limits<double>::infinity();
    }

    Vec gradient(const Vec& p) const {
        Vec r;
        Matrix j;
        evaluate(p, r, j);
        return gradient_of(r, j);
    }

    static Vec gradient_of(const Vec& r, const Matrix& j) {
        Vec g(j.empty() ? 0 : j[0].size(), 0.0);
        for (std::size_t i = 0; i < r.size(); ++i)
            for (std::size_t k = 0; k < g.size(); ++k) g[k] += 2.0 * j[i][k] * r[i];
        return g;
    }

    static Matrix normal_matrix(const Matrix& j, std::size_t n) {
        Matrix a(n, Vec(n, 0.0));
        for (const Vec& row : j)
            for (std::size_t x = 0; x < n; ++x)
                for (std::size_t y = 0; y < n; ++y) a[x][y] += row[x] * row[y];
        return a;
    }

private:
    const FitInputs& in_;
    Vec prior_;
};

constexpr double gradient_stop = 1e-8, step_stop = 1e-12;

bool small_step(const Vec& step, const Vec& p) { return norm(step) <= step_stop * (1.0 + norm(p)); }

const Vec& finite_gradient(const Vec& g) {
    for (const double v : g)
        if (!std::isfinite(v)) throw Error("E_NON_FINITE", "the gradient is not finite");
    return g;
}

[[noreturn]] void out_of_iterations() { throw Error("E_NO_CONVERGENCE", "max_iter reached"); }

struct Run {
    Vec p;
    long long iterations;
};

Run gauss_newton(const Problem& problem, Vec p, long long max_iter) {
    Vec r;
    Matrix j;
    for (long long it = 1; it <= max_iter; ++it) {
        problem.evaluate(p, r, j);
        const Vec g = finite_gradient(Problem::gradient_of(r, j));
        if (norm(g) <= gradient_stop) return {p, it - 1};
        Vec rhs(g.size());
        for (std::size_t k = 0; k < g.size(); ++k) rhs[k] = -g[k] / 2.0;
        Vec step = solve_linear(Problem::normal_matrix(j, p.size()), rhs);
        const double f = dot(r, r);
        for (int halving = 0; halving < 60; ++halving) {
            Vec trial = p;
            for (std::size_t k = 0; k < p.size(); ++k) trial[k] += step[k];
            if (problem.objective(trial) < f) {
                p = std::move(trial);
                break;
            }
            for (double& s : step) s /= 2.0;
        }
        if (small_step(step, p)) return {p, it};
    }
    out_of_iterations();
}

// Damped steps on the free variables; a variable pressed against its bound is held there, so the
// stopping point meets the first-order conditions of the bounded problem.
Run levenberg_marquardt(const Problem& problem, Vec p, const FitInputs& in, long long max_iter) {
    const std::size_t n = p.size();
    const auto clip = [&](std::size_t k, double v) {
        if (in.lower) v = std::max(v, (*in.lower)[k]);
        if (in.upper) v = std::min(v, (*in.upper)[k]);
        return v;
    };
    for (std::size_t k = 0; k < n; ++k) p[k] = clip(k, p[k]);
    double mu = 1e-3;
    Vec r;
    Matrix j;
    problem.evaluate(p, r, j);
    double f = dot(r, r);
    for (long long it = 1; it <= max_iter; ++it) {
        Vec g = finite_gradient(Problem::gradient_of(r, j));
        std::vector<char> held(n, 0);
        for (std::size_t k = 0; k < n; ++k) {
            const bool at_low = in.lower && p[k] <= (*in.lower)[k] && g[k] > 0.0;
            const bool at_high = in.upper && p[k] >= (*in.upper)[k] && g[k] < 0.0;
            if (at_low || at_high) {
                held[k] = 1;
                g[k] = 0.0;
            }
        }
        if (norm(g) <= gradient_stop) return {p, it - 1};
        Matrix a = Problem::normal_matrix(j, n);
        Matrix damped = a;
        Vec rhs(n);
        for (std::size_t k = 0; k < n; ++k) {
            damped[k][k] += mu * std::max(a[k][k], 1e-12);
            rhs[k] = -g[k] / 2.0;
            if (held[k]) {
                for (std::size_t c = 0; c < n; ++c) damped[k][c] = damped[c][k] = 0.0;
                damped[k][k] = 1.0;
                rhs[k] = 0.0;
            }
        }
        const Vec step = lu_solve(damped, rhs);
        Vec trial(n), moved(n);
        for (std::size_t k = 0; k < n; ++k) {
            trial[k] = clip(k, p[k] + step[k]);
            moved[k] = trial[k] - p[k];
        }
        const double ft = problem.objective(trial);
        if (ft < f) {
            p = std::move(trial);
            problem.evaluate(p, r, j);
            f = dot(r, r);
            mu = std::max(mu / 3.0, 1e-15);
            if (small_step(moved, p)) return {p, it};
        } else {
            if (small_step(moved, p)) return {p, it};
            mu *= 4.0;
        }
    }
    out_of_iterations();
}

// Inverse-Hessian updates, with a weak Wolfe line search by bisection.
Run bfgs(const Problem& problem, Vec p, long long max_iter) {
    const std::size_t n = p.size();
    Matrix h(n, Vec(n, 0.0));
    const auto reset = [&] {
        for (std::size_t i = 0; i < n; ++i) {
            std::ranges::fill(h[i], 0.0);
            h[i][i] = 1.0;
        }
    };
    reset();
    double f = problem.objective(p);
    Vec g = finite_gradient(problem.gradient(p));
    for (long long it = 1; it <= max_iter; ++it) {
        if (norm(g) <= gradient_stop) return {p, it - 1};
        Vec d(n, 0.0);
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t k = 0; k < n; ++k) d[i] -= h[i][k] * g[k];
        double slope = dot(d, g);
        if (slope >= 0.0) {
            reset();
            d = g;
            for (double& v : d) v = -v;
            slope = dot(d, g);
        }
        double lo = 0.0, hi = HUGE_VAL, t = it == 1 ? std::min(1.0, 1.0 / norm(g)) : 1.0;
        Vec trial(n), gt = g;
        double ft = f;
        bool found = false;
        for (int ls = 0; ls < 60; ++ls) {
            for (std::size_t k = 0; k < n; ++k) trial[k] = p[k] + t * d[k];
            ft = problem.objective(trial);
            if (ft > f + 1e-4 * t * slope) {
                hi = t;
            } else {
                gt = problem.gradient(trial);
                if (dot(gt, d) < 0.9 * slope) {
                    lo = t;
                } else {
                    found = true;
                    break;
                }
            }
            t = std::isinf(hi) ? 2.0 * lo : (lo + hi) / 2.0;
        }
        if (!found) {
            // At rounding level no step satisfies the conditions: restart once along the gradient.
            if (ft >= f) {
                bool identity = true;
                for (std::size_t i = 0; i < n; ++i)
                    for (std::size_t k = 0; k < n; ++k) identity = identity && h[i][k] == (i == k ? 1.0 : 0.0);
                if (identity) throw Error("E_NO_CONVERGENCE", "no acceptable step");
                reset();
                continue;
            }
            gt = problem.gradient(trial);
        }
        Vec s(n), y(n);
        for (std::size_t k = 0; k < n; ++k) {
            s[k] = trial[k] - p[k];
            y[k] = gt[k] - g[k];
        }
        p = trial;
        f = ft;
        g = finite_gradient(gt);
        if (small_step(s, p)) return {p, it};
        const double sy = dot(s, y);
        if (sy > 0.0) {
            Vec hy(n, 0.0);
            for (std::size_t i = 0; i < n; ++i)
                for (std::size_t k = 0; k < n; ++k) hy[i] += h[i][k] * y[k];
            const double yhy = dot(y, hy);
            for (std::size_t i = 0; i < n; ++i)
                for (std::size_t k = 0; k < n; ++k)
                    h[i][k] += (1.0 + yhy / sy) * s[i] * s[k] / sy - (hy[i] * s[k] + s[i] * hy[k]) / sy;
        }
    }
    out_of_iterations();
}

// Is x, on its support, the minimum? Solves there with the signs fixed, and tests all conditions.
bool polish(const Matrix& q, const Vec& q0, const Vec& pen, Vec& x) {
    const std::size_t n = x.size();
    std::vector<std::size_t> s;
    for (std::size_t i = 0; i < n; ++i)
        if (x[i] != 0.0) s.push_back(i);
    Vec exact(n, 0.0);
    if (!s.empty()) {
        Matrix a(s.size(), Vec(s.size()));
        Vec rhs(s.size());
        for (std::size_t i = 0; i < s.size(); ++i) {
            for (std::size_t k = 0; k < s.size(); ++k) a[i][k] = q[s[i]][s[k]];
            rhs[i] = -q0[s[i]] - pen[s[i]] * (x[s[i]] > 0.0 ? 1.0 : -1.0);
        }
        const Vec v = lu_solve(a, rhs);
        for (std::size_t i = 0; i < s.size(); ++i) {
            if (v[i] * x[s[i]] <= 0.0) return false;
            exact[s[i]] = v[i];
        }
    }
    for (std::size_t i = 0; i < n; ++i) {
        if (exact[i] != 0.0) continue;
        double g = q0[i];
        for (std::size_t k = 0; k < n; ++k) g += q[i][k] * exact[k];
        if (std::fabs(g) > pen[i] * (1.0 + 1e-12) + 1e-12) return false;
    }
    x = exact;
    return true;
}

}  // namespace

FitResult fit(const FitInputs& in) {
    const std::size_t n = in.start.size();
    if (in.x.size() != in.y.size()) throw Error("E_INPUT", "x and y differ in length");
    if (n != parameter_count(in.model)) throw Error("E_INPUT", "start has the wrong length", "start");
    const bool data_fit = in.model != FitModel::Rosenbrock;  // weights do not apply to Rosenbrock
    if (data_fit && in.weights && in.weights->size() != in.x.size())
        throw Error("E_INPUT", "weights have the wrong length", "weights");
    if (in.prior && in.prior->size() != n) throw Error("E_INPUT", "prior has the wrong length", "prior");
    if ((in.lower && in.lower->size() != n) || (in.upper && in.upper->size() != n))
        throw Error("E_INPUT", "bounds have the wrong length");
    if (data_fit && in.weights && std::ranges::any_of(*in.weights, [](double w) { return w < 0.0; }))
        throw Error("E_DOMAIN", "a weight is negative", "weights");
    if (in.regularisation < 0.0) throw Error("E_DOMAIN", "regularisation is negative", "regularisation");
    if ((in.lower || in.upper) && in.method != FitMethod::LevenbergMarquardt)
        throw Error("E_INPUT", "bounds need LEVENBERG_MARQUARDT");
    if (in.lower && in.upper)
        for (std::size_t k = 0; k < n; ++k)
            if ((*in.lower)[k] > (*in.upper)[k]) throw Error("E_INPUT", "lower is above upper");
    if (in.max_iter < 1) throw Error("E_INPUT", "max_iter must be at least 1", "max_iter");

    const Problem problem(in);
    Vec start = in.start;
    for (std::size_t k = 0; k < n; ++k) {
        if (in.lower) start[k] = std::max(start[k], (*in.lower)[k]);
        if (in.upper) start[k] = std::min(start[k], (*in.upper)[k]);
    }
    if (!std::isfinite(problem.objective(start))) throw Error("E_NON_FINITE", "the objective at start is not finite");
    Run run;
    switch (in.method) {
        case FitMethod::GaussNewton: run = gauss_newton(problem, start, in.max_iter); break;
        case FitMethod::LevenbergMarquardt: run = levenberg_marquardt(problem, start, in, in.max_iter); break;
        case FitMethod::Bfgs: run = bfgs(problem, start, in.max_iter); break;
    }
    Vec r;
    Matrix j;
    problem.evaluate(run.p, r, j);
    return {run.p, dot(r, r), run.iterations, "CONVERGED", r};
}

std::vector<Breach> check_bid_ask(const Vec& fitted, const Vec& bid, const Vec& ask) {
    if (fitted.size() != bid.size() || fitted.size() != ask.size()) throw Error("E_INPUT", "lengths differ");
    for (std::size_t i = 0; i < bid.size(); ++i)
        if (bid[i] > ask[i]) throw Error("E_INPUT", "bid is above ask");
    std::vector<Breach> out;
    for (std::size_t i = 0; i < fitted.size(); ++i) {
        if (fitted[i] < bid[i]) out.push_back({i, "BID", bid[i] - fitted[i]});
        else if (fitted[i] > ask[i]) out.push_back({i, "ASK", fitted[i] - ask[i]});
    }
    return out;
}

CurveReport curve_report(const RateConvention& c, Date as_of, const std::vector<OisQuote>& quotes,
                         CurveInterpolation interpolation) {
    constexpr double h = 1e-5;
    const SolvedCurve base = ois_bootstrap(c, as_of, quotes, interpolation, SolveMethod::Sequential);
    const std::size_t n = quotes.size();
    const auto zeros = [&](const std::vector<OisQuote>& q) {
        const Curve curve = ois_bootstrap(c, as_of, q, interpolation, SolveMethod::Sequential).curve;
        Vec z(n);
        for (std::size_t i = 0; i < n; ++i) z[i] = -curve.log_df(i) / curve.time(curve.pillars()[i].date);
        return z;
    };
    Matrix jac(n, Vec(n));
    std::vector<OisQuote> q = quotes;
    for (std::size_t k = 0; k < n; ++k) {
        q[k].rate = quotes[k].rate + h;
        const Vec up = zeros(q);
        q[k].rate = quotes[k].rate - h;
        const Vec down = zeros(q);
        q[k].rate = quotes[k].rate;
        for (std::size_t i = 0; i < n; ++i) jac[i][k] = (up[i] - down[i]) / (2.0 * h);
    }
    const Vec s = singular_values(jac);
    return {jac, s.back() == 0.0 ? HUGE_VAL : s.front() / s.back(), base.max_repricing_error};
}

HedgeResult hedge_solve(const Matrix& a, const Vec& b, const Vec& weights, const Vec& costs, double lambda) {
    if (a.empty() || a[0].empty()) throw Error("E_INPUT", "a is empty", "a");
    const std::size_t rows = a.size(), n = a[0].size();
    for (const Vec& row : a)
        if (row.size() != n) throw Error("E_INPUT", "a is ragged", "a");
    if (b.size() != rows || weights.size() != rows || costs.size() != n) throw Error("E_INPUT", "lengths do not match");
    if (std::ranges::any_of(weights, [](double w) { return w <= 0.0; })) throw Error("E_DOMAIN", "weights must be positive", "weights");
    if (std::ranges::any_of(costs, [](double c) { return c < 0.0; })) throw Error("E_DOMAIN", "a cost is negative", "costs");
    if (lambda < 0.0) throw Error("E_DOMAIN", "lambda is negative", "lambda");

    Matrix q(n, Vec(n, 0.0));  // 2 A^T W A
    Vec q0(n, 0.0);            // 2 A^T W b
    for (std::size_t r = 0; r < rows; ++r)
        for (std::size_t i = 0; i < n; ++i) {
            q0[i] += 2.0 * weights[r] * a[r][i] * b[r];
            for (std::size_t k = 0; k < n; ++k) q[i][k] += 2.0 * weights[r] * a[r][i] * a[r][k];
        }
    Matrix gram = q;
    for (Vec& row : gram)
        for (double& v : row) v /= 2.0;
    check_full_rank(gram, 1e-12);

    Vec pen(n);
    for (std::size_t i = 0; i < n; ++i) pen[i] = lambda * costs[i];
    // Coordinate descent finds the support; a linear solve on it is then exact.
    Vec x(n, 0.0);
    bool exact = false;
    for (long long sweep = 1; sweep <= 200000 && !exact; ++sweep) {
        double change = 0.0;
        for (std::size_t i = 0; i < n; ++i) {
            double g = q0[i];
            for (std::size_t k = 0; k < n; ++k)
                if (k != i) g += q[i][k] * x[k];
            const double v = std::fabs(g) <= pen[i] ? 0.0 : (g > 0.0 ? -(g - pen[i]) : -(g + pen[i])) / q[i][i];
            change = std::max(change, std::fabs(v - x[i]));
            x[i] = v;
        }
        if (sweep % 10 == 0 || change == 0.0) {
            Vec candidate = x;
            if (polish(q, q0, pen, candidate)) {
                x = candidate;
                exact = true;
            }
        }
        if (change == 0.0) break;
    }
    if (!exact) throw Error("E_NO_CONVERGENCE", "the hedge solve did not settle");
    HedgeResult out{x, Vec(rows), 0.0};
    for (std::size_t r = 0; r < rows; ++r) {
        double v = b[r];
        for (std::size_t i = 0; i < n; ++i) v += a[r][i] * x[i];
        out.residual[r] = v;
        out.objective += weights[r] * v * v;
    }
    for (std::size_t i = 0; i < n; ++i) out.objective += pen[i] * std::fabs(x[i]);
    return out;
}

double spread_cost(const Vec& quantities, const Vec& half_spreads) {
    if (quantities.size() != half_spreads.size()) throw Error("E_INPUT", "lengths differ");
    if (std::ranges::any_of(half_spreads, [](double h) { return h < 0.0; })) throw Error("E_DOMAIN", "a half spread is negative", "half_spreads");
    double cost = 0.0;
    for (std::size_t i = 0; i < quantities.size(); ++i) cost += std::fabs(quantities[i]) * half_spreads[i];
    return cost;
}

}  // namespace quantforge
