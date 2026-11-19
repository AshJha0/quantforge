// CLI handlers, stage K wave 1 (PROPOSED rulings KR-1 to KR-14, specifications/stage-k-rulings-w1.md; contract
// table "Stage K wave 1 operations" in specifications/cli-contract.md). Error order HR-66: every input is read
// first (E_SCHEMA), then the structural E_INPUT checks run here, before In::ready() raises a non-finite input
// (F-2) as E_DOMAIN; the library then raises E_DOMAIN, the value-dependent E_INPUT and the stage K sizes
// (E_LIMIT), last. These verbs skip the general array limit (run_case), as the Python build skips its generic
// sizes for them (limits.STAGE_K_OPS).

namespace sk = quantforge::stage_k;

const json::Value& array_named(const In& in, string_view k) {
    const Value& a = in.need(k);
    if (a.kind != Kind::Array) schema(k, "expected an array");
    return a;
}

// One bitemporal record: `value` (any JSON value) and `valid_to` (an instant or null) must both be present.
sk::BiRecord bi_record_of(const Value& v) {
    if (v.kind != Kind::Object) schema("records", "a record is not an object");
    if (!v.find("value") || !v.find("valid_to")) schema("records", "a record has no value or no valid_to");
    const In r(v);
    const long long sequence = r.integer("sequence");
    const string& series = r.text("series_id");
    if (sequence < 1 || series.empty()) schema("records", "bad sequence or series_id in a record");
    const Instant valid_from = r.instant("valid_from");
    const std::optional<Instant> valid_to = maybe_instant(r, "valid_to");
    const Instant knowledge_time = r.instant("knowledge_time");
    // Ruling F-38: an F-1 token at the top level of the value is a Real, which F-2 refuses; nested, a string.
    if (const Value& value = *v.find("value"); value.kind == Kind::String &&
        (value.text == "NaN" || value.text == "Infinity" || value.text == "-Infinity"))
        to_real(value, "records.value");
    return {sequence, series, valid_from, valid_to, knowledge_time, r.boolean("deleted", false)};
}

void op_bitemporal_query(const In& in, Out& out) {
    const Value& raw = array_named(in, "records");
    std::vector<sk::BiRecord> log;
    log.reserve(raw.items.size());
    for (const Value& v : raw.items) log.push_back(bi_record_of(v));
    const string& series = in.text("series_id");
    const Instant k = in.instant("knowledge_as_of"), at = in.instant("valid_at");
    sk::check_log(log);
    in.ready();
    const sk::BiAnswer a = sk::bitemporal_query(log, series, k, at);
    out.key_string("status", sk::status_name(a.status));
    out.values.key("row");
    if (!a.winner) {
        out.values.null();
        return;
    }
    const sk::BiRecord& w = log[*a.winner];
    out.values.begin_object();
    out.values.key("sequence");
    out.values.integer(w.sequence);
    out.key_string("valid_from", format_instant(w.valid_from));
    out.values.key("valid_to");
    if (w.valid_to) out.values.string(format_instant(*w.valid_to));
    else out.values.null();
    out.key_string("knowledge_time", format_instant(w.knowledge_time));
    out.values.key("value");
    out.values.value(*raw.items[*a.winner].find("value"));
    out.values.end_object();
}

void op_par_annual(const In& in, Out& out) {
    const Vec quotes = in.reals("quotes");
    sk::check_quotes_shape(quotes.size());
    in.ready();
    out.key_reals("discount_factors", sk::par_annual(quotes));
}

void op_incremental_update(const In& in, Out& out) {
    const Vec pq = in.reals("previous_quotes"), pd = in.reals("previous_discount_factors");
    const Vec nq = in.reals("new_quotes");
    sk::check_update_shape(pq.size(), pd.size(), nq.size());
    in.ready();
    const sk::Update u = sk::incremental_update(pq, pd, nq);
    out.key_reals("discount_factors", u.discount_factors);
    out.values.key("first_changed_index");
    if (u.first_changed_index) out.values.integer(static_cast<long long>(*u.first_changed_index));
    else out.values.null();
    out.values.key("recomputed");
    out.values.integer(static_cast<long long>(u.recomputed));
}

void op_trigger_check(const In& in, Out& out) {
    const Vec changes = in.reals("changes");
    const double x_ref = in.real("x_ref"), x_now = in.real("x_now");
    const double days = in.real("days_since"), k = in.real("k");
    sk::check_changes_shape(changes.size());
    in.ready();
    const sk::Trigger t = sk::trigger_check(changes, x_ref, x_now, days, k);
    out.values.key("fire");
    out.values.boolean(t.fire);
    out.key_real("sigma", t.sigma);
    out.key_real("threshold", t.threshold);
    out.key_real("false_alarm_rate", t.false_alarm_rate);
}

void op_intraday_bound(const In& in, Out& out) {
    std::vector<sk::ZeroPosition> positions;
    for (const Value& item : array_named(in, "positions").items) {
        if (item.kind != Kind::Object) schema("positions", "expected an array of objects");
        const In p(item);
        const double notional = p.real("notional"), maturity = p.real("maturity");
        positions.push_back({notional, maturity, p.real("yield")});
    }
    const double shift = in.real("shift");
    sk::check_positions_shape(positions.size());
    in.ready();
    const sk::Intraday r = sk::delta_gamma_bound(positions, shift);
    out.key_real("estimate_pnl", r.estimate_pnl);
    out.key_real("bound", r.bound);
    out.key_string("label", sk::label);
}

void op_richardson_check(const In& in, Out& out) {
    const Vec values = in.reals("values");
    const double ratio = in.real("ratio"), order = in.real("assumed_order");
    sk::check_values_shape(values.size());
    in.ready();
    const sk::Richardson r = sk::richardson_check(values, ratio, order);
    out.key_string("status", sk::status_name(r.status));
    out.key_maybe("observed_order", r.observed_order);
    out.key_maybe("extrapolated", r.extrapolated);
}

constexpr Entry stage_k_ops[] = {
    {"calib.trigger.check", op_trigger_check},
    {"core.store.bitemporal_query", op_bitemporal_query},
    {"curve.bootstrap.par_annual", op_par_annual},
    {"curve.incremental.update", op_incremental_update},
    {"num.richardson.check", op_richardson_check},
    {"risk.intraday.delta_gamma_bound", op_intraday_bound},
};

// The verbs that carry their own stage K sizes in place of the general array limit.
bool stage_k_verb(string_view op) {
    return std::ranges::any_of(stage_k_ops, [op](const Entry& e) { return e.verb == op; });
}
