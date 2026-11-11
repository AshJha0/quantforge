package org.quantforge.cli;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.risk.Xva;

/** Stage G wave 4b: the deterministic xVA layer (xva-framework.md). */
final class OpsXva {
    private OpsXva() {}

    private static final int MAX = 10_000;

    private static QfError domain(String key) {
        return new QfError("E_DOMAIN", key + " is out of range", key);
    }

    private static QfError input(String key) {
        return new QfError("E_INPUT", key + " is not valid", key);
    }

    private static void sameLength(String key, int n, double[]... xs) {
        for (double[] x : xs) {
            if (x.length != n) {
                throw input(key);
            }
        }
    }

    /** Raw CSA inputs, checked after the gate. */
    private record RawCsa(double hr, double hp, double mta, long mpor, double ia) {}

    static void register(Map<String, Function<In, Out>> table) {
        table.put("xva.exposure.collateralised", OpsXva::collateralised);
        table.put("xva.adjustments.value", OpsXva::adjustments);
        table.put("xva.simm.ir_delta", in -> {
            double[] s = in.reals("sensitivities");
            double[] rw = in.reals("risk_weights");
            double[][] rho = in.anyMatrix("correlations");
            double thr = in.real("concentration_threshold");
            in.limit(s.length > MAX, "sensitivities");
            in.gate();
            boolean ok = rw.length == s.length && rho.length == s.length;
            for (double[] row : rho) {
                ok &= row.length == s.length;
            }
            if (!ok) {
                throw input("correlations");
            }
            for (double x : rw) {
                if (!(x >= 0.0)) {
                    throw domain("risk_weights");
                }
            }
            for (double[] row : rho) {
                for (double x : row) {
                    if (!(x >= -1.0 && x <= 1.0)) {
                        throw domain("correlations");
                    }
                }
            }
            if (!(thr > 0.0)) {
                throw domain("concentration_threshold");
            }
            double[] ws = new double[s.length];
            double[] r = Xva.simm(s, rw, rho, thr, ws);
            return Operations.out("weighted_sensitivities", ws, "concentration_factor", r[0], "margin", r[1]);
        });
        table.put("xva.wwr.cva_hw", in -> {
            double[] t = in.reals("times");
            double[][] v = in.anyMatrix("values");
            double[] df = in.reals("discount_factors");
            double h = in.real("hazard_rate");
            double r = in.real("recovery");
            double b = in.real("wwr_b");
            in.limit(t.length > MAX, "times");
            in.limit(v.length > 1_000_000, "values");
            in.gate();
            Xva.checkGrid("times", t, 1);
            if (!(t[0] > 0.0)) {
                throw domain("times");
            }
            sameLength("discount_factors", t.length, df);
            if (v.length == 0) {
                throw input("values");
            }
            sameLength("values", t.length, v);
            if (!(h > 0.0)) {
                throw domain("hazard_rate");
            }
            if (!(r >= 0.0 && r < 1.0)) {
                throw domain("recovery");
            }
            double[] a = new double[t.length];
            double cva = Xva.wwrCva(t, v, df, h, r, b, a);
            return Operations.out("cva", cva, "a", a);
        });
    }

