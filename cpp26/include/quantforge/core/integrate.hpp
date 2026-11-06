#pragma once
#include "quantforge/core/root.hpp"

namespace quantforge {

double trapezoid(const Fn& f, double a, double b, long long n);
double simpson(const Fn& f, double a, double b, long long n);
double gauss_legendre(const Fn& f, double a, double b, long long n);
double adaptive_simpson(const Fn& f, double a, double b, double tol = 1e-10, long long max_depth = 50);

struct KronrodResult {
    double value;
    double error_estimate;
};
KronrodResult gauss_kronrod(const Fn& f, double a, double b, double tol = 1e-10, long long max_intervals = 500);

/// order is 1 or 2.
double central_difference(const Fn& f, double x, double h, long long order);

}  // namespace quantforge
