#pragma once
#include <functional>
#include <optional>
#include <string>

namespace quantforge {

using Fn = std::function<double(double)>;

struct RootOptions {
    double x_tol = 1e-12;
    double f_tol = 0.0;
    long long max_iter = 200;
};

struct RootResult {
    double root;
    long long iterations;
    double residual;
    std::string termination;  // X_TOL, F_TOL or EXACT
};

struct Bracket {
    double a, b;
};

/// Root finders on a callback, used inside solvers; unchecked: caller guarantees finite inputs.
RootResult bisection(const Fn& f, double a, double b, const RootOptions& opt = {});
RootResult brent(const Fn& f, double a, double b, const RootOptions& opt = {});
RootResult newton(const Fn& f, const Fn& df, double x0, std::optional<Bracket> bracket, const RootOptions& opt = {});

}  // namespace quantforge
