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

// ---- stage I wave 1: hedge solvers (08-hedging/hedge-solvers.md, rulings I-1 to I-14) ----

// Rulings C9 and I-12: an optional key may be absent, but null for it is E_SCHEMA.
bool present(const In& in, string_view key) {
    const Value* p = in.raw().find(key);
    if (!p) return false;
    if (p->kind == Kind::Null) schema(key, "null is not allowed");
    return true;
}

// lower, upper: Real or null items (I-12).
std::optional<std::vector<hedging::Bound>> bounds_of(const In& in, string_view key) {
    if (!present(in, key)) return std::nullopt;
    return in.maybe_reals(key);
}

// lower_lots, upper_lots: Integer or null items (I-12).
std::optional<std::vector<std::optional<long long>>> lot_bounds_of(const In& in, string_view key) {
    if (!present(in, key)) return std::nullopt;
    const Value& a = in.need(key);
    if (a.kind != Kind::Array) schema(key, "expected an array");
    std::vector<std::optional<long long>> out;
    for (const Value& item : a.items)
        out.push_back(item.kind == Kind::Null ? std::nullopt : std::optional<long long>(to_integer(item, key)));
    return out;
}

std::size_t widest_row(const Matrix& m) {
    std::size_t w = 0;
    for (const Vec& row : m) w = std::max(w, row.size());
    return w;
}

// Ruling I-4.
constexpr std::size_t max_factors = 1000, max_instruments = 200, max_equalities = 200, max_integer_instruments = 12,
                      max_positions = 1000, max_greek_hedges = 3;

void write_ls(Out& out, const Vec& x, const Vec& residual, double objective) {
    out.key_reals("x", x);
    out.key_reals("residual", residual);
    out.key_real("objective", objective);
}

void op_hedge_qp_solve(const In& in, Out& out) {
    hedging::QpProblem p;
    p.a = in.matrix("a");
    p.b = in.reals("b");
    p.weights = in.reals("weights");
    p.ridge = optional_real(in, "ridge", 0.0);
    if (present(in, "eq_matrix")) p.eq_matrix = in.matrix("eq_matrix");
    if (present(in, "eq_rhs")) p.eq_rhs = in.reals("eq_rhs");
    p.lower = bounds_of(in, "lower");
    p.upper = bounds_of(in, "upper");
    if (present(in, "singular"))
        p.singular = in.choice<hedging::Singular>(
            "singular", {{"ERROR", hedging::Singular::Error}, {"MIN_NORM", hedging::Singular::MinNorm}});
    limit_if(p.a.size() > max_factors, "a");
    limit_if(widest_row(p.a) > max_instruments, "a");
    limit_if(p.eq_matrix && p.eq_matrix->size() > max_equalities, "eq_matrix");
    in.ready();
    const hedging::QpResult r = hedging::solve_qp(p);
    write_ls(out, r.x, r.residual, r.objective);
    key_int(out, "rank", r.rank);
}

void op_hedge_integer_solve(const In& in, Out& out) {
    hedging::IntegerProblem p;
    p.a = in.matrix("a");
    p.b = in.reals("b");
    p.weights = in.reals("weights");
    p.ridge = optional_real(in, "ridge", 0.0);
    p.lot_sizes = in.reals("lot_sizes");
    p.lower_lots = lot_bounds_of(in, "lower_lots");
    p.upper_lots = lot_bounds_of(in, "upper_lots");
    limit_if(p.a.size() > max_factors, "a");
    limit_if(widest_row(p.a) > max_integer_instruments, "a");
    in.ready();
    const hedging::IntegerResult r = hedging::solve_integer(p);
    out.values.key("lots");
    out.values.begin_array();
    for (const long long n : r.lots) out.values.integer(n);
    out.values.end_array();
    write_ls(out, r.x, r.residual, r.objective);
    out.key_real("continuous_objective", r.continuous_objective);
    out.key_real("rounding_cost", r.rounding_cost);
}

void op_hedge_minvar_ratio(const In& in, Out& out) {
    const bool has_cov = present(in, "covariance"), has_exp = present(in, "exposure_changes"),
               has_hedge = present(in, "hedge_changes");
    const Matrix cov = has_cov ? in.matrix("covariance") : Matrix{};
    const Vec exposure = has_exp ? in.reals("exposure_changes") : Vec{};
    const Matrix series = has_hedge ? in.matrix("hedge_changes") : Matrix{};
    limit_if(cov.size() > max_instruments + 1, "covariance");
    limit_if(series.size() > max_instruments, "hedge_changes");
    in.ready();
    if (has_cov == (has_exp || has_hedge) || has_exp != has_hedge)
        throw Error("E_INPUT", "give covariance, or exposure_changes with hedge_changes", "covariance");
    const hedging::MinVarResult r = hedging::min_variance(has_cov ? cov : hedging::sample_covariance(exposure, series));
    out.key_reals("hedge", r.hedge);
    out.key_real("variance_before", r.variance_before);
    out.key_real("variance_after", r.variance_after);
    out.key_real("effectiveness", r.effectiveness);
}

