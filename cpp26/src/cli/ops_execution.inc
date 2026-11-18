// Stage H wave 1 (rulings HR-1 to HR-10): exec.schedule.*, exec.ac.*, exec.impact.*, exec.tca.shortfall,
// micro.mm.as_quotes. Included after ops_research.inc (uses key_integers).

namespace exe = quantforge::execution;

constexpr EnumTable<exe::Mode> exec_modes = {{"UNITS", exe::Mode::Units}, {"CONTINUOUS", exe::Mode::Continuous}};
constexpr EnumTable<exe::Side> exec_sides = {{"BUY", exe::Side::Buy}, {"SELL", exe::Side::Sell}};

// HR-3: UNITS slices are written as JSON integers, CONTINUOUS slices as reals.
void key_slices(Out& out, string_view k, const Vec& s, exe::Mode mode) {
    if (mode == exe::Mode::Continuous) {
        out.key_reals(k, s);
        return;
    }
    std::vector<long long> v(s.size());
    for (std::size_t i = 0; i < s.size(); ++i) v[i] = (long long)s[i];
    key_integers(out, k, v);
}

void key_amount(Out& out, string_view k, double x, exe::Mode mode) {
    if (mode == exe::Mode::Continuous) {
        out.key_real(k, x);
        return;
    }
    out.values.key(k);
    out.values.integer((long long)x);
}

void op_exec_twap(const In& in, Out& out) {
    const double x = in.real("quantity");
    const long long n = in.integer("n_buckets");
    const auto mode = in.find("mode") ? in.choice("mode", exec_modes) : exe::Mode::Continuous;  // HR-56
    limit_if(n > exe::max_steps, "n_buckets");
    in.ready();
    key_slices(out, "slices", exe::twap(x, n, mode), mode);
}

void op_exec_vwap(const In& in, Out& out) {
    const double x = in.real("quantity");
    const Vec w = in.reals("profile");
    const auto mode = in.find("mode") ? in.choice("mode", exec_modes) : exe::Mode::Continuous;  // HR-56
    in.ready();
    key_slices(out, "slices", exe::vwap(x, w, mode), mode);
}

void op_exec_pov(const In& in, Out& out) {
    const double x = in.real("quantity"), p = in.real("participation");
    const Vec v = in.reals("market_volume");
    const auto mode = in.find("mode") ? in.choice("mode", exec_modes) : exe::Mode::Continuous;  // HR-56
    in.ready();
    const exe::Pov r = exe::pov(x, p, v, mode);
    key_slices(out, "slices", r.slices, mode);
    key_amount(out, "filled", r.filled, mode);
    key_amount(out, "residual", r.residual, mode);
}

exe::AcParams read_ac(const In& in) {
    exe::AcParams p{};
    p.quantity = in.real("quantity");
    p.horizon = in.real("horizon");
    p.n_steps = in.integer("n_steps");
    p.sigma = in.real("sigma");
    p.epsilon = in.real("epsilon");
    p.eta = in.real("eta");
    p.gamma = in.real("gamma");
    return p;
}

void op_exec_ac_trajectory(const In& in, Out& out) {
    const exe::AcParams p = read_ac(in);
    const double lambda = in.real("risk_aversion");
    limit_if(p.n_steps > exe::max_steps, "n_steps");
    in.ready();
    const exe::AcTrajectory r = exe::ac_trajectory(p, lambda);
    out.key_reals("holdings", r.holdings);
    out.key_reals("trades", r.trades);
    out.key_real("kappa", r.kappa);
    out.key_real("expected_cost", r.expected_cost);
    out.key_real("variance", r.variance);
    out.key_real("objective", r.objective);
}

void op_exec_ac_frontier(const In& in, Out& out) {
    const exe::AcParams p = read_ac(in);
    const Vec lambdas = in.reals("risk_aversions");
    limit_if(p.n_steps > exe::max_steps, "n_steps");
    in.ready();
    const exe::AcFrontier r = exe::ac_frontier(p, lambdas);
    out.key_reals("risk_aversions", r.risk_aversions);
    out.key_reals("expected_costs", r.expected_cost);
    out.key_reals("variances", r.variance);
}

