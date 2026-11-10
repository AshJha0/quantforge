// CLI handlers, the equity verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_eq_outright(const In& in, Out& out) {
    const ForwardInput f = forward_of(in);
    in.ready();
    const EquityForward r = f.solve();
    out.key_real("forward", r.forward);
    out.key_real("discount_factor", r.discount_factor);
    out.key_real("carry_factor", r.carry_factor);
    out.key_real("pv_dividends", r.pv_dividends);
}

void op_eq_flat(const In& in, Out& out) {
    const double spot = in.real("spot"), rate = in.real("rate"), borrow = in.real("borrow"), t = in.real("expiry_years");
    const auto dividends = rows_of<TimedDividend>(in, "dividends", [](const In& r) { return TimedDividend{r.real("time_years"), r.real("amount")}; });
    in.ready();
    limit_if(dividends.size() > max_quotes, "dividends");
    out.key_real("forward", equity_forward_flat(spot, rate, borrow, t, dividends));
}

void op_eq_parity(const In& in, Out& out) {
    const auto quotes = rows_of<ParityQuote>(in, "quotes", parity_quote_of);
    require_key(in, "discount_factor");
    const auto d = to_maybe_real(*in.raw().find("discount_factor"), "discount_factor");
    in.ready();
    limit_if(quotes.size() > max_quotes, "quotes");
    const ParityForward r = parity_forward(quotes, d);
    out.key_real("forward", r.forward);
    out.key_real("discount_factor", r.discount_factor);
    out.key_real("max_residual", r.max_residual);
    out.key_reals("outside_spread", r.outside_spread);
}

void op_dividend_implied(const In& in, Out& out) {
    const double spot = in.real("spot");
    const CurveInput f = curve_of(in, "funding");
    const double b = in.real("borrow_rate");
    const auto futures = rows_of<FuturesQuote>(in, "futures", [](const In& r) { return FuturesQuote{r.date("expiry"), r.real("price")}; });
    in.ready();
    f.limit();
    limit_if(futures.size() > max_quotes, "futures");
    const ImpliedDividends r = implied_dividends(spot, f.build(), b, futures);
    out.key_reals("pv_dividends", r.pv_dividends);
    out.key_reals("period_pv_dividends", r.period_pv_dividends);
    out.key_reals("dividend_yields", r.dividend_yields);
}

void op_borrow_implied(const In& in, Out& out) {
    const double spot = in.real("spot");
    const CurveInput f = curve_of(in, "funding");
    const auto divs = cash_dividends_of(in);
    const Date expiry = in.date("expiry");
    const double fwd = in.real("forward");
    in.ready();
    f.limit();
    out.key_real("borrow_rate", implied_borrow(spot, f.build(), divs, expiry, fwd));
}

void op_equity_futures_basis(const In& in, Out& out) {
    const double spot = in.real("spot");
    const CurveInput f = curve_of(in, "funding");
    const double b = in.real("borrow_rate"), s = in.real("financing_spread");
    const auto divs = cash_dividends_of(in);
    const Date expiry = in.date("expiry");
    const double price = in.real("futures_price");
    in.ready();
    f.limit();
    const FuturesBasis r = equity_futures_basis(spot, f.build(), b, s, divs, expiry, price);
    out.key_real("fair_price", r.fair_price);
    out.key_real("basis", r.basis);
    out.key_real("implied_financing_spread", r.implied_financing_spread);
}

void op_index_dividends(const In& in, Out& out) {
    const double divisor = in.real("divisor");
    const auto cs = constituents_of(in, "constituents", true);
    const auto periods = rows_of<Period2>(in, "periods", [](const In& r) { return Period2{r.date("start"), r.date("end")}; });
    const Vec implied = in.reals("implied_period_points");
    in.ready();
    const IndexDividends r = index_dividends(divisor, cs, periods, implied);
    out.key_real("level", r.level);
    out.values.key("ex_dates");
    out.values.begin_array();
    for (const Date d : r.ex_dates) out.values.string(format_date(d));
    out.values.end_array();
    out.key_reals("points", r.points);
    out.key_reals("period_points", r.period_points);
    out.key_reals("basis", r.basis);
}

void op_index_rebalance(const In& in, Out& out) {
    const double divisor = in.real("divisor");
    const auto a = constituents_of(in, "constituents", false), b = constituents_of(in, "new_constituents", false);
    in.ready();
    const Rebalance r = index_rebalance(divisor, a, b);
    out.key_real("level", r.level);
    out.key_real("new_divisor", r.new_divisor);
    out.key_reals("weights", r.weights);
}

void op_corporate_action(const In& in, Out& out) {
    const auto action = in.choice<CorporateAction>("action", {{"SPLIT", CorporateAction::Split},
                                                              {"REVERSE_SPLIT", CorporateAction::ReverseSplit},
                                                              {"RIGHTS", CorporateAction::Rights},
                                                              {"SPECIAL_DIVIDEND", CorporateAction::SpecialDividend}});
    const double p = in.real("cum_price"), shares = in.real("shares"), strike = in.real("strike");
    double a = 0.0, k = 0.0;
    if (action == CorporateAction::Rights) {
        a = in.real("new_per_old");
        k = in.real("subscription_price");
    } else {
        a = in.real(action == CorporateAction::SpecialDividend ? "amount" : "ratio");
    }
    in.ready();
    const ActionResult r = corporate_action(action, p, shares, strike, a, k);
    out.key_real("factor", r.factor);
    out.key_real("ex_price", r.ex_price);
    out.key_real("adjusted_shares", r.adjusted_shares);
    out.key_real("adjusted_strike", r.adjusted_strike);
}

void op_trs_pv(const In& in, Out& out) {
    const double spot = in.real("spot");
    const CurveInput f = curve_of(in, "funding");
    const double b = in.real("borrow_rate");
    const auto divs = cash_dividends_of(in);
    const Value& tv = in.need("trade");
    if (tv.kind != Kind::Object) schema("trade", "expected an object");
    const In t(tv);
    const TrsTrade trade{t.date("start"), t.date("end"), t.real("initial_price"), t.real("shares"), t.real("spread"),
                         t.choice<double>("side", {{"RECEIVE_EQUITY", 1.0}, {"PAY_EQUITY", -1.0}})};
    const Value* cr = in.raw().find("current_rate");
    if (!cr) schema("current_rate", "missing");
    const std::optional<double> rate = cr->kind == Kind::Null ? std::nullopt : std::optional<double>(to_real(*cr, "current_rate"));
    in.ready();
    f.limit();
    const TrsPrice r = trs_price(spot, f.build(), b, divs, trade, rate);
    out.key_real("equity_leg", r.equity_leg);
    out.key_real("funding_leg", r.funding_leg);
    out.key_real("pv", r.pv);
}

constexpr Entry equity_ops[] = {
    {"eq.borrow.implied", op_borrow_implied},
    {"eq.corporate_action.adjust", op_corporate_action},
    {"eq.dividend.implied", op_dividend_implied},
    {"eq.forward.flat", op_eq_flat},
    {"eq.forward.outright", op_eq_outright},
    {"eq.forward.parity", op_eq_parity},
    {"eq.futures.basis", op_equity_futures_basis},
    {"eq.index.dividends", op_index_dividends},
    {"eq.index.rebalance", op_index_rebalance},
    {"eq.trs.pv", op_trs_pv},
};