hedging::Position position_of(const In& r, bool with_quantity) {
    hedging::Position p;
    p.instrument = r.choice<hedging::Instrument>("instrument", {{"CALL", hedging::Instrument::Call},
                                                                {"PUT", hedging::Instrument::Put},
                                                                {"UNDERLYING", hedging::Instrument::Underlying}});
    if (present(r, "strike")) p.strike = r.real("strike");
    if (present(r, "expiry_years")) p.expiry_years = r.real("expiry_years");
    if (with_quantity) p.quantity = r.real("quantity");
    return p;
}

std::vector<hedging::Position> positions_of(const In& in, string_view key, bool with_quantity) {
    const Value& a = in.need(key);
    if (a.kind != Kind::Array) schema(key, "expected an array");
    std::vector<hedging::Position> out;
    for (const Value& item : a.items) {
        if (item.kind != Kind::Object) schema(key, "expected an object");
        out.push_back(position_of(In(item), with_quantity));
    }
    return out;
}

void write_greeks(Out& out, string_view key, const hedging::Greeks& g) {
    out.values.key(key);
    out.values.begin_object();
    out.key_real("delta", g.delta);
    out.key_real("gamma", g.gamma);
    out.key_real("vega", g.vega);
    out.values.end_object();
}

void op_hedge_greeks_neutralise(const In& in, Out& out) {
    const hedging::Market m{in.real("spot"), in.real("rate"), in.real("dividend_yield"), in.real("volatility")};
    const std::vector<hedging::Position> book = positions_of(in, "portfolio", true);
    const std::vector<hedging::Position> hedges = positions_of(in, "hedges", false);
    const Value& t = in.need("targets");
    if (t.kind != Kind::Array) schema("targets", "expected an array");
    std::vector<hedging::Greek> targets;
    for (const Value& item : t.items)
        targets.push_back(to_enum<hedging::Greek>(
            item, "targets",
            {{"DELTA", hedging::Greek::Delta}, {"GAMMA", hedging::Greek::Gamma}, {"VEGA", hedging::Greek::Vega}}));
    limit_if(book.size() > max_positions, "portfolio");
    limit_if(hedges.size() > max_greek_hedges, "hedges");
    in.ready();
    const hedging::GreekHedge r = hedging::neutralise(m, book, hedges, targets);
    out.key_reals("quantities", r.quantities);
    write_greeks(out, "greeks_before", r.before);
    write_greeks(out, "greeks_after", r.after);
}

void op_hedge_beta_futures(const In& in, Out& out) {
    const double value = in.real("portfolio_value"), beta = in.real("portfolio_beta"),
                 target = in.real("target_beta"), price = in.real("futures_price"), mult = in.real("multiplier");
    hedging::Rounding rounding = hedging::Rounding::Nearest;
    if (present(in, "rounding"))
        rounding = in.choice<hedging::Rounding>(
            "rounding", {{"NEAREST", hedging::Rounding::Nearest}, {"NONE", hedging::Rounding::None}});
    in.ready();
    const hedging::BetaHedge r = hedging::beta_futures(value, beta, target, price, mult, rounding);
    out.key_real("contracts", r.contracts);
    out.key_real("contracts_held", r.contracts_held);
    out.key_real("beta_after", r.beta_after);
}

void op_hedge_residual_report(const In& in, Out& out) {
    const Matrix a = in.matrix("a"), cov = in.matrix("covariance");
    const Vec b = in.reals("b"), x = in.reals("x");
    limit_if(a.size() > max_factors, "a");
    limit_if(cov.size() > max_factors, "covariance");
    limit_if(widest_row(a) > max_instruments, "a");
    in.ready();
    const hedging::ResidualReport r = hedging::residual_report(a, b, x, cov);
    out.key_reals("residual", r.residual);
    out.key_real("variance_before", r.variance_before);
    out.key_real("variance_after", r.variance_after);
    out.key_real("volatility_after", r.volatility_after);
    out.key_real("effectiveness", r.effectiveness);
    out.key_reals("contributions", r.contributions);
}

constexpr Entry hedge_ops[] = {
    {"hedge.solve", op_hedge_solve},
    {"hedge.spread_cost", op_spread_cost},
    {"hedge.qp.solve", op_hedge_qp_solve},
    {"hedge.integer.solve", op_hedge_integer_solve},
    {"hedge.minvar.ratio", op_hedge_minvar_ratio},
    {"hedge.greeks.neutralise", op_hedge_greeks_neutralise},
    {"hedge.beta.futures", op_hedge_beta_futures},
    {"hedge.residual.report", op_hedge_residual_report},
};