void op_exec_impact_sqrt(const In& in, Out& out) {
    const double q = in.real("quantity"), v = in.real("daily_volume"), s = in.real("daily_vol");
    const double y = in.real("coefficient", 1.0);
    in.ready();
    out.key_real("impact", exe::impact_sqrt(q, v, s, y));
    out.key_string("model", exe::assumed);
}

void op_exec_impact_ow_optimal(const In& in, Out& out) {
    const double x = in.real("quantity"), t = in.real("horizon"), rho = in.real("resilience");
    in.ready();
    const exe::OwOptimal r = exe::ow_optimal(x, t, rho);
    out.key_real("initial_block", r.initial_block);
    out.key_real("rate", r.rate);
    out.key_real("final_block", r.final_block);
}

void op_exec_tca_shortfall(const In& in, Out& out) {
    const auto side = in.choice("side", exec_sides);
    const double pd = in.real("decision_price"), p0 = in.real("arrival_price"), pc = in.real("end_price");
    const double x = in.real("order_quantity");
    const Value& fv = in.need("fills");
    if (fv.kind != Kind::Array) schema("fills", "expected an array of objects");
    std::vector<exe::Fill> fills;
    fills.reserve(fv.items.size());
    for (const Value& f : fv.items) {
        if (f.kind != Kind::Object) schema("fills", "expected an array of objects");
        const In fi(f);
        fills.push_back({fi.real("quantity"), fi.real("price")});
    }
    const double fees = in.real("fees");
    std::optional<double> bench;
    if (in.find("benchmark_vwap")) bench = in.real("benchmark_vwap");
    limit_if(fills.size() > exe::max_fills, "fills");  // HR-9
    in.ready();
    const exe::Shortfall r = exe::shortfall(side, pd, p0, pc, x, fills, fees, bench);
    out.key_real("delay", r.delay);
    out.key_real("execution", r.execution);
    out.key_real("opportunity", r.opportunity);
    out.key_real("total", r.total);
    out.key_real("total_bps", r.total_bps);
    if (r.vwap_slippage) out.key_real("vwap_slippage", *r.vwap_slippage);
}

void op_micro_mm_as_quotes(const In& in, Out& out) {
    const double s = in.real("mid"), q = in.real("inventory"), g = in.real("risk_aversion");
    const double sigma = in.real("sigma"), tl = in.real("time_left"), k = in.real("k");
    in.ready();
    const exe::Quotes r = exe::as_quotes(s, q, g, sigma, tl, k);
    out.key_real("reservation", r.reservation);
    out.key_real("spread", r.spread);
    out.key_real("bid", r.bid);
    out.key_real("ask", r.ask);
}

void op_usecase_execution_tca(const In& in, Out& out) {
    const exe::AcParams p = read_ac(in);
    const double lambda = in.real("risk_aversion");
    const auto side = in.choice("side", exec_sides);
    const double pd = in.real("decision_price"), p0 = in.real("arrival_price"), pc = in.real("end_price");
    const Vec fp = in.reals("fill_prices");
    const long long done = in.integer("completed_steps");
    const double fee = in.real("fee_per_unit");
    limit_if(p.n_steps > exe::max_steps, "n_steps");
    in.ready();
    const exe::ExecutionTca r = exe::execution_tca(p, lambda, side, pd, p0, pc, fp, done, fee);
    key_slices(out, "lots", r.lots, exe::Mode::Units);
    out.key_real("expected_cost", r.expected_cost);
    out.key_real("variance", r.variance);
    key_amount(out, "filled", r.filled, exe::Mode::Units);
    out.key_real("fees", r.fees);
    out.key_real("delay", r.shortfall.delay);
    out.key_real("execution", r.shortfall.execution);
    out.key_real("opportunity", r.shortfall.opportunity);
    out.key_real("total", r.shortfall.total);
    out.key_real("total_bps", r.shortfall.total_bps);
}

// ---- Stage H wave 2 execution (HR-59 to HR-67): adaptive-algos.md and tca-pretrade.md ----

constexpr EnumTable<exe::PairMode> exec_pair_modes = {{"CASH_BALANCED", exe::PairMode::CashBalanced},
                                                      {"HEDGED", exe::PairMode::Hedged}};

