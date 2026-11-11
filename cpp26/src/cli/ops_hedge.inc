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

// The inputs of hedge.qp.solve other than cost_weight, shared with hedge.frontier.solve. Limits are checked here.
hedging::QpProblem qp_problem_of(const In& in) {
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
    if (present(in, "half_spreads")) p.half_spreads = in.reals("half_spreads");
    if (present(in, "impact")) p.impact = in.reals("impact");
    if (present(in, "margin_rates")) p.margin_rates = in.reals("margin_rates");
    if (present(in, "margin_limit")) p.margin_limit = in.real("margin_limit");
    limit_if(p.a.size() > max_factors, "a");
    limit_if(widest_row(p.a) > max_instruments, "a");
    limit_if(p.eq_matrix && p.eq_matrix->size() > max_equalities, "eq_matrix");
    return p;
}

void op_hedge_qp_solve(const In& in, Out& out) {
    hedging::QpProblem p = qp_problem_of(in);
    if (present(in, "cost_weight")) p.cost_weight = in.real("cost_weight");
    in.ready();
    const hedging::QpResult r = hedging::solve_qp(p);
    write_ls(out, r.x, r.residual, r.objective);
    key_int(out, "rank", r.rank);
    if (r.costed) {  // I-27
        out.key_real("risk", r.risk);
        out.key_real("cost", r.cost);
    }
    if (r.margined) out.key_real("margin", r.margin);
}

