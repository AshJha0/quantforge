#include "quantforge/core/linalg.hpp"

#include <algorithm>
#include <cmath>
#include <functional>
#include <utility>

#include "quantforge/core/error.hpp"

namespace quantforge {
namespace {

void check_square(const Matrix& a) {
    if (a.empty()) throw Error("E_INPUT", "the matrix is empty", "a");
    for (const auto& row : a)
        if (row.size() != a.size()) throw Error("E_INPUT", "the matrix must be square", "a");
}

double largest_entry(const Matrix& a) {
    double m = 0.0;
    for (const auto& row : a)
        for (const double v : row) m = std::max(m, std::fabs(v));
    return m;
}

void check_symmetric(const Matrix& a) {
    const double limit = 1e-12 * largest_entry(a);
    for (std::size_t i = 0; i < a.size(); ++i)
        for (std::size_t j = 0; j < i; ++j)
            if (std::fabs(a[i][j] - a[j][i]) > limit) throw Error("E_INPUT", "the matrix is not symmetric", "a");
}

// Eliminates in place. A negative threshold means no singularity test.
std::vector<double> lu(Matrix& a, std::vector<double>& b, double threshold) {
    const std::size_t n = a.size();
    for (std::size_t k = 0; k < n; ++k) {
        std::size_t p = k;
        for (std::size_t i = k + 1; i < n; ++i)
            if (std::fabs(a[i][k]) > std::fabs(a[p][k])) p = i;
        if (threshold >= 0.0 && std::fabs(a[p][k]) <= threshold)
            throw Error("E_SINGULAR", "a pivot is below the threshold", "a");
        std::swap(a[k], a[p]);
        std::swap(b[k], b[p]);
        for (std::size_t i = k + 1; i < n; ++i) {
            const double m = a[i][k] / a[k][k];
            for (std::size_t j = k; j < n; ++j) a[i][j] -= m * a[k][j];
            b[i] -= m * b[k];
        }
    }
    std::vector<double> x(n);
    for (std::size_t i = n; i-- > 0;) {
        double s = b[i];
        for (std::size_t j = i + 1; j < n; ++j) s -= a[i][j] * x[j];
        x[i] = s / a[i][i];
    }
    return x;
}

}  // namespace

std::vector<double> lu_solve(Matrix a, std::vector<double> b) { return lu(a, b, -1.0); }

void check_full_rank(Matrix a, double relative) {
    std::vector<double> b(a.size(), 0.0);
    lu(a, b, relative * largest_entry(a));
}

std::vector<double> singular_values(Matrix a) {
    const std::size_t rows = a.size(), n = a[0].size();
    for (int sweep = 0; sweep < 60; ++sweep) {
        bool rotated = false;
        for (std::size_t p = 0; p + 1 < n; ++p) {
            for (std::size_t q = p + 1; q < n; ++q) {
                double alpha = 0.0, beta = 0.0, gamma = 0.0;
                for (std::size_t i = 0; i < rows; ++i) {
                    alpha += a[i][p] * a[i][p];
                    beta += a[i][q] * a[i][q];
                    gamma += a[i][p] * a[i][q];
                }
                if (std::fabs(gamma) <= 1e-16 * std::sqrt(alpha * beta)) continue;
                rotated = true;
                const double zeta = (beta - alpha) / (2.0 * gamma);
                const double t = std::copysign(1.0, zeta) / (std::fabs(zeta) + std::hypot(zeta, 1.0));
                const double c = 1.0 / std::hypot(t, 1.0), s = c * t;
                for (std::size_t i = 0; i < rows; ++i) {
                    const double x = a[i][p], y = a[i][q];
                    a[i][p] = c * x - s * y;
                    a[i][q] = s * x + c * y;
                }
            }
        }
        if (!rotated) break;
    }
    std::vector<double> out(n);
    for (std::size_t k = 0; k < n; ++k) {
        double s = 0.0;
        for (std::size_t i = 0; i < rows; ++i) s += a[i][k] * a[i][k];
        out[k] = std::sqrt(s);
    }
    std::ranges::sort(out, std::greater{});
    return out;
}

std::vector<double> solve_linear(const Matrix& a, const std::vector<double>& b) {
    check_square(a);
    if (b.size() != a.size()) throw Error("E_INPUT", "b has the wrong length", "b");
    Matrix m = a;
    std::vector<double> v = b;
    return lu(m, v, 1e-14 * largest_entry(a));
}

Matrix cholesky(const Matrix& a) {
    check_square(a);
    check_symmetric(a);
    const std::size_t n = a.size();
    Matrix l(n, std::vector<double>(n, 0.0));
    for (std::size_t j = 0; j < n; ++j) {
        double d = a[j][j];
        for (std::size_t k = 0; k < j; ++k) d -= l[j][k] * l[j][k];
        if (d <= 0.0) throw Error("E_NOT_POSITIVE_DEFINITE", "a pivot is not positive", "a");
        l[j][j] = std::sqrt(d);
        for (std::size_t i = j + 1; i < n; ++i) {
            double s = a[i][j];
            for (std::size_t k = 0; k < j; ++k) s -= l[i][k] * l[j][k];
            l[i][j] = s / l[j][j];
        }
    }
    return l;
}

// Cyclic Jacobi rotations: slow for large matrices, accurate for the small ones used here.
std::vector<double> eigen_symmetric(const Matrix& input) {
    check_square(input);
    check_symmetric(input);
    Matrix a = input;
    const std::size_t n = a.size();
    for (int sweep = 0; sweep < 100; ++sweep) {
        double off = 0.0;
        for (std::size_t i = 0; i < n; ++i)
            for (std::size_t j = 0; j < i; ++j) off += a[i][j] * a[i][j];
        if (off == 0.0) break;
        for (std::size_t p = 0; p + 1 < n; ++p) {
            for (std::size_t q = p + 1; q < n; ++q) {
                if (a[p][q] == 0.0) continue;
                const double theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
                const double t = std::copysign(1.0, theta) / (std::fabs(theta) + std::hypot(theta, 1.0));
                const double c = 1.0 / std::hypot(t, 1.0), s = t * c;
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
            }
        }
    }
    std::vector<double> values(n);
    for (std::size_t i = 0; i < n; ++i) values[i] = a[i][i];
    std::ranges::sort(values);
    return values;
}

}  // namespace quantforge
