#pragma once
#include <vector>

namespace quantforge {

using Matrix = std::vector<std::vector<double>>;

/// Solver primitive called with intermediate values; unchecked: caller guarantees finite inputs.
std::vector<double> solve_linear(const Matrix& a, const std::vector<double>& b);
Matrix cholesky(const Matrix& a);
std::vector<double> eigen_symmetric(const Matrix& a);
/// LU with partial pivoting and no singularity test.
/// unchecked: caller guarantees finite inputs
std::vector<double> lu_solve(Matrix a, std::vector<double> b);
/// E_SINGULAR when a pivot of the symmetric matrix is at or below relative times its largest entry.
/// unchecked: caller guarantees finite inputs
void check_full_rank(Matrix a, double relative);
/// Descending, by one-sided Jacobi.
/// unchecked: caller guarantees finite inputs
std::vector<double> singular_values(Matrix a);

}  // namespace quantforge