exe::Mode exec_mode(const In& in) { return in.find("mode") ? in.choice("mode", exec_modes) : exe::Mode::Continuous; }

const Value& exec_object(const In& in, string_view k) {
    const Value& v = in.need(k);
    if (v.kind != Kind::Object) schema(k, "expected an object");
    return v;
}

void op_exec_algo_arrival(const In& in, Out& out) {
    const double x = in.real("quantity");
    const long long n = in.integer("n_buckets");
    const double k = in.real("urgency");
    const auto mode = exec_mode(in);
    limit_if(n > exe::max_steps, "n_buckets");
    in.ready();
    key_slices(out, "slices", exe::algo_arrival(x, n, k, mode), mode);
}

void op_exec_algo_close(const In& in, Out& out) {
    const double x = in.real("quantity"), v = in.real("close_volume"), p = in.real("auction_participation");
    const Vec w = in.reals("profile");
    const auto mode = exec_mode(in);
    in.ready();
    const exe::Close r = exe::algo_close(x, v, p, w, mode);
    key_amount(out, "auction_quantity", r.auction_quantity, mode);
    key_slices(out, "slices", r.slices, mode);
}

void op_exec_algo_liquidity_seek(const In& in, Out& out) {
    const auto side = in.choice("side", exec_sides);
    const double x = in.real("quantity"), lim = in.real("limit_price"), a = in.real("take_fraction");
    const Value& bv = in.need("books");
    if (bv.kind != Kind::Array) schema("books", "expected an array of buckets");
    std::vector<exe::Book> books;
    books.reserve(bv.items.size());
    for (const Value& b : bv.items) {
        if (b.kind != Kind::Array) schema("books", "each bucket must be an array of levels");
        exe::Book book;
        book.reserve(b.items.size());
        for (const Value& l : b.items) {
            if (l.kind != Kind::Array || l.items.size() != 2) schema("books", "each level must be [price, size]");
            book.push_back({to_real(l.items[0], "books"), to_real(l.items[1], "books")});
        }
        books.push_back(std::move(book));
    }
    in.ready();
    const exe::Seek r = exe::algo_liquidity_seek(side, x, lim, a, books);
    out.key_reals("slices", r.slices);
    out.key_maybes("avg_prices", r.avg_prices);
    out.key_real("filled", r.filled);
    out.key_real("residual", r.residual);
    out.key_real("notional", r.notional);
    out.key_maybe("avg_fill_price", r.avg_fill_price);
}

void op_exec_algo_pair(const In& in, Out& out) {
    const In a(exec_object(in, "leg_a"));
    const auto sa = a.choice("side", exec_sides);
    const double qa = a.real("quantity"), pa = a.real("price");
    const In b(exec_object(in, "leg_b"));
    const auto sb = b.choice("side", exec_sides);
    const double pb = b.real("price");
    const auto pm = in.choice("pair_mode", exec_pair_modes);
    std::optional<double> h;
    if (in.find("hedge_ratio")) h = in.real("hedge_ratio");
    const long long n = in.integer("n_buckets");
    const auto mode = exec_mode(in);
    limit_if(n > exe::max_steps, "n_buckets");
    in.ready();
    const exe::Pair r = exe::algo_pair(sa, qa, pa, sb, pb, pm, h, n, mode);
    key_slices(out, "slices_a", r.slices_a, mode);
    key_slices(out, "slices_b", r.slices_b, mode);
    key_amount(out, "quantity_b", r.quantity_b, mode);
    out.key_reals("cash_imbalance", r.cash_imbalance);
}

void op_exec_algo_basket(const In& in, Out& out) {
    const Value& lv = in.need("legs");
    if (lv.kind != Kind::Array) schema("legs", "expected an array of objects");
    std::vector<exe::Leg> legs;
    legs.reserve(lv.items.size());
    for (const Value& g : lv.items) {
        if (g.kind != Kind::Object) schema("legs", "expected an array of objects");
        const In gi(g);
        legs.push_back({gi.choice("side", exec_sides), gi.real("quantity"), gi.real("price")});
    }
    const long long n = in.integer("n_buckets");
    const auto mode = exec_mode(in);
    limit_if(n > exe::max_steps, "n_buckets");
    in.ready();
    const exe::Basket r = exe::algo_basket(legs, n, mode);
    out.values.key("slices");
    out.values.begin_array();
    for (const Vec& s : r.slices) {
        out.values.begin_array();
        for (const double v : s) {
            if (mode == exe::Mode::Continuous) out.values.real(v);
            else out.values.integer((long long)v);  // HR-3
        }
        out.values.end_array();
    }
    out.values.end_array();
    out.key_reals("cash_imbalance", r.cash_imbalance);
    out.key_real("gross_notional", r.gross_notional);
}

