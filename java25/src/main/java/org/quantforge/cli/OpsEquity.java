package org.quantforge.cli;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.pricing.EquityCurves;

/** Stage D wave 2, D5: equity curves, index, corporate actions, TRS. */
final class OpsEquity {
    private OpsEquity() {}

    private static final int MAX = 1000;

    private static List<EquityCurves.Div> divs(In in, String key) {
        List<In> l = in.objects(key);
        in.limit(l.size() > MAX, key);
        List<EquityCurves.Div> out = new ArrayList<>();
        for (In d : l) {
            out.add(new EquityCurves.Div(d.date("ex_date"), d.real("amount")));
        }
        return out;
    }

    private static List<EquityCurves.Constituent> constituents(In in, String key, boolean withDivs) {
        List<In> l = in.objects(key);
        in.limit(l.size() > MAX, key);
        List<EquityCurves.Constituent> out = new ArrayList<>();
        for (In c : l) {
            out.add(new EquityCurves.Constituent(c.string("id"), c.real("shares"), c.real("price"),
                    withDivs ? divs(c, "dividends") : List.of()));
        }
        return out;
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("eq.dividend.implied", in -> {
            double spot = in.real("spot");
            OpsLinear.CurveInput f = OpsLinear.curve(in, "funding");
            double b = in.real("borrow_rate");
            List<In> fut = in.objects("futures");
            in.limit(fut.size() > MAX, "futures");
            LocalDate[] e = new LocalDate[fut.size()];
            double[] p = new double[e.length];
            for (int i = 0; i < e.length; i++) {
                e[i] = fut.get(i).date("expiry");
                p[i] = fut.get(i).real("price");
            }
            in.gate();
            EquityCurves.Implied r = EquityCurves.impliedDividends(spot, f.build(), b, e, p);
            return Operations.out("pv_dividends", r.pv(), "period_pv_dividends", r.period(),
                    "dividend_yields", r.yields());
        });
        table.put("eq.borrow.implied", in -> {
            double spot = in.real("spot");
            OpsLinear.CurveInput f = OpsLinear.curve(in, "funding");
            List<EquityCurves.Div> d = divs(in, "dividends");
            LocalDate expiry = in.date("expiry");
            double fwd = in.real("forward");
            in.gate();
            return Operations.out("borrow_rate", EquityCurves.impliedBorrow(spot, f.build(), d, expiry, fwd));
        });
        table.put("eq.futures.basis", in -> {
            double spot = in.real("spot");
            OpsLinear.CurveInput f = OpsLinear.curve(in, "funding");
            double b = in.real("borrow_rate");
            double s = in.real("financing_spread");
            List<EquityCurves.Div> d = divs(in, "dividends");
            LocalDate expiry = in.date("expiry");
            double price = in.real("futures_price");
            in.gate();
            EquityCurves.Basis r = EquityCurves.futuresBasis(spot, f.build(), b, s, d, expiry, price);
            return Operations.out("fair_price", r.fair(), "basis", r.basis(),
                    "implied_financing_spread", r.impliedSpread());
        });
        table.put("eq.index.dividends", in -> {
            double divisor = in.real("divisor");
            List<EquityCurves.Constituent> cs = constituents(in, "constituents", true);
            List<In> per = in.objects("periods");
            in.limit(per.size() > MAX, "periods");
            LocalDate[] s = new LocalDate[per.size()];
            LocalDate[] e = new LocalDate[s.length];
            for (int i = 0; i < s.length; i++) {
                s[i] = per.get(i).date("start");
                e[i] = per.get(i).date("end");
            }
            double[] implied = in.reals("implied_period_points");
            in.gate();
            EquityCurves.IndexDivs r = EquityCurves.indexDividends(divisor, cs, s, e, implied);
            return Operations.out("level", r.level(), "ex_dates", r.exDates().stream().map(LocalDate::toString).toList(),
                    "points", r.points(), "period_points", r.periodPoints(), "basis", r.basis());
        });
        table.put("eq.index.rebalance", in -> {
            double divisor = in.real("divisor");
            List<EquityCurves.Constituent> old = constituents(in, "constituents", false);
            List<EquityCurves.Constituent> neu = constituents(in, "new_constituents", false);
            in.gate();
            EquityCurves.Rebalance r = EquityCurves.rebalance(divisor, old, neu);
            return Operations.out("level", r.level(), "new_divisor", r.newDivisor(), "weights", r.weights());
        });
        table.put("eq.corporate_action.adjust", in -> {
            String action = in.string("action");
            double p = in.real("cum_price");
            double shares = in.real("shares");
            double strike = in.real("strike");
            Double ratio = null;
            Double m = null;
            Double k = null;
            Double amount = null;
            switch (action) {
                case "SPLIT", "REVERSE_SPLIT" -> ratio = in.real("ratio");
                case "RIGHTS" -> {
                    m = in.real("new_per_old");
                    k = in.real("subscription_price");
                }
                case "SPECIAL_DIVIDEND" -> amount = in.real("amount");
                default -> throw new QfError("E_SCHEMA", "unknown action", "action");
            }
            in.gate();
            EquityCurves.Action r = EquityCurves.corporateAction(action, p, shares, strike, ratio, m, k, amount);
            return Operations.out("factor", r.factor(), "ex_price", r.exPrice(), "adjusted_shares", r.shares(),
                    "adjusted_strike", r.strike());
        });
        table.put("eq.trs.pv", in -> {
            double spot = in.real("spot");
            OpsLinear.CurveInput f = OpsLinear.curve(in, "funding");
            double b = in.real("borrow_rate");
            List<EquityCurves.Div> d = divs(in, "dividends");
            In t = in.object("trade");
            LocalDate start = t.date("start");
            LocalDate end = t.date("end");
            double s0 = t.real("initial_price");
            double n = t.real("shares");
            double spread = t.real("spread");
            String side = t.string("side");
            if (!side.equals("RECEIVE_EQUITY") && !side.equals("PAY_EQUITY")) {
                throw new QfError("E_SCHEMA", "unknown side", "side");
            }
            Double current = in.nullableReal("current_rate");
            in.gate();
            EquityCurves.Trs r = EquityCurves.trs(spot, f.build(), b, d, start, end, s0, n, spread, side.equals("RECEIVE_EQUITY"),
                    current);
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("equity_leg", r.equityLeg());
            out.put("funding_leg", r.fundingLeg());
            out.put("pv", r.pv());
            return new Out(out, Map.of());
        });
    }
}
