#include "quantforge/core/correlation.hpp"

#include <algorithm>
#include <cmath>

#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

void check_square(const Matrix& m) {
    if (m.empty()) throw Error("E_INPUT", "matrix is empty", "matrix");
    for (const auto& row : m)
        if (row.size() != m.size()) throw Error("E_INPUT", "matrix is not square", "matrix");
}

// Cyclic Jacobi on a symmetric matrix: eigenvalues w and eigenvectors as the columns of v.
void jacobi(Matrix a, std::vector<double>& w, Matrix& v) {
    const std::size_t n = a.size();
    v.assign(n, std::vector<double>(n, 0.0));
    for (std::size_t i = 0; i < n; ++i) v[i][i] = 1.0;
    for (int sweep = 0; sweep < 100; ++sweep) {
        double off = 0.0;
        for (std::size_t p = 0; p < n; ++p)
            for (std::size_t q = p + 1; q < n; ++q) off += a[p][q] * a[p][q];
        if (off < 1e-300) break;
        for (std::size_t p = 0; p < n; ++p)
            for (std::size_t q = p + 1; q < n; ++q) {
                if (a[p][q] == 0.0) continue;
                const double theta = (a[q][q] - a[p][p]) / (2 * a[p][q]);
                const double t = (theta >= 0 ? 1.0 : -1.0) / (std::fabs(theta) + std::sqrt(theta * theta + 1));
                const double c = 1 / std::sqrt(t * t + 1), s = t * c;
                for (std::size_t k = 0; k < n; ++k) {
                    const double akp = a[k][p], akq = a[k][q];
                    a[k][p] = c * akp - s * akq;
                    a[k][q] = s * akp + c * akq;
                }
                for (std::size_t k = 0; k < n; ++k) {
                    const double apk = a[p][k], aqk = a[q][k];
                    a[p][k] = c * apk - s * aqk;
                    a[q][k] = s * apk + c * aqk;
                }
                for (std::size_t k = 0; k < n; ++k) {
                    const double vkp = v[k][p], vkq = v[k][q];
                    v[k][p] = c * vkp - s * vkq;
                    v[k][q] = s * vkp + c * vkq;
                }
            }
    }
    w.resize(n);
    for (std::size_t i = 0; i < n; ++i) w[i] = a[i][i];
}

Matrix symmetrised(const Matrix& m) {
    Matrix s = m;
    for (std::size_t i = 0; i < m.size(); ++i)
        for (std::size_t j = 0; j < m.size(); ++j) s[i][j] = (m[i][j] + m[j][i]) / 2;
    return s;
}

double pair_correlation(const std::vector<double>& w, const std::vector<double>& s, double index) {
    double own = 0.0, cross = 0.0;
    for (std::size_t i = 0; i < w.size(); ++i) {
        own += w[i] * w[i] * s[i] * s[i];
        for (std::size_t j = 0; j < w.size(); ++j)
            if (i != j) cross += w[i] * w[j] * s[i] * s[j];
    }
    return (index * index - own) / cross;
}

}  // namespace

CorrValidation corr_validate(const Matrix& m) {
    check_square(m);
    const std::size_t n = m.size();
    CorrValidation r{true, true, true, false, false, 0.0};
    for (std::size_t i = 0; i < n; ++i) {
        if (m[i][i] != 1.0) r.unit_diagonal = false;
        for (std::size_t j = 0; j < n; ++j) {
            if (m[i][j] != m[j][i]) r.symmetric = false;
            if (!(m[i][j] >= -1.0 && m[i][j] <= 1.0)) r.in_range = false;
        }
    }
    std::vector<double> w;
    Matrix v;
    jacobi(symmetrised(m), w, v);
    r.min_eigenvalue = *std::min_element(w.begin(), w.end());
    r.psd = r.min_eigenvalue >= -1e-10;
    r.valid = r.symmetric && r.unit_diagonal && r.in_range && r.psd;
    return r;
}

NearestCorr corr_nearest(const Matrix& m) {
    check_square(m);
    const std::size_t n = m.size();
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < n; ++j)
            if (m[i][j] != m[j][i]) throw Error("E_INPUT", "matrix is not symmetric", "matrix");
    // Higham's alternating projections with Dykstra's correction [S1].
    Matrix y = m, ds(n, std::vector<double>(n, 0.0)), r(n, std::vector<double>(n)), x(n, std::vector<double>(n));
    std::vector<double> w;
    Matrix v;
    bool converged = false;
    for (int it = 0; it < 100000 && !converged; ++it) {
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t j = 0; j < n; ++j) r[i][j] = y[i][j] - ds[i][j];
        jacobi(r, w, v);
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t j = 0; j < n; ++j) {
                double s = 0.0;
                for (std::size_t k = 0; k < n; ++k) s += v[i][k] * std::max(w[k], 0.0) * v[j][k];
                x[i][j] = s;
            }
        double change = 0.0;
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t j = 0; j < n; ++j) {
                ds[i][j] = x[i][j] - r[i][j];
                const double next = i == j ? 1.0 : x[i][j];
                change = std::max(change, std::fabs(next - y[i][j]));
                y[i][j] = next;
            }
        converged = change < 1e-14;
    }
    if (!converged) throw Error("E_NO_CONVERGENCE", "the nearest correlation matrix did not converge");
    double d = 0.0;
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < n; ++j) d += (y[i][j] - m[i][j]) * (y[i][j] - m[i][j]);
    return {y, std::sqrt(d)};
}

double corr_implied(const std::vector<double>& w, const std::vector<double>& vols, double index_vol) {
    if (w.size() < 2 || w.size() != vols.size()) throw Error("E_INPUT", "two names or more, with lists of one length");
    for (const double s : vols)
        if (!(s > 0)) throw Error("E_DOMAIN", "a vol is not above 0", "vols");
    if (!(index_vol > 0)) throw Error("E_DOMAIN", "index_vol is not above 0", "index_vol");
    return pair_correlation(w, vols, index_vol);
}

Dispersion corr_dispersion(const std::vector<double>& w, const std::vector<double>& k, double ki,
                           const std::vector<double>& s, double si, double n) {
    if (w.size() < 2 || k.size() != w.size() || s.size() != w.size())
        throw Error("E_INPUT", "two names or more, with lists of one length");
    for (const double x : k)
        if (!(x > 0)) throw Error("E_DOMAIN", "a vol strike is not above 0", "vol_strikes");
    if (!(ki > 0)) throw Error("E_DOMAIN", "index_vol_strike is not above 0", "index_vol_strike");
    for (const double x : s)
        if (!(x > 0)) throw Error("E_DOMAIN", "a realized vol is not above 0", "realized_vols");
    if (!(si > 0)) throw Error("E_DOMAIN", "index_realized_vol is not above 0", "index_realized_vol");
    Dispersion d;
    d.pnl = 0.0;
    for (std::size_t i = 0; i < w.size(); ++i) {
        d.constituent_variance_notionals.push_back(n * w[i] / (2 * k[i]));
        d.pnl += d.constituent_variance_notionals.back() * (s[i] * s[i] - k[i] * k[i]);
    }
    d.index_variance_notional = n / (2 * ki);
    d.pnl -= d.index_variance_notional * (si * si - ki * ki);
    d.implied_correlation = pair_correlation(w, k, ki);
    d.realized_correlation = pair_correlation(w, s, si);
    return d;
}

}  // namespace quantforge
