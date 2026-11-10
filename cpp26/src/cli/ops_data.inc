// CLI handlers, units of money, snapshots, market data checks and the as-of store.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_snapshot_hash(const In& in, Out& out) {
    const string& text = in.text("document_text");
    const SnapshotHash h = snapshot_hash(text);  // one linear pass, and its E_SCHEMA comes first
    in.ready();
    out.key_string("canonical", h.canonical);
    out.key_string("snapshot_id", h.snapshot_id);
}

void op_check_quotes(const In& in, Out& out) {
    QuoteCheckInputs c;
    c.as_of = in.instant("as_of");
    const Value& quotes = in.need("quotes");
    if (quotes.kind != Kind::Array) schema("quotes", "expected an array");
    for (const Value& q : quotes.items) c.quotes.push_back(quote_of(q));
    c.stale_after_seconds = in.integer("stale_after_seconds");
    if (in.find("max_relative_spread")) c.max_relative_spread = in.real("max_relative_spread");
    c.positive_only = in.boolean("positive_only", false);
    c.outlier_threshold = in.real("outlier_threshold", 5.0);
    c.outlier_min_history = in.integer("outlier_min_history", 5);
    if (const Value* h = in.find("history")) {
        if (h->kind != Kind::Object) schema("history", "expected an object");
        for (const auto& [id, mids] : h->members) c.history[id] = to_reals(mids, "history");
    }
    in.ready();
    const auto results = check_quotes(c);
    out.values.key("results");
    out.values.begin_array();
    for (const QuoteCheckResult& r : results) {
        out.values.begin_object();
        out.key_string("instrument_id", r.instrument_id);
        out.key_string("quote_status", r.quote_status);
        out.values.key("quality_flags");
        out.values.begin_array();
        for (const string& f : r.quality_flags) out.values.string(f);
        out.values.end_array();
        out.values.end_object();
    }
    out.values.end_array();
}

void op_store_query(const In& in, Out& out) {
    const auto log = log_of(in);
    const Instant as_of = in.instant("as_of");
    const string* series = in.find("series_id") ? &in.text("series_id") : nullptr;
    const auto from = maybe_instant(in, "event_from"), to = maybe_instant(in, "event_to");
    in.ready();
    check_store_nesting(log);
    check_store(log, {as_of, from, to});
    if (from && to && *from > *to) throw Error("E_DATE_ORDER", "event_from is after event_to", "event_from");
    out.values.key("rows");
    out.values.begin_array();
    for (const StoreRow& r : store_view(log, as_of)) {
        if (series && r.series_id != *series) continue;
        if ((from && r.event_time < *from) || (to && r.event_time > *to)) continue;
        write_row(out, r);
    }
    out.values.end_array();
}

void op_store_latest(const In& in, Out& out) {
    const auto log = log_of(in);
    const Instant as_of = in.instant("as_of");
    const string& series = in.text("series_id");
    in.ready();
    check_store_nesting(log);
    check_store(log, {as_of});
    std::optional<StoreRow> best;
    for (StoreRow& r : store_view(log, as_of))
        if (r.series_id == series) best = std::move(r);  // the view ascends by event_time
    out.values.key("row");
    if (best) write_row(out, *best);
    else out.values.null();
}

void op_store_snapshot(const In& in, Out& out) {
    const auto log = log_of(in);
    const Instant as_of = in.instant("as_of");
    in.ready();
    check_store_nesting(log);
    check_store(log, {as_of});
    const SnapshotHash h = store_snapshot(log, as_of);
    out.key_string("canonical", h.canonical);
    out.key_string("snapshot_id", h.snapshot_id);
}

void op_store_replay(const In& in, Out& out) {
    const auto log = log_of(in);
    const Value& a = in.need("checkpoints");
    if (a.kind != Kind::Array) schema("checkpoints", "expected an array");
    std::vector<Instant> points;
    for (const Value& v : a.items) points.push_back(to_instant_value(v, "checkpoints"));
    in.ready();
    limit_if(points.size() > 1000, "checkpoints");
    limit_if(product_above((long long)log.size(), (long long)points.size(), 10000000), "checkpoints");
    check_store_nesting(log);
    check_store(log, std::vector<std::optional<Instant>>(points.begin(), points.end()));
    const auto replay = store_replay(log, points);
    out.values.key("snapshots");
    out.values.begin_array();
    for (const ReplayPoint& p : replay) {
        out.values.begin_object();
        out.key_string("as_of", format_instant(p.as_of));
        out.values.key("row_count");
        out.values.integer((long long)p.row_count);
        out.key_string("snapshot_id", p.snapshot_id);
        out.values.end_object();
    }
    out.values.end_array();
    out.key_string("head", store_chain(log).head);
}

void op_store_chain(const In& in, Out& out) {
    const auto log = log_of(in);
    in.ready();
    check_store_nesting(log);
    check_store(log, {});
    const Chain c = store_chain(log);
    out.key_string("head", c.head);
    out.values.key("hashes");
    out.values.begin_array();
    for (const string& h : c.hashes) out.values.string(h);
    out.values.end_array();
}

void op_units_convert(const In& in, Out& out) {
    static constexpr EnumTable<RateUnit> units = {{"DECIMAL", RateUnit::Decimal}, {"PERCENT", RateUnit::Percent}, {"BP", RateUnit::Bp}};
    const double v = in.real("value");
    const RateUnit from = in.choice("from", units), to = in.choice("to", units);
    in.ready();
    out.key_real("value", convert_unit(v, from, to));
}

void op_add_money(const In& in, Out& out) {
    const Value& av = in.need("a");
    const Value& bv = in.need("b");
    if (av.kind != Kind::Object) schema("a", "expected an object");
    if (bv.kind != Kind::Object) schema("b", "expected an object");
    const MoneyInput a = money_of(In(av)), b = money_of(In(bv));
    in.ready();
    limit_amount(a);
    limit_amount(b);
    if (a.currency != b.currency) throw Error("E_CURRENCY_MISMATCH", "currencies differ");
    out.key_string("amount", format_shortest(parse_amount(*a.amount) + parse_amount(*b.amount)));
    out.key_string("currency", a.currency);
}

void op_round_money(const In& in, Out& out) {
    const MoneyInput m = money_of(in);
    in.ready();
    limit_amount(m);
    out.key_string("amount", round_to_places(parse_amount(*m.amount), minor_units(m.currency)));
    out.key_string("currency", m.currency);
}

constexpr Entry data_ops[] = {
    {"core.data.check_quotes", op_check_quotes},
    {"core.snapshot.hash", op_snapshot_hash},
    {"core.store.chain", op_store_chain},
    {"core.store.latest", op_store_latest},
    {"core.store.query_as_of", op_store_query},
    {"core.store.replay", op_store_replay},
    {"core.store.snapshot", op_store_snapshot},
    {"core.units.add_money", op_add_money},
    {"core.units.convert", op_units_convert},
    {"core.units.round_money", op_round_money},
};
