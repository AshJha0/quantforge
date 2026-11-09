// CLI handlers, the hedge verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_hedge_solve(const In& in, Out& out) {
    const Matrix a = in.matrix("a");
    const Vec b = in.reals("b"), weights = in.reals("weights"), costs = in.reals("costs");
    const double lambda = in.real("lambda");
    in.ready();
    limit_if(!a.empty() && a[0].size() > 20, "a");
    const HedgeResult r = hedge_solve(a, b, weights, costs, lambda);
    out.key_reals("x", r.x);
    out.key_reals("residual", r.residual);
    out.key_real("objective", r.objective);
}

void op_spread_cost(const In& in, Out& out) {
    const Vec q = in.reals("quantities"), h = in.reals("half_spreads");
    in.ready();
    out.key_real("cost", spread_cost(q, h));
}

constexpr Entry hedge_ops[] = {
    {"hedge.solve", op_hedge_solve},
    {"hedge.spread_cost", op_spread_cost},
};
