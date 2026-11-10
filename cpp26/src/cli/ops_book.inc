#include "quantforge/core/book.hpp"
// CLI handlers, stage F book (F5): book.lifecycle.apply, book.marks.resolve and use case 4.
// Included by dispatch.cpp inside its unnamed namespace.

BookPosition book_position_of(const In& r) { return {r.text("instrument"), r.real("quantity"), r.real("average_cost")}; }

BookEvent book_event_of(const In& r) {
    BookEvent e;
    e.date = r.date("date");
    const string& type = r.text("type");
    if (type == "TRADE") {
        e.type = BookEventType::Trade;
        e.instrument = r.text("instrument");
        e.quantity = r.real("quantity");
        e.price = r.real("price");
    } else if (type == "FIXING") {
        e.type = BookEventType::Fixing;
        e.instrument = r.text("index");
        e.price = r.real("value");
    } else if (type == "EXPIRY") {
        e.type = BookEventType::Expiry;
        e.instrument = r.text("instrument");
        e.price = r.real("settlement_price");
    } else if (type == "DEFAULT") {
        e.type = BookEventType::Default;
        e.instrument = r.text("instrument");
        e.price = r.real("recovery_price");
    } else if (type == "ROLL") {
        e.type = BookEventType::Roll;
        e.instrument = r.text("from");
        e.to = r.text("to");
        e.price = r.real("from_price");
        e.to_price = r.real("to_price");
    } else {
        schema("type", "value is not listed");
    }
    return e;
}

void op_book_lifecycle_apply(const In& in, Out& out) {
    const auto positions = rows_of<BookPosition>(in, "positions", book_position_of);
    const auto events = rows_of<BookEvent>(in, "events", book_event_of);
    in.ready();
    const BookResult r = apply_lifecycle(positions, events);
    out.values.key("positions");
    out.values.begin_array();
    for (const BookPosition& p : r.positions) {
        out.values.begin_object();
        out.key_string("instrument", p.instrument);
        out.key_real("quantity", p.quantity);
        out.key_real("average_cost", p.average_cost);
        out.values.end_object();
    }
    out.values.end_array();
    out.values.key("realized_pnl");
    out.values.begin_array();
    for (const auto& [name, pnl] : r.realized) {
        out.values.begin_object();
        out.key_string("instrument", name);
        out.key_real("pnl", pnl);
        out.values.end_object();
    }
    out.values.end_array();
    out.key_real("total_realized", r.total_realized);
    out.values.key("fixings");
    out.values.begin_array();
    for (const BookFixing& f : r.fixings) {
        out.values.begin_object();
        out.key_string("index", f.index);
        out.key_string("date", format_date(f.date));
        out.key_real("value", f.value);
        out.values.end_object();
    }
    out.values.end_array();
}

MarkQuote mark_quote_of(const In& r) { return {r.text("instrument"), r.date("date"), r.real("price")}; }

MarkSource mark_source_of(const In& r) { return {r.text("name"), rows_of<MarkQuote>(r, "quotes", mark_quote_of)}; }

std::pair<string, double> ipv_price_of(const In& r) { return {r.text("instrument"), r.real("price")}; }

constexpr string_view mark_status_name(MarkStatus s) {
    switch (s) {
    case MarkStatus::Primary: return "PRIMARY";
    case MarkStatus::Fallback: return "FALLBACK";
    case MarkStatus::Stale: return "STALE";
    case MarkStatus::Missing: break;
    }
    return "MISSING";
}

void op_book_marks_resolve(const In& in, Out& out) {
    const Date as_of = in.date("as_of");
    const Value& list = in.need("instruments");
    if (list.kind != Kind::Array) schema("instruments", "expected an array");
    std::vector<string> instruments;
    for (const Value& v : list.items) instruments.push_back(to_string(v, "instruments"));
    const auto sources = rows_of<MarkSource>(in, "sources", mark_source_of);
    const long long max_age = in.integer("max_age_days");
    const auto ipv = in.find("ipv") ? rows_of<std::pair<string, double>>(in, "ipv", ipv_price_of)
                                    : std::vector<std::pair<string, double>>{};
    const double threshold = in.real("ipv_threshold");
    in.ready();
    const std::vector<Mark> marks = resolve_marks(as_of, instruments, sources, max_age, ipv, threshold);
    out.values.key("marks");
    out.values.begin_array();
    for (const Mark& m : marks) {
        out.values.begin_object();
        out.key_string("instrument", m.instrument);
        out.key_maybe("price", m.price);
        out.values.key("source");
        if (m.source) out.values.string(*m.source);
        else out.values.null();
        out.key_string("status", mark_status_name(m.status));
        out.values.key("age_days");
        if (m.age_days) out.values.integer(*m.age_days);
        else out.values.null();
        out.key_maybe("ipv_diff", m.ipv_diff);
        out.values.key("ipv_breach");
        out.values.boolean(m.ipv_breach);
        out.values.end_object();
    }
    out.values.end_array();
}

void op_usecase_factor_attribution(const In& in, Out& out) {
    const Vec y = in.reals("portfolio_returns");
    const Matrix f = in.matrix("factor_returns");
    const Value& names = in.need("factor_names");
    if (names.kind != Kind::Array) schema("factor_names", "expected an array");
    for (const Value& v : names.items) to_string(v, "factor_names");
    in.ready();
    const FactorAttribution r = factor_attribution(y, f, names.items.size());
    out.key_real("alpha", r.alpha);
    out.key_reals("betas", r.betas);
    out.key_real("r_squared", r.r_squared);
    out.key_reals("contributions", r.contributions);
    out.key_real("mean_return", r.mean_return);
    out.key_real("residual_vol", r.residual_vol);
    out.key_reals("beta_se", r.beta_se);
}

constexpr Entry book_ops[] = {
    {"book.lifecycle.apply", op_book_lifecycle_apply},
    {"book.marks.resolve", op_book_marks_resolve},
    {"usecase.factor_attribution", op_usecase_factor_attribution},
};