// Wave 4a: risk against cost, one solve per weight in order; the first error stops it.
void op_hedge_frontier_solve(const In& in, Out& out) {
    hedging::QpProblem p = qp_problem_of(in);
    const bool has_single = present(in, "cost_weight");
    if (has_single) (void)in.real("cost_weight");
    const Vec weights = in.reals("cost_weights");
    limit_if(weights.size() > 50, "cost_weights");
    in.ready();
    if (has_single) throw Error("E_INPUT", "cost_weight goes with hedge.qp.solve, not the frontier", "cost_weight");
    if (weights.empty()) throw Error("E_INPUT", "cost_weights is empty", "cost_weights");
    for (std::size_t i = 1; i < weights.size(); ++i)
        if (!(weights[i] > weights[i - 1])) throw Error("E_INPUT", "cost_weights must increase strictly", "cost_weights");
    if (!p.half_spreads && !p.impact) throw Error("E_INPUT", "a frontier needs half_spreads or impact", "half_spreads");
    std::vector<hedging::QpResult> points;
    for (const double w : weights) {
        p.cost_weight = w;
        points.push_back(hedging::solve_qp(p));
    }
    out.values.key("points");
    out.values.begin_array();
    for (std::size_t i = 0; i < points.size(); ++i) {
        out.values.begin_object();
        out.key_real("cost_weight", weights[i]);
        out.key_reals("x", points[i].x);
        out.key_real("risk", points[i].risk);
        out.key_real("cost", points[i].cost);
        out.values.end_object();
    }
    out.values.end_array();
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

// A Greek-hedge instrument. Fixed key sets (I-41): instrument, quantity on the portfolio only, strike and
// expiry_years; any other key, or a missing quantity, is E_INPUT, raised by the caller after the finite rule.
// A missing or extra strike or expiry is the library's check 1, also E_INPUT.
hedging::Position position_of(const In& r, bool with_quantity, bool& keys_ok) {
    hedging::Position p;
    p.instrument = r.choice<hedging::Instrument>("instrument", {{"CALL", hedging::Instrument::Call},
                                                                {"PUT", hedging::Instrument::Put},
                                                                {"UNDERLYING", hedging::Instrument::Underlying}});
    for (const auto& [key, value] : r.raw().members)
        if (key != "instrument" && key != "strike" && key != "expiry_years" && !(with_quantity && key == "quantity"))
            keys_ok = false;
    if (present(r, "strike")) p.strike = r.real("strike");
    if (present(r, "expiry_years")) p.expiry_years = r.real("expiry_years");
    if (with_quantity) {
        if (present(r, "quantity")) p.quantity = r.real("quantity");
        else keys_ok = false;
    }
    return p;
}

std::vector<hedging::Position> positions_of(const In& in, string_view key, bool with_quantity, bool& keys_ok) {
    const Value& a = in.need(key);
    if (a.kind != Kind::Array) schema(key, "expected an array");
    std::vector<hedging::Position> out;
    for (const Value& item : a.items) {
        if (item.kind != Kind::Object) schema(key, "expected an object");
        out.push_back(position_of(In(item), with_quantity, keys_ok));
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
    bool book_keys = true, hedge_keys = true;
    const std::vector<hedging::Position> book = positions_of(in, "portfolio", true, book_keys);
    const std::vector<hedging::Position> hedges = positions_of(in, "hedges", false, hedge_keys);
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
    if (!book_keys) throw Error("E_INPUT", "portfolio: keys other than those of the instrument (I-41)", "portfolio");
    if (!hedge_keys) throw Error("E_INPUT", "hedges: keys other than those of the instrument (I-41)", "hedges");
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

// ---- stage I wave 2: credit and correlation hedges (08-hedging/credit-and-correlation-hedges.md) ----

constexpr std::size_t max_credit_book = 1000, max_credit_hedges = 50, max_correlation_book = 1000,
                      max_correlation_hedges = 5;  // ruling I-19

hedging::CdsContract cds_contract_of(const In& r, bool trade) {
    hedging::CdsContract c;
    c.maturity = r.date("maturity");
    c.coupon = r.real("coupon");
    if (trade) {
        c.notional = r.real("notional");
        c.buy = r.choice<bool>("side", {{"BUY_PROTECTION", true}, {"SELL_PROTECTION", false}});
    }
    return c;
}

void write_credit_risk(Out& out, string_view key, const hedging::CreditRisk& r, bool with_pv) {
    out.values.key(key);
    out.values.begin_object();
    if (with_pv) out.key_real("pv", r.pv);
    out.key_real("cs01", r.cs01);
    out.key_real("jtd", r.jtd);
    out.key_reals("buckets", r.buckets);
    out.values.end_object();
}

void op_hedge_credit_cds(const In& in, Out& out) {
    const Date t = in.date("trade_date");
    const CurveInput d = curve_of(in, "discount");
    const HazardCurve h = hazard_of(in.need("hazard"), "hazard");
    const double recovery = in.real("recovery");
    const auto book = rows_of<hedging::CdsContract>(in, "book", [](const In& r) { return cds_contract_of(r, true); });
    const auto hedges =
        rows_of<hedging::CdsContract>(in, "hedges", [](const In& r) { return cds_contract_of(r, false); });
    const Value& tv = in.need("targets");
    if (tv.kind != Kind::Array) schema("targets", "expected an array");
    std::vector<string> targets;
    for (const Value& item : tv.items) targets.push_back(to_string(item, "targets"));
    limit_if(book.size() > max_credit_book, "book");
    limit_if(hedges.size() > max_credit_hedges, "hedges");
    in.ready();
    d.limit();
    limit_if(h.dates.size() > max_quotes, "hazard");
    require_flat_forwards(d);  // check 1 (R1-4)
    const hedging::CreditHedge r = hedging::credit_hedge(t, d.build(), h, recovery, book, hedges, targets);
    out.key_reals("notionals", r.notionals);
    write_credit_risk(out, "book", r.book, true);
    write_credit_risk(out, "after", r.after, false);
    out.key_real("hedge_upfront", r.hedge_upfront);
}

// One two-asset position. Its keys are recorded so that a key set other than its kind's is E_INPUT (check 1),
// raised by the caller after E_LIMIT and the finite rule.
struct KeyedPosition {
    hedging::TwoAssetPosition p;
    bool keys_ok = true;
};

KeyedPosition two_asset_position_of(const In& r, bool with_quantity) {
    using K = hedging::TwoAssetKind;
    KeyedPosition k;
    k.p.kind = r.choice<K>("instrument", {{"EXCHANGE", K::Exchange},
                                          {"CALL_1", K::Call1},
                                          {"PUT_1", K::Put1},
                                          {"CALL_2", K::Call2},
                                          {"PUT_2", K::Put2},
                                          {"UNDERLYING_1", K::Underlying1},
                                          {"UNDERLYING_2", K::Underlying2}});
    std::vector<string_view> wanted{"instrument"};
    if (with_quantity) wanted.push_back("quantity");
    if (k.p.kind == K::Exchange) wanted.insert(wanted.end(), {"quantity1", "quantity2", "expiry_years"});
    else if (k.p.kind != K::Underlying1 && k.p.kind != K::Underlying2) wanted.insert(wanted.end(), {"strike", "expiry_years"});
    for (const auto& [key, value] : r.raw().members)
        if (std::ranges::find(wanted, string_view(key)) == wanted.end()) k.keys_ok = false;
    const auto read = [&](string_view key, double& into) {
        if (r.raw().find(key)) into = to_real(*r.raw().find(key), key);
        else k.keys_ok = false;
    };
    for (const string_view key : wanted) {
        if (key == "instrument") continue;
        double* slot = key == "quantity"    ? &k.p.quantity
                       : key == "quantity1" ? &k.p.quantity1
                       : key == "quantity2" ? &k.p.quantity2
                       : key == "strike"    ? &k.p.strike
                                            : &k.p.expiry_years;
        read(key, *slot);
    }
    return k;
}

std::vector<KeyedPosition> two_asset_positions_of(const In& in, string_view key, bool with_quantity) {
    const Value& a = in.need(key);
    if (a.kind != Kind::Array) schema(key, "expected an array");
    std::vector<KeyedPosition> out;
    for (const Value& item : a.items) {
        if (item.kind != Kind::Object) schema(key, "expected an object");
        out.push_back(two_asset_position_of(In(item), with_quantity));
    }
    return out;
}

void op_hedge_correlation_neutralise(const In& in, Out& out) {
    using T = hedging::TwoAssetTarget;
    const hedging::TwoAssetMarket m{in.real("spot1"),  in.real("spot2"), in.real("rate"),
                                    in.real("yield1"), in.real("yield2"), in.real("vol1"),
                                    in.real("vol2"),   in.real("correlation")};
    const auto book = two_asset_positions_of(in, "book", true);
    const auto hedges = two_asset_positions_of(in, "hedges", false);
    const Value& tv = in.need("targets");
    if (tv.kind != Kind::Array) schema("targets", "expected an array");
    std::vector<T> targets;
    for (const Value& item : tv.items)
        targets.push_back(to_enum<T>(item, "targets",
                                     {{"DELTA_1", T::Delta1},
                                      {"DELTA_2", T::Delta2},
                                      {"VEGA_1", T::Vega1},
                                      {"VEGA_2", T::Vega2},
                                      {"CORRELATION", T::Correlation}}));
    limit_if(book.size() > max_correlation_book, "book");
    limit_if(hedges.size() > max_correlation_hedges, "hedges");
    in.ready();
    std::vector<hedging::TwoAssetPosition> b, h;
    for (const KeyedPosition& k : book) {
        if (!k.keys_ok) throw Error("E_INPUT", "book: keys other than those of the instrument kind", "book");
        b.push_back(k.p);
    }
    for (const KeyedPosition& k : hedges) {
        if (!k.keys_ok) throw Error("E_INPUT", "hedges: keys other than those of the instrument kind", "hedges");
        h.push_back(k.p);
    }
    const hedging::CorrelationHedge r = hedging::correlation_hedge(m, b, h, targets);
    out.key_reals("quantities", r.quantities);
    const auto write = [&](string_view key, const hedging::TwoAssetGreeks& g) {
        out.values.key(key);
        out.values.begin_object();
        out.key_real("delta_1", g[0]);
        out.key_real("delta_2", g[1]);
        out.key_real("vega_1", g[2]);
        out.key_real("vega_2", g[3]);
        out.key_real("correlation01", g[4]);
        out.values.end_object();
    };
    write("greeks_before", r.before);
    write("greeks_after", r.after);
}

// ---- stage I wave 3: cross-asset hedge (08-hedging/cross-asset-hedge.md) ----

constexpr std::size_t max_cross_asset_book = 1000, max_cross_asset_hedges = 200, max_curve_pillars = 100;  // I-23

struct KeyedCrossAsset {
    hedging::CrossAssetPosition p;
    bool keys_ok = true;
};

KeyedCrossAsset cross_asset_position_of(const In& r, bool with_quantity) {
    using K = hedging::CrossAssetKind;
    KeyedCrossAsset k;
    k.p.kind = r.choice<K>("instrument", {{"CALL", K::Call},
                                          {"PUT", K::Put},
                                          {"FORWARD", K::Forward},
                                          {"ZCB", K::Zcb},
                                          {"UNDERLYING", K::Underlying}});
    std::vector<std::pair<string_view, double*>> wanted;
    if (with_quantity) wanted.emplace_back("quantity", &k.p.quantity);
    if (k.p.kind == K::Call || k.p.kind == K::Put || k.p.kind == K::Forward)
        wanted.insert(wanted.end(), {{"strike", &k.p.strike}, {"expiry_years", &k.p.expiry_years}});
    if (k.p.kind == K::Zcb) wanted.insert(wanted.end(), {{"expiry_years", &k.p.expiry_years}, {"notional", &k.p.notional}});
    for (const auto& [key, value] : r.raw().members)
        if (key != "instrument" && std::ranges::none_of(wanted, [&](const auto& w) { return w.first == key; }))
            k.keys_ok = false;
    for (const auto& [key, slot] : wanted) {
        if (const Value* v = r.raw().find(key)) *slot = to_real(*v, key);
        else k.keys_ok = false;
    }
    return k;
}

std::vector<KeyedCrossAsset> cross_asset_positions_of(const In& in, string_view key, bool with_quantity) {
    const Value& a = in.need(key);
    if (a.kind != Kind::Array) schema(key, "expected an array");
    std::vector<KeyedCrossAsset> out;
    for (const Value& item : a.items) {
        if (item.kind != Kind::Object) schema(key, "expected an object");
        out.push_back(cross_asset_position_of(In(item), with_quantity));
    }
    return out;
}

void op_hedge_crossasset_solve(const In& in, Out& out) {
    const double spot = in.real("spot"), q = in.real("dividend_yield"), vol = in.real("volatility");
    const Value& cv = in.need("curve");
    if (cv.kind != Kind::Object) schema("curve", "expected an object");
    const In cin(cv);
    const hedging::ZeroCurve curve{cin.reals("times"), cin.reals("zero_rates")};
    const auto book = cross_asset_positions_of(in, "book", true);
    const auto hedges = cross_asset_positions_of(in, "hedges", false);
    const Vec weights = in.reals("weights");
    const double ridge = optional_real(in, "ridge", 0.0);
    limit_if(book.size() > max_cross_asset_book, "book");
    limit_if(hedges.size() > max_cross_asset_hedges, "hedges");
    limit_if(curve.times.size() > max_curve_pillars, "curve");
    in.ready();
    hedging::check_zero_curve(curve);  // check 1, before the key sets of check 2
    std::vector<hedging::CrossAssetPosition> b, h;
    for (const KeyedCrossAsset& k : book) {
        if (!k.keys_ok) throw Error("E_INPUT", "book: keys other than those of the instrument kind", "book");
        b.push_back(k.p);
    }
    for (const KeyedCrossAsset& k : hedges) {
        if (!k.keys_ok) throw Error("E_INPUT", "hedges: keys other than those of the instrument kind", "hedges");
        h.push_back(k.p);
    }
    const hedging::CrossAssetHedge r = hedging::cross_asset_hedge(spot, q, vol, curve, b, h, weights, ridge);
    out.key_reals("positions", r.positions);
    out.key_reals("book_risk", r.book_risk);
    out.key_reals("residual_risk", r.residual_risk);
    out.key_real("objective", r.objective);
}

// ---- stage I wave 4b: backtest and effectiveness (08-hedging/dynamic-hedge-and-effectiveness.md) ----

constexpr std::size_t max_path = 100000;  // ruling I-32

void write_effectiveness(Out& out, const hedging::Effectiveness& e) {
    out.key_real("dollar_offset", e.dollar_offset);
    out.key_real("regression_slope", e.regression_slope);
    out.key_real("regression_r2", e.regression_r2);
    out.key_real("variance_reduction", e.variance_reduction);
}

void op_hedge_effectiveness(const In& in, Out& out) {
    const Vec x = in.reals("item_changes"), y = in.reals("hedge_changes");
    limit_if(x.size() > max_path, "item_changes");
    limit_if(y.size() > max_path, "hedge_changes");
    in.ready();
    write_effectiveness(out, hedging::effectiveness(x, y));
}

void op_hedge_backtest_delta(const In& in, Out& out) {
    const Value& ov = in.need("option");
    if (ov.kind != Kind::Object) schema("option", "expected an object");
    const In o(ov);
    const hedging::BacktestOption option{o.choice<bool>("type", {{"CALL", true}, {"PUT", false}}), o.real("strike"),
                                         o.real("expiry_years")};
    const double quantity = in.real("quantity"), rate = in.real("rate"), q = in.real("dividend_yield"),
                 vol = in.real("hedge_volatility");
    const Vec times = in.reals("times"), spots = in.reals("spots");
    hedging::BacktestCosts costs;
    if (present(in, "half_spread")) costs.half_spread = in.real("half_spread");
    if (present(in, "impact")) costs.impact = in.real("impact");
    limit_if(times.size() > max_path, "times");
    limit_if(spots.size() > max_path, "spots");
    in.ready();
    const hedging::DeltaBacktest r = hedging::backtest_delta(option, quantity, rate, q, vol, times, spots, costs);
    out.key_reals("option_values", r.option_values);
    out.key_reals("shares", r.shares);
    out.key_reals("portfolio_values", r.portfolio_values);
    out.key_real("final_pnl", r.final_pnl);
    write_effectiveness(out, r.stats);
    if (r.costed) out.key_real("trading_cost", r.trading_cost);  // I-40
}

// ---- stage I wave 4c: instrument selection (08-hedging/instrument-selection.md) ----

void op_hedge_select_solve(const In& in, Out& out) {
    hedging::QpProblem p;
    p.a = in.matrix("a");
    p.b = in.reals("b");
    p.weights = in.reals("weights");
    p.ridge = optional_real(in, "ridge", 0.0);
    p.lower = bounds_of(in, "lower");
    p.upper = bounds_of(in, "upper");
    const long long k = in.integer("max_instruments");
    const bool forbidden = present(in, "eq_matrix") || present(in, "eq_rhs") || present(in, "singular");  // I-47
    limit_if(p.a.size() > max_factors, "a");
    limit_if(widest_row(p.a) > 20, "a");  // ruling I-35
    in.ready();
    const hedging::SelectResult r = hedging::select_instruments(p, k, forbidden);
    out.values.key("selected");
    out.values.begin_array();
    for (const long long i : r.selected) out.values.integer(i);
    out.values.end_array();
    write_ls(out, r.x, r.residual, r.objective);
}

// ---- stage I wave 4d: slippage (08-hedging/hedge-slippage.md) ----

void op_hedge_slippage_report(const In& in, Out& out) {
    const auto orders = rows_of<hedging::Order>(in, "orders", [](const In& r) {
        hedging::Order o{r.real("quantity"), r.real("decision_price"), r.real("final_price"), r.real("half_spread"),
                         r.real("impact"), {}};
        o.fills = rows_of<hedging::Fill>(r, "fills", [](const In& f) { return hedging::Fill{f.real("quantity"), f.real("price")}; });
        return o;
    });
    std::size_t fills = 0;
    for (const hedging::Order& o : orders) fills += o.fills.size();
    limit_if(orders.size() > 10000, "orders");  // ruling I-38
    limit_if(fills > 1000000, "fills");
    in.ready();
    const hedging::SlippageReport r = hedging::slippage_report(orders);
    const auto costs = [&](const hedging::Slippage& s) {
        out.key_real("execution_cost", s.execution_cost);
        out.key_real("opportunity_cost", s.opportunity_cost);
        out.key_real("shortfall", s.shortfall);
        out.key_real("model_cost", s.model_cost);
        out.key_real("slippage", s.slippage);
    };
    out.values.key("orders");
    out.values.begin_array();
    for (const hedging::Slippage& s : r.orders) {
        out.values.begin_object();
        out.key_real("filled_quantity", s.filled_quantity);
        out.key_maybe("average_price", s.average_price);
        costs(s);
        out.values.end_object();
    }
    out.values.end_array();
    out.values.key("total");
    out.values.begin_object();
    costs(r.total);
    out.values.end_object();
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
    {"hedge.credit.cds", op_hedge_credit_cds},
    {"hedge.correlation.neutralise", op_hedge_correlation_neutralise},
    {"hedge.crossasset.solve", op_hedge_crossasset_solve},
    {"hedge.frontier.solve", op_hedge_frontier_solve},
    {"hedge.backtest.delta", op_hedge_backtest_delta},
    {"hedge.effectiveness", op_hedge_effectiveness},
    {"hedge.select.solve", op_hedge_select_solve},
    {"hedge.slippage.report", op_hedge_slippage_report},
};
