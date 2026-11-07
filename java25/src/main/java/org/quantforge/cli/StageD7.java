package org.quantforge.cli;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.pricing.CapSwaption;
import org.quantforge.pricing.CmdtyMbs;
import org.quantforge.pricing.Inflation;

/** Stage D wave 3, D7 to D9: caps and swaptions, commodities, MBS. */
final class StageD7 {
    private StageD7() {}

    private static boolean normalModel(In in) {
        String m = in.string("model");
        return switch (m) {
            case "BLACK_76" -> false;
            case "BACHELIER" -> true;
            default -> throw new QfError("E_SCHEMA", "model must be BLACK_76 or BACHELIER", "model");
        };
    }

    private static String choose(In t, String key, String a, String b) {
        String v = t.string(key);
        if (!v.equals(a) && !v.equals(b)) {
            throw new QfError("E_SCHEMA", "unknown " + key, key);
        }
        return v;
    }

    private static CmdtyMbs.Pool pool(In in) {
        In p = in.object("pool");
        double balance = p.real("balance");
        double wac = p.real("wac");
        double net = p.real("net_coupon");
        long wam = p.integer("wam");
        long age = p.integer("age");
        In pre = p.object("prepayment");
        String model = choose(pre, "model", "CPR", "PSA");
        boolean psa = model.equals("PSA");
        double rate = pre.real(psa ? "speed" : "rate");
        return new CmdtyMbs.Pool(balance, wac, net, wam, age, psa, rate);
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("rates.cap.price", in -> {
            StageB.CurveInput d = StageB.curve(in, "discount");
            StageB.CurveInput p = StageB.curve(in, "projection");
            boolean normal = normalModel(in);
            Object v = in.anyValue("vol");
            boolean listed = v instanceof List<?>;
            double[] vols = listed ? in.reals("vol") : new double[] {in.real("vol")};
            In t = in.object("trade");
            boolean cap = choose(t, "type", "CAP", "FLOOR").equals("CAP");
            long start = t.integer("start_months");
            long tenor = t.integer("tenor_months");
            double k = t.real("strike");
            double n = t.real("notional");
            in.gate();
            CapSwaption.Cap r = CapSwaption.cap(d.build(), p.build(), normal, vols, listed, cap, start, tenor, k, n);
            return Operations.out("caplets", r.caplets(), "price", r.price());
        });
        table.put("rates.swaption.price", in -> {
            StageB.CurveInput d = StageB.curve(in, "discount");
            StageB.CurveInput p = StageB.curve(in, "projection");
            boolean normal = normalModel(in);
            double vol = in.real("vol");
            In t = in.object("trade");
            boolean payer = choose(t, "type", "PAYER", "RECEIVER").equals("PAYER");
            long expiry = t.integer("expiry_months");
            long tenor = t.integer("tenor_months");
            double k = t.real("strike");
            double n = t.real("notional");
            in.gate();
            CapSwaption.Swaption r = CapSwaption.swaption(d.build(), p.build(), normal, vol, payer, expiry, tenor, k, n);
            return Operations.out("price", r.price(), "forward_rate", r.forward(), "annuity", r.annuity());
        });
        table.put("cmdty.curve.forward", in -> {
            List<In> q = in.objects("quotes");
            in.limit(q.size() > 1000, "quotes");
            long[] k = new long[q.size()];
            double[] prices = new double[k.length];
            for (int i = 0; i < k.length; i++) {
                k[i] = Inflation.index(StageD6.month(q.get(i).string("month"), "month"));
                prices[i] = q.get(i).real("price");
            }
            Object s = in.anyValue("seasonality");
            double[] season = s == null ? null : in.reals("seasonality");
            List<String> ms = in.strings("months");
            long[] months = new long[ms.size()];
            for (int i = 0; i < months.length; i++) {
                months[i] = Inflation.index(StageD6.month(ms.get(i), "months"));
            }
            in.gate();
            return Operations.out("forwards", CmdtyMbs.forwards(k, prices, season, months));
        });
        table.put("cmdty.storage.carry", in -> {
            StageB.CurveInput f = StageB.curve(in, "funding");
            List<In> fw = in.objects("forwards");
            in.limit(fw.size() > 1000, "forwards");
            LocalDate[] d = new LocalDate[fw.size()];
            double[] p = new double[d.length];
            for (int i = 0; i < d.length; i++) {
                d[i] = fw.get(i).date("date");
                p[i] = fw.get(i).real("price");
            }
            double u = in.real("storage_cost");
            in.gate();
            CmdtyMbs.Carry r = CmdtyMbs.carry(f.build(), d, p, u);
            List<Boolean> arb = new ArrayList<>();
            for (boolean b : r.arbitrage()) {
                arb.add(b);
            }
            return Operations.out("convenience_yields", r.yields(), "carry_values", r.values(), "arbitrage", arb);
        });
        table.put("mbs.cashflows", in -> {
            CmdtyMbs.Pool p = pool(in);
            in.gate();
            CmdtyMbs.Flows f = CmdtyMbs.cashflows(p);
            return Operations.out("balance", f.balance(), "interest", f.interest(),
                    "scheduled_principal", f.scheduled(), "prepayment", f.prepayment(), "wal", f.wal());
        });
        table.put("mbs.price", in -> {
            CmdtyMbs.Pool p = pool(in);
            double y = in.real("yield");
            long delay = in.integer("delay_days");
            in.gate();
            CmdtyMbs.Price r = CmdtyMbs.price(p, y, delay);
            return Operations.out("price", r.price(), "modified_duration", r.duration(), "wal", r.wal());
        });
    }
}
