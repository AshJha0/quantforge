// CLI handlers, stage H wave 2: microstructure estimators (H-4b, specifications/09-microstructure/
// micro-estimators.md) and venue analytics (H-16, specifications/10-execution/venue-analytics.md); rulings HR-70 to
// HR-75 as amended (HR-66). Every input is read before In::ready(), so E_SCHEMA and a non-finite input (F-2) come
// before any rule check. Included after ops_micro.inc (uses array_of).

namespace mest = quantforge::micro_est;

enum class CancelOutcome { Cancel, Fill };
constexpr EnumTable<CancelOutcome> cancel_outcomes = {{"CANCEL", CancelOutcome::Cancel}, {"FILL", CancelOutcome::Fill}};
constexpr EnumTable<bool> venue_sides = {{"BUY", true}, {"SELL", false}};

// Each element of the array `k` must be an object; f reads one.
template <class F>
void each_object(const In& in, string_view k, F f) {
    for (const Value& item : array_of(in, k).items) {
        if (item.kind != Kind::Object) schema(k, "expected an array of objects");
        f(In(item));
    }
}

void key_estimate(Out& out, string_view name, const mest::Estimate& e) {
    out.key_real(name, e.value);
    out.key_real("se", e.se);
}

void op_mest_arrival_rate(const In& in, Out& out) {
    const long long count = in.integer("count");
    const double window = in.real("window");
    in.ready();
    key_estimate(out, "lambda", mest::arrival_rate(count, window));
}

void op_mest_cancel_rate(const In& in, Out& out) {
    std::vector<mest::Order> rows;
    each_object(in, "orders", [&](const In& o) {
        const double life = o.real("lifetime");
        rows.push_back({life, o.choice("outcome", cancel_outcomes) == CancelOutcome::Cancel});
    });
    in.ready();
    key_estimate(out, "theta", mest::cancel_rate(rows));
}

std::vector<std::pair<double, double>> pairs_of(const In& in, string_view k, string_view a, string_view b) {
    std::vector<std::pair<double, double>> rows;
    each_object(in, k, [&](const In& p) {
        const double x = p.real(a);
        rows.emplace_back(x, p.real(b));
    });
    return rows;
}

void op_mest_resilience(const In& in, Out& out) {
    const double s_inf = in.real("s_inf");
    const auto points = pairs_of(in, "points", "t", "s");
    in.ready();
    key_estimate(out, "kappa", mest::resilience(s_inf, points));
}

void op_mest_liquidity_decay(const In& in, Out& out) {
    const auto levels = pairs_of(in, "levels", "k", "depth");
    in.ready();
    key_estimate(out, "alpha", mest::liquidity_decay(levels));
}

void op_mest_adverse_selection(const In& in, Out& out) {
    const Vec x = in.reals("x"), y = in.reals("y");
    in.ready();
    key_estimate(out, "lambda_as", mest::adverse_selection(x, y));
}

void op_mest_regime_impact(const In& in, Out& out) {
    const Value& reg = in.need("regimes");
    if (reg.kind != Kind::Object) schema("regimes", "expected an object");
    std::map<string, const Value*, mest::CodePointLess> sorted;
    for (const auto& [label, v] : reg.members) sorted.emplace(label, &v);
    std::map<string, mest::Sample, mest::CodePointLess> rows;
    for (const auto& [label, v] : sorted) {
        if (v->kind != Kind::Object) schema("regimes", "expected an object per label");
        const In r(*v);
        Vec x = r.reals("x");
        rows[label] = {std::move(x), r.reals("y")};
    }
    in.ready();
    const mest::RegimeImpact ri = mest::regime_impact(rows);
    out.values.key("regimes");
    out.values.begin_object();
    for (const auto& [label, e] : ri.regimes) {
        out.values.key(label);
        out.values.begin_object();
        key_estimate(out, "lambda_as", e);
        out.values.end_object();
    }
    out.values.end_object();
    out.key_real("ratio", ri.ratio);
}

void op_mest_passive_vs_aggressive(const In& in, Out& out) {
    const Vec p = in.reals("passive"), a = in.reals("aggressive");
    in.ready();
    key_estimate(out, "delta", mest::passive_vs_aggressive(p, a));
}

void op_exec_venue_analytics(const In& in, Out& out) {
    const auto mids = pairs_of(in, "mids", "t", "mid");
    std::vector<mest::venue::Fill> fills;
    each_object(in, "fills", [&](const In& f) {
        mest::venue::Fill r;
        r.venue = f.text("venue");
        r.buy = f.choice("side", venue_sides);
        r.quantity = f.real("quantity");
        r.price = f.real("price");
        r.t = f.real("t");
        fills.push_back(std::move(r));
    });
    std::vector<mest::venue::Order> orders;
    each_object(in, "orders", [&](const In& o) {
        mest::venue::Order r;
        r.venue = o.text("venue");
        r.sent = o.real("sent");
        r.filled = o.real("filled");
        orders.push_back(std::move(r));
    });
    const Vec horizons = in.reals("horizons");
    in.ready();
    const mest::venue::Result r = mest::venue::analytics(mids, fills, orders, horizons);
    out.values.key("fill_rates");
    out.values.begin_object();
    for (const auto& [v, rate] : r.fill_rates) out.key_real(v, rate);
    out.values.end_object();
    out.values.key("markouts");
    out.values.begin_array();
    for (const auto& m : r.markouts) {
        out.values.begin_object();
        out.key_string("venue", m.venue);
        out.key_real("h", m.h);
        out.key_real("markout", m.markout);
        out.key_real("markout_bps", m.markout_bps);
        out.key_real("toxicity", m.toxicity);
        out.values.end_object();
    }
    out.values.end_array();
}

constexpr Entry micro_est_ops[] = {
    {"exec.venue.analytics", op_exec_venue_analytics},
    {"micro.est.adverse_selection", op_mest_adverse_selection},
    {"micro.est.arrival_rate", op_mest_arrival_rate},
    {"micro.est.cancel_rate", op_mest_cancel_rate},
    {"micro.est.liquidity_decay", op_mest_liquidity_decay},
    {"micro.est.passive_vs_aggressive", op_mest_passive_vs_aggressive},
    {"micro.est.regime_impact", op_mest_regime_impact},
    {"micro.est.resilience", op_mest_resilience},
};
