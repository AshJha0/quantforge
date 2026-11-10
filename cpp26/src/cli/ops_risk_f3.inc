#include "quantforge/core/risk_f3.hpp"
// CLI handlers, stage F risk_f3 (06-risk/book-sensitivities.md). Included by dispatch.cpp inside its unnamed namespace.

void f3_matrix(Out& out, string_view key, const Matrix& m) {
    out.values.key(key);
    out.values.begin_array();
    for (const auto& row : m) {
        out.values.begin_array();
        for (const double x : row) out.values.real(x);
        out.values.end_array();
    }
    out.values.end_array();
}

void f3_strings(Out& out, string_view key, const std::vector<string>& v) {
    out.values.key(key);
    out.values.begin_array();
    for (const string& s : v) out.values.string(s);
    out.values.end_array();
}

void op_book_ois_sensitivity(const In& in, Out& out) {
    const Date as_of = in.date("as_of");
    const RateConvention* c = ois_convention_of(in.need("convention"), "convention");
    const auto raw = quotes_of(in);
    std::vector<string> labels;
    for (const Value& q : in.need("quotes").items) labels.push_back(In(q).text("tenor"));
    const auto interpolation = in.choice("interpolation", curve_interpolations);
    const auto swaps = rows_of<BookSwap>(in, "swaps", [](const In& r) {
        return BookSwap{r.text("id"), r.integer("tenor_years"), r.real("fixed_rate"),
                        r.choice<FixedSide>("side", {{"PAYER", FixedSide::Pay}, {"RECEIVER", FixedSide::Receive}})};
    });
    in.ready();
    const auto quotes = checked_quotes(raw);
    limit_if(swaps.size() > 100000, "swaps");
    check_crossed(raw);
    const BookSensitivity r = ois_book_sensitivity(*c, as_of, quotes, interpolation, swaps);
    out.key_reals("pv", r.pv);
    out.key_real("book_pv", r.book_pv);
    out.values.key("quote_sensitivity");
    out.values.begin_object();
    std::vector<string> ids;
    for (const BookSwap& s : swaps) ids.push_back(s.id);
    f3_strings(out, "swaps", ids);
    f3_strings(out, "quotes", labels);
    f3_matrix(out, "matrix", r.quote_sensitivity);
    out.values.end_object();
    out.key_reals("book_sensitivity", r.book_sensitivity);
    out.values.key("zero_jacobian");
    out.values.begin_object();
    std::vector<string> pillars;
    for (const Date d : r.pillars) pillars.push_back(format_date(d));
    f3_strings(out, "pillars", pillars);
    f3_strings(out, "quotes", labels);
    f3_matrix(out, "matrix", r.zero_jacobian);
    out.values.end_object();
}

void op_curve_pca(const In& in, Out& out) {
    const Matrix changes = in.matrix("changes");
    const long long k = in.integer("components");
    in.ready();
    limit_if(changes.size() > 100000, "changes");
    limit_if(!changes.empty() && changes[0].size() > max_quotes, "changes");
    const CurvePca r = curve_pca(changes, k);
    out.key_reals("eigenvalues", r.eigenvalues);
    f3_matrix(out, "loadings", r.loadings);
    out.key_reals("explained_ratio", r.explained_ratio);
}

void op_curve_cross_gamma(const In& in, Out& out) {
    const CurveInput ci = curve_of(in, "curve");
    // The product is {kind: "OIS", trade} with side PAYER or RECEIVER (the golden spelling of this verb).
    const Value& pv = in.need("product");
    if (pv.kind != Kind::Object) schema("product", "expected an object");
    const In p(pv);
    p.choice<int>("kind", {{"OIS", 0}});
    const Value& tv = p.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In t(tv);
    const OisTrade trade{ois_convention_of(t.need("convention"), "convention"), parse_tenor(t.text("tenor")),
                         t.real("fixed_rate"), t.real("notional"),
                         t.choice<FixedSide>("side", {{"PAYER", FixedSide::Pay}, {"RECEIVER", FixedSide::Receive}})};
    const double bump = in.real("bump_bp");
    in.ready();
    ci.limit();
    check_bump(bump);
    const CrossGamma r = cross_gamma(ci.build(), trade, bump);
    out.key_real("value", r.value);
    f3_matrix(out, "cross_gamma", r.gamma);
}

void op_credit_jtd(const In& in, Out& out) {
    const auto positions = rows_of<JtdPosition>(in, "positions", [](const In& r) {
        return JtdPosition{r.text("id"),
                           r.choice<JtdKind>("kind", {{"BOND", JtdKind::Bond},
                                                      {"CDS_PROTECTION_BUYER", JtdKind::CdsProtectionBuyer},
                                                      {"CDS_PROTECTION_SELLER", JtdKind::CdsProtectionSeller}}),
                           r.real("notional"), r.real("recovery"), r.real("market_value")};
    });
    in.ready();
    limit_if(positions.size() > 100000, "positions");
    const Jtd r = jump_to_default(positions);
    out.key_reals("jtd", r.jtd);
    out.key_real("total", r.total);
}

constexpr Entry risk_f3_ops[] = {
    {"risk.book.ois_sensitivity", op_book_ois_sensitivity},
    {"risk.credit.jtd", op_credit_jtd},
    {"risk.curve.cross_gamma", op_curve_cross_gamma},
    {"risk.curve.pca", op_curve_pca},
};
