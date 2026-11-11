package org.quantforge.cli;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.hedging.CorrelationHedge;
import org.quantforge.hedging.CreditHedge;
import org.quantforge.pricing.Credit;

/**
 * Stage I wave 2: credit and correlation hedges ({@code 08-hedging/credit-and-correlation-hedges.md}). Inputs are read
 * first (E_SCHEMA), then the size limits of ruling I-19, then the finite rule F-2, then each operation's own checks.
 */
final class OpsHedgeCreditCorr {
    private OpsHedgeCreditCorr() {}

    private static final int MAX_BOOK = 1_000;
    private static final int MAX_CREDIT_HEDGES = 50;
    private static final int MAX_CORRELATION_HEDGES = 5;
    private static final Set<String> NUMERIC_KEYS = Set.of("quantity1", "quantity2", "expiry_years", "strike",
            "quantity");

    static void register(Map<String, Function<In, Out>> table) {
        table.put("hedge.credit.cds", OpsHedgeCreditCorr::credit);
        table.put("hedge.correlation.neutralise", OpsHedgeCreditCorr::correlation);
    }

    private static boolean buyer(In tr) {
        return switch (tr.string("side")) {
            case "BUY_PROTECTION" -> true;
            case "SELL_PROTECTION" -> false;
            default -> throw new QfError("E_SCHEMA", "unknown side", "side");
        };
    }

    private static Map<String, Object> risk(CreditHedge.Risk r, boolean withPv) {
        Map<String, Object> m = new LinkedHashMap<>();
        if (withPv) {
            m.put("pv", r.pv());
        }
        m.put("cs01", r.cs01());
        m.put("jtd", r.jtd());
        m.put("buckets", r.buckets());
        return m;
    }

    private static Out credit(In in) {
        LocalDate t = in.date("trade_date");
        OpsLinear.CurveInput d = OpsLinear.curve(in, "discount");
        OpsCredit.HazardInput h = OpsCredit.hazard(in);
        double r = in.real("recovery");
        List<In> bookIn = in.objects("book");
        List<CreditHedge.Trade> book = new ArrayList<>();
        for (In tr : bookIn) {
            book.add(new CreditHedge.Trade(tr.date("maturity"), tr.real("coupon"), tr.real("notional"), buyer(tr)));
        }
        List<In> hedgeIn = in.objects("hedges");
        List<CreditHedge.Contract> hedges = new ArrayList<>();
        for (In c : hedgeIn) {
            hedges.add(new CreditHedge.Contract(c.date("maturity"), c.real("coupon")));
        }
        List<String> targets = in.strings("targets");
        in.limit(bookIn.size() > MAX_BOOK, "book");
        in.limit(hedgeIn.size() > MAX_CREDIT_HEDGES, "hedges");
        in.gate();
        OpsCredit.logLinear(d);
        Credit.Hazard hazard = h.build();
        var curve = d.build();
        Credit.checkAsOf(t, curve, hazard);
        CreditHedge.Result res = CreditHedge.solve(t, curve, hazard, r, book, hedges, targets);
        return Operations.out("notionals", res.notionals(), "book", risk(res.book(), true), "after",
                risk(res.after(), false), "hedge_upfront", res.hedgeUpfront());
    }

    private static CorrelationHedge.Instrument instrument(In p) {
        CorrelationHedge.Kind kind = p.choice("instrument", CorrelationHedge.Kind.class);
        Map<String, Double> values = new LinkedHashMap<>();
        boolean unknown = false;
        for (String k : p.keys()) {
            if (k.equals("instrument")) {
                continue;
            }
            if (NUMERIC_KEYS.contains(k)) {
                p.notNull(k);
                values.put(k, p.real(k));
            } else {
                unknown = true;
            }
        }
        return new CorrelationHedge.Instrument(kind, values, unknown);
    }

    private static Out correlation(In in) {
        CorrelationHedge.Market mk = new CorrelationHedge.Market(in.real("spot1"), in.real("spot2"), in.real("rate"),
                in.real("yield1"), in.real("yield2"), in.real("vol1"), in.real("vol2"), in.real("correlation"));
        List<In> bookIn = in.objects("book");
        List<In> hedgeIn = in.objects("hedges");
        List<CorrelationHedge.Instrument> book = new ArrayList<>();
        for (In p : bookIn) {
            book.add(instrument(p));
        }
        List<CorrelationHedge.Instrument> hedges = new ArrayList<>();
        for (In p : hedgeIn) {
            hedges.add(instrument(p));
        }
        List<CorrelationHedge.Target> targets = new ArrayList<>();
        for (String s : in.strings("targets")) {
            targets.add(In.parseEnum("targets", s, CorrelationHedge.Target.class));
        }
        in.limit(bookIn.size() > MAX_BOOK, "book");
        in.limit(hedgeIn.size() > MAX_CORRELATION_HEDGES, "hedges");
        in.gate();
        CorrelationHedge.Result r = CorrelationHedge.solve(mk, book, hedges, targets);
        return Operations.out("quantities", r.quantities(), "greeks_before", greeks(r.before()), "greeks_after",
                greeks(r.after()));
    }

    private static Map<String, Object> greeks(double[] g) {
        return Operations.out("delta_1", g[0], "delta_2", g[1], "vega_1", g[2], "vega_2", g[3], "correlation01", g[4])
                .outputs();
    }
}