void op_exec_tca_pretrade(const In& in, Out& out) {
    const double x = in.real("quantity"), adv = in.real("adv"), sigma = in.real("daily_vol");
    const double p = in.real("participation"), hs = in.real("half_spread_bps");
    const In k(exec_object(in, "params"));
    const exe::PretradeParams params{k.real("a1"), k.real("a2"), k.real("a3"), k.real("a4"), k.real("b1")};
    std::optional<double> price;
    if (in.find("price")) price = in.real("price");
    in.ready();
    const exe::Pretrade r = exe::tca_pretrade(x, adv, sigma, p, hs, params, price);
    out.key_real("istar_bps", r.istar_bps);
    out.key_real("impact_bps", r.impact_bps);
    out.key_real("spread_bps", r.spread_bps);
    out.key_real("expected_cost_bps", r.expected_cost_bps);
    out.key_real("duration_days", r.duration_days);
    out.key_real("timing_risk_bps", r.timing_risk_bps);
    if (r.expected_cost) out.key_real("expected_cost", *r.expected_cost);
    if (r.timing_risk) out.key_real("timing_risk", *r.timing_risk);
}

void op_exec_tca_attribution(const In& in, Out& out) {
    const auto side = in.choice("side", exec_sides);
    const double pd = in.real("decision_price"), m0 = in.real("arrival_mid"), pc = in.real("end_price");
    const double x = in.real("order_quantity");
    const Value& fv = in.need("fills");
    if (fv.kind != Kind::Array) schema("fills", "expected an array of objects");
    std::vector<exe::AttrFill> fills;
    fills.reserve(fv.items.size());
    for (const Value& f : fv.items) {
        if (f.kind != Kind::Object) schema("fills", "expected an array of objects");
        const In fi(f);
        fills.push_back({fi.real("quantity"), fi.real("price"), fi.real("mid")});
    }
    const double fees = in.real("fees", 0.0);
    limit_if(fills.size() > exe::max_fills, "fills");  // HR-9
    in.ready();
    const exe::Attribution r = exe::tca_attribution(side, pd, m0, pc, x, fills, fees);
    out.key_real("delay", r.delay);
    out.key_real("impact", r.impact);
    out.key_real("spread", r.spread);
    out.key_real("execution", r.execution);
    out.key_real("opportunity", r.opportunity);
    out.key_real("fees", r.fees);
    out.key_real("total", r.total);
    out.key_real("total_bps", r.total_bps);
}

constexpr Entry execution_ops[] = {
    {"exec.algo.arrival", op_exec_algo_arrival},
    {"exec.algo.basket", op_exec_algo_basket},
    {"exec.algo.close", op_exec_algo_close},
    {"exec.algo.liquidity_seek", op_exec_algo_liquidity_seek},
    {"exec.algo.pair", op_exec_algo_pair},
    {"exec.schedule.twap", op_exec_twap},
    {"exec.schedule.vwap", op_exec_vwap},
    {"exec.schedule.pov", op_exec_pov},
    {"exec.ac.trajectory", op_exec_ac_trajectory},
    {"exec.ac.frontier", op_exec_ac_frontier},
    {"exec.impact.sqrt", op_exec_impact_sqrt},
    {"exec.impact.ow_optimal", op_exec_impact_ow_optimal},
    {"exec.tca.attribution", op_exec_tca_attribution},
    {"exec.tca.pretrade", op_exec_tca_pretrade},
    {"exec.tca.shortfall", op_exec_tca_shortfall},
    {"micro.mm.as_quotes", op_micro_mm_as_quotes},
    {"usecase.execution_tca", op_usecase_execution_tca},
};
