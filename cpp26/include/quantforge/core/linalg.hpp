#pragma once
#include <vector>

namespace quantforge {

using Matrix = std::vector<std::vector<double>>;

std::vector<double> solve_linear(const Matrix& a, const std::vector<double>& b);
Matrix cholesky(const Matrix& a);
std::vector<double> eigen_symmetric(const Matrix& a);

}  // namespace quantforge