    private static Out collateralised(In in) {
        double[] t = in.reals("times");
        List<In> trades = in.objects("trades");
        in.limit(t.length > MAX, "times");
        in.limit(trades.size() > MAX, "trades");
        List<String> set = new ArrayList<>();
        List<double[][]> vals = new ArrayList<>();
        for (In x : trades) {
            set.add(x.string("netting_set"));
            vals.add(x.anyMatrix("values"));
        }
        Map<String, RawCsa> csa = new TreeMap<>();
        if (in.has("csa")) {
            In c = in.object("csa");
            for (String k : c.keys()) {
                In x = c.object(k);
                csa.put(k, new RawCsa(x.real("threshold_receive"), x.real("threshold_post"),
                        x.real("minimum_transfer_amount"), x.integer("mpor_steps"), x.real("independent_amount", 0.0)));
            }
        }
        double q = in.real("pfe_quantile");
        in.gate();
        Xva.checkGrid("times", t, 2);
        if (trades.isEmpty()) {
            throw input("trades");
        }
        TreeMap<String, double[][]> net = new TreeMap<>();
        for (int i = 0; i < set.size(); i++) {
            double[][] v = vals.get(i);
            if (v.length == 0) {
                throw input("values");
            }
            sameLength("values", t.length, v);
            double[][] cur = net.get(set.get(i));
            if (cur == null) {
                cur = new double[v.length][t.length];
                net.put(set.get(i), cur);
            }
            if (cur.length != v.length) {
                throw input("values");
            }
            for (int p = 0; p < v.length; p++) {
                for (int j = 0; j < t.length; j++) {
                    cur[p][j] += v[p][j];
                }
            }
        }
        for (Map.Entry<String, RawCsa> e : csa.entrySet()) {
            RawCsa c = e.getValue();
            if (!(c.hr() >= 0.0) || !(c.hp() >= 0.0) || !(c.mta() >= 0.0)) {
                throw domain("csa");
            }
            if (c.mpor() < 0) {
                throw domain("mpor_steps");
            }
            if (!net.containsKey(e.getKey())) {
                throw input("csa");
            }
        }
        if (!(q > 0.0 && q <= 1.0)) {
            throw domain("pfe_quantile");
        }
        Map<String, Object> sets = new LinkedHashMap<>();
        double[] total = new double[t.length];
        for (Map.Entry<String, double[][]> e : net.entrySet()) {
            RawCsa c = csa.get(e.getKey());
            Xva.Csa terms = c == null ? null
                    : new Xva.Csa(c.hr(), c.hp(), c.mta(), (int) Math.min(c.mpor(), Integer.MAX_VALUE), c.ia());
            Xva.Profile pr = Xva.profile(t, e.getValue(), terms, q);
            for (int i = 0; i < t.length; i++) {
                total[i] += pr.ee()[i];
            }
            sets.put(e.getKey(), Operations.out("ee", pr.ee(), "ene", pr.ene(), "pfe", pr.pfe(), "epe", pr.epe(),
                    "effective_epe", pr.effectiveEpe()).outputs());
        }
        return Operations.out("netting_sets", sets, "total_ee", total);
    }

    private static Out adjustments(In in) {
        double[] t = in.reals("times");
        double[] df = in.reals("discount_factors");
        double[] ee = in.reals("ee");
        double[] ene = in.reals("ene");
        In cp = in.object("counterparty");
        double hc = cp.real("hazard_rate");
        double rc = cp.real("recovery");
        In own = in.object("own");
        double hb = own.real("hazard_rate");
        double rb = own.real("recovery");
        In f = in.object("funding");
        double sb = f.real("borrow_spread");
        double sl = f.real("lend_spread");
        boolean excl = f.bool("exclude_dva_overlap");
        boolean hasIm = in.has("im");
        boolean hasImS = in.has("im_spread");
        boolean hasCap = in.has("capital");
        boolean hasHur = in.has("hurdle_rate");
        double[] im = hasIm ? in.reals("im") : null;
        double ims = hasImS ? in.real("im_spread") : 0.0;
        double[] cap = hasCap ? in.reals("capital") : null;
        double hur = hasHur ? in.real("hurdle_rate") : 0.0;
        in.limit(t.length > MAX, "times");
        in.gate();
        Xva.checkGrid("times", t, 1);
        if (!(t[0] > 0.0)) {
            throw domain("times");
        }
        sameLength("ee", t.length, df, ee, ene);
        if (hasIm != hasImS) {
            throw input("im_spread");
        }
        if (hasCap != hasHur) {
            throw input("hurdle_rate");
        }
        if (hasIm) {
            sameLength("im", t.length, im);
        }
        if (hasCap) {
            sameLength("capital", t.length, cap);
        }
        for (int i = 0; i < t.length; i++) {
            if (!(ee[i] >= 0.0)) {
                throw domain("ee");
            }
            if (!(ene[i] <= 0.0)) {
                throw domain("ene");
            }
        }
        if (!(hc >= 0.0) || !(hb >= 0.0)) {
            throw domain("hazard_rate");
        }
        if (!(rc >= 0.0 && rc < 1.0) || !(rb >= 0.0 && rb < 1.0)) {
            throw domain("recovery");
        }
        double[] r = Xva.adjustments(t, df, ee, ene, hc, rc, hb, rb, sb, sl, excl, im, ims, cap, hur);
        Out o = Operations.out("cva", r[0], "dva", r[1], "fca", r[2], "fba", r[3], "fva", r[4]);
        if (hasIm) {
            o.outputs().put("mva", r[5]);
        }
        if (hasCap) {
            o.outputs().put("kva", r[6]);
        }
        return o;
    }
}
