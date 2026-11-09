#pragma once
#include <vector>

namespace quantforge {

enum class InterpMethod { Linear, LogLinear, CubicNatural, CubicClamped, CubicNotAKnot, MonotonePchip, Tension };

struct InterpParams {
    double slope_start = 0.0;
    double slope_end = 0.0;
    double tension = 0.0;
};

struct InterpResult {
    std::vector<double> values;
    std::vector<double> derivatives;  // empty for Linear and LogLinear
};

InterpResult interpolate(InterpMethod method, const std::vector<double>& x, const std::vector<double>& y,
                         const std::vector<double>& at, const InterpParams& params = {});

struct MonotoneConvexResult {
    std::vector<double> forwards;
    std::vector<double> zero_rates;
};

MonotoneConvexResult monotone_convex(const std::vector<double>& t, const std::vector<double>& r,
                                     const std::vector<double>& at, bool positive);

// ---- stage F (Q1): curve interpolations on ln S at node times (curve-framework.md "Stage F") ----

enum class NodeCurveMethod { MonotoneConvex, MonotonicLogCubic, TensionSpline };

/// ln S through nodes (t_i, ln S_i), i = 0..n, n >= 1, with the instantaneous forward f = -d ln S/dt
/// (right-hand at a node). Beyond t_n: a flat forward equal to f(t_n-) (ruling F-20).
class NodeLogCurve {
public:
    /// unchecked: caller guarantees finite inputs, t strictly increasing with at least 2 nodes, and
    /// tension in (0, 1000] for TensionSpline (ignored otherwise).
    NodeLogCurve(NodeCurveMethod method, std::vector<double> t, std::vector<double> ln_s, double tension = 0.0);
    /// unchecked: caller guarantees a finite t >= t_0.
    double ln_s(double t) const;
    /// unchecked: caller guarantees a finite t >= t_0.
    double forward(double t) const;

private:
    NodeCurveMethod method_;
    std::vector<double> t_, y_;
    double sigma_ = 0.0;
    std::vector<double> c_;    // MC: discrete forwards y_i (index 1..n); MLC: slopes m_i; tension: moments M_i
    std::vector<double> fn_;   // MC: node forwards f_i
    struct Value {
        double ln_s, forward;
    };
    Value section(std::size_t i, double t) const;  // on [t_i, t_{i+1}]
    double left_forward_at_end() const;
};

}  // namespace quantforge
