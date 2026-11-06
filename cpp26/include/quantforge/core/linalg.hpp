#pragma once
#include <vector>

namespace quantforge {

using Matrix = std::vector<std::vector<double>>;

std::vector<double> solve_linear(const Matrix& a, const std::vector<double>& b);
Matrix cholesky(const Matrix& a);
std::vector<double> eigen_symmetric(const Matrix& a);
/// LU with partial pivoting and no singularity test.
std::vector<double> lu_solve(Matrix a, std::vector<double> b);
/// E_SINGULAR when a pivot of the symmetric matrix is at or below relative times its largest entry.
void check_full_rank(Matrix a, double relative);
/// Descending, by one-sided Jacobi.
std::vector<double> singular_values(Matrix a);

}  // namespace quantforge
