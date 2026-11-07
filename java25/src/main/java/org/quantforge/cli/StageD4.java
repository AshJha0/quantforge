package org.quantforge.cli;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.pricing.Credit;

/** Stage D wave 2, D4: credit. */
final class StageD4 {
    private StageD4() {}

    private record HazardInput(LocalDate asOf, LocalDate[] dates, double[] survival) {
        Credit.Hazard build() {
            return new Credit.Hazard(asOf, dates, survival);
        }
    }

    private static HazardInput hazard(In in) {
        In h = in.object("hazard");
        LocalDate asOf = h.date("as_of");
        List<In> p = h.objects("pillars");
        in.limit(p.size() > 100, "hazard");
        LocalDate[] d = new LocalDate[p.size()];
        double[] s = new double[d.length];
        for (int i = 0; i < d.length; i++) {
            d[i] = p.get(i).date("date");
            s[i] = p.get(i).real("survival");
        }
        return new HazardInput(asOf, d, s);
    }

    private record Quotes(String[] tenors, double[] spreads) {}

    private static Quotes quotes(In in) {
        List<In> q = in.objects("quotes");
        in.limit(q.size() > 100, "quotes");
        String[] t = new String[q.size()];
        double[] s = new double[t.length];
        for (int i = 0; i < t.length; i++) {
            t[i] = q.get(i).string("tenor");
            s[i] = q.get(i).real("spread");
        }
        return new Quotes(t, s);
    }

    private static List<Map<String, Object>> pillars(Credit.Hazard h) {
        LocalDate[] d = Credit.pillarDates(h);
        double[] s = Credit.survivals(h);
        List<Map<String, Object>> out = new ArrayList<>();
        for (int i = 0; i < d.length; i++) {
            out.add(Operations.out("date", d[i].toString(), "survival", s[i]).outputs());
        }
        return out;
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("credit.cds.price", in -> {
            LocalDate t = in.date("trade_date");
            StageB.CurveInput d = StageB.curve(in, "discount");
            HazardInput h = hazard(in);
            double r = in.real("recovery");
            In tr = in.object("trade");
            LocalDate m = tr.date("maturity");
            double coupon = tr.real("coupon");
            double notional = tr.real("notional");
            String side = tr.string("side");
            if (!side.equals("BUY_PROTECTION") && !side.equals("SELL_PROTECTION")) {
                throw new QfError("E_SCHEMA", "unknown side", "side");
            }
            String payout = in.string("payout");
            if (!payout.equals("STANDARD") && !payout.equals("DIGITAL")) {
                throw new QfError("E_SCHEMA", "unknown payout", "payout");
            }
            in.gate();
            Credit.Price p = Credit.price(t, d.build(), h.build(), r, m, coupon, notional,
                    side.equals("BUY_PROTECTION"), payout.equals("DIGITAL"));
            return Operations.out("pv", p.pv(), "upfront", p.upfront(), "accrued", p.accrued(),
                    "par_spread", p.parSpread(), "protection_leg", p.protection(), "rpv01", p.rpv01());
        });
        table.put("credit.cds.bootstrap", in -> {
            LocalDate t = in.date("trade_date");
            StageB.CurveInput d = StageB.curve(in, "discount");
            double r = in.real("recovery");
            Quotes q = quotes(in);
            in.gate();
            return Operations.out("pillars", pillars(Credit.bootstrap(t, d.build(), r, q.tenors(), q.spreads())));
        });
        table.put("credit.index.intrinsic", in -> {
            LocalDate t = in.date("trade_date");
            StageB.CurveInput d = StageB.curve(in, "discount");
            List<In> names = in.objects("names");
            in.limit(names.size() > 1000, "names");
            List<HazardInput> hz = new ArrayList<>();
            double[] rec = new double[names.size()];
            double[] w = new double[rec.length];
            for (int i = 0; i < rec.length; i++) {
                hz.add(hazard(names.get(i)));
                rec[i] = names.get(i).real("recovery");
                w[i] = names.get(i).real("weight");
            }
            In tr = in.object("trade");
            LocalDate m = tr.date("maturity");
            double coupon = tr.real("coupon");
            double quoted = in.real("quoted_upfront");
            in.gate();
            if (rec.length == 0) {
                throw new QfError("E_INPUT", "no names", "names");
            }
            Curve c = d.build();
            double[] u = new double[rec.length];
            double num = 0.0;
            double den = 0.0;
            for (int i = 0; i < u.length; i++) {
                if (!(w[i] >= 0.0)) {
                    throw new QfError("E_DOMAIN", "weights must not be negative", "names");
                }
                u[i] = Credit.price(t, c, hz.get(i).build(), rec[i], m, coupon, 1.0, true, false).upfront();
                num += w[i] * u[i];
                den += w[i];
            }
            if (!(den > 0.0)) {
                throw new QfError("E_INPUT", "weights sum to zero", "names");
            }
            double intrinsic = num / den;
            return Operations.out("intrinsic_upfront", intrinsic, "basis", quoted - intrinsic, "name_upfronts", u);
        });
        table.put("credit.curve.composite", in -> {
            LocalDate t = in.date("trade_date");
            StageB.CurveInput d = StageB.curve(in, "discount");
            double r = in.real("recovery");
            List<In> cons = in.objects("constituents");
            in.limit(cons.size() > 1000, "constituents");
            List<Quotes> qs = new ArrayList<>();
            double[] w = new double[cons.size()];
            for (int i = 0; i < w.length; i++) {
                qs.add(quotes(cons.get(i)));
                w[i] = cons.get(i).real("weight");
            }
            double scale = in.real("scale");
            in.gate();
            if (qs.isEmpty()) {
                throw new QfError("E_INPUT", "no constituents", "constituents");
            }
            String[] tenors = qs.getFirst().tenors();
            for (Quotes q : qs) {
                if (!java.util.Arrays.equals(q.tenors(), tenors)) {
                    throw new QfError("E_INPUT", "constituents differ in tenors", "constituents");
                }
            }
            if (!(scale > 0.0)) {
                throw new QfError("E_DOMAIN", "scale must be positive", "scale");
            }
            double den = 0.0;
            for (double v : w) {
                if (!(v >= 0.0)) {
                    throw new QfError("E_DOMAIN", "weights must not be negative", "constituents");
                }
                den += v;
            }
            if (!(den > 0.0)) {
                throw new QfError("E_INPUT", "weights sum to zero", "constituents");
            }
            double[] s = new double[tenors.length];
            for (int k = 0; k < s.length; k++) {
                double num = 0.0;
                for (int i = 0; i < w.length; i++) {
                    num += w[i] * qs.get(i).spreads()[k];
                }
                s[k] = scale * num / den;
            }
            return Operations.out("spreads", s, "pillars", pillars(Credit.bootstrap(t, d.build(), r, tenors, s)));
        });
    }
}
