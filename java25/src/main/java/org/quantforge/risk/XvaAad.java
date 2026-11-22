package org.quantforge.risk;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Reverse-mode (adjoint) sensitivities of the G-41 valuation adjustments, written by hand
 * (specifications/06-risk/xva-aad-adjustments.md, rulings KR-262 to KR-268). Port of
 * python/quantforge_core/xva_aad.py: the same backward pass, bucket by bucket from the first.
 */
public final class XvaAad {
    private XvaAad() {}

    /** Gradient keys in canonical order (KR-263), before the optional im and capital keys. */
    public static final List<String> BASE_KEYS = List.of("counterparty.hazard_rate", "counterparty.hazard_buckets",
            "counterparty.recovery", "own.hazard_rate", "own.hazard_buckets", "own.recovery", "discount_factors",
            "ee", "ene", "funding.borrow_spread", "funding.lend_spread");

    /** All keys a request may differentiate: the base keys, then im and capital when given. */
    public static List<String> keys(boolean hasIm, boolean hasCapital) {
        List<String> out = new ArrayList<>(BASE_KEYS);
        if (hasIm) {
            out.add("im");
            out.add("im_spread");
        }
        if (hasCapital) {
            out.add("capital");
            out.add("hurdle_rate");
        }
        return out;
    }

    /** The validated G-41 inputs; im and capital are null when absent. */
    public record Request(double[] t, double[] df, double[] ee, double[] ene, double hc, double rc, double hb,
                          double rb, double sb, double sl, boolean excludeOverlap, double[] im, double imSpread,
                          double[] capital, double hurdle) {}

    /** Adjoint accumulators of one output. */
    private static final class Bar {
        final double[] sc;
        final double[] sb;
        final double[] pc;
        final double[] pb;
        final double[] df;
        final double[] ee;
        final double[] ene;
        final double[] prof;
        final double[] hbDirect;
        double rc;
        double rb;
        double spread;

        Bar(int n) {
            sc = new double[n + 1];
            sb = new double[n + 1];
            pc = new double[n];
            pb = new double[n];
            df = new double[n];
            ee = new double[n];
            ene = new double[n];
            prof = new double[n];
            hbDirect = new double[n];
        }
    }

    /** The forward intermediates the backward pass reads. */
    private static final class Tape {
        final int n;
        final double[] t;
        final double[] dt;
        final double[] df;
        final double[] sc;
        final double[] sb;
        final double[] bc;
        final double[] bb;
        final double[] w;

        Tape(Request r) {
            n = r.t().length;
            t = new double[n + 1];
            System.arraycopy(r.t(), 0, t, 1, n);
            dt = new double[n];
            df = r.df();
            sc = new double[n + 1];
            sb = new double[n + 1];
            for (int k = 0; k <= n; k++) {
                sc[k] = Math.exp(-r.hc() * t[k]);
                sb[k] = Math.exp(-r.hb() * t[k]);
            }
            bc = new double[n];
            bb = new double[n];
            w = new double[n];
            for (int i = 0; i < n; i++) {
                dt[i] = r.t()[i] - t[i];
                bc[i] = sc[i] * -Math.expm1(-r.hc() * dt[i]); // cancellation free (PT-6)
                bb[i] = sb[i] * -Math.expm1(-r.hb() * dt[i]);
                w[i] = df[i] * sc[i] * sb[i] * dt[i];
            }
        }

        void throughW(Bar bar, int i, double gw) {
            bar.df[i] += gw * sc[i] * sb[i] * dt[i];
            bar.sc[i] += gw * df[i] * sb[i] * dt[i];
            bar.sb[i] += gw * df[i] * sc[i] * dt[i];
        }
    }

    private static Bar cva(Tape tp, Request r) {
        Bar bar = new Bar(tp.n);
        double lc = 1 - r.rc();
        for (int i = 0; i < tp.n; i++) {
            double b = tp.bc[i];
            double e = r.ee()[i];
            bar.rc -= tp.df[i] * e * b * tp.sb[i];
            bar.df[i] += lc * e * b * tp.sb[i];
            bar.ee[i] += lc * tp.df[i] * b * tp.sb[i];
            bar.pc[i] += lc * tp.df[i] * e * tp.sb[i];
            bar.sb[i] += lc * tp.df[i] * e * b;
        }
        return bar;
    }

    private static Bar dva(Tape tp, Request r) {
        Bar bar = new Bar(tp.n);
        double lb = 1 - r.rb();
        for (int i = 0; i < tp.n; i++) {
            double x = -r.ene()[i];
            double b = tp.bb[i];
            bar.rb -= tp.df[i] * x * b * tp.sc[i];
            bar.df[i] += lb * x * b * tp.sc[i];
            bar.ene[i] -= lb * tp.df[i] * b * tp.sc[i];
            bar.pb[i] += lb * tp.df[i] * x * tp.sc[i];
            bar.sc[i] += lb * tp.df[i] * x * b;
        }
        return bar;
    }

    /** FCA (toEe true), MVA and KVA: coef sum W_i x_i. */
    private static Bar funding(Tape tp, double coef, double[] prof, boolean toEe) {
        Bar bar = new Bar(tp.n);
        double[] target = toEe ? bar.ee : bar.prof;
        for (int i = 0; i < tp.n; i++) {
            target[i] += coef * tp.w[i];
            bar.spread += tp.w[i] * prof[i];
            tp.throughW(bar, i, coef * prof[i]);
        }
        return bar;
    }

    /** FBA; branch 0: no overlap rule, 1: linear branch, -1: the floor (KR-264). */
    private static Bar fba(Tape tp, Request r, int branch) {
        Bar bar = new Bar(tp.n);
        double lb = 1 - r.rb();
        double coef = branch == 0 ? r.sl() : (branch > 0 ? r.sl() - r.hb() * lb : 0.0);
        for (int i = 0; i < tp.n; i++) {
            double x = -r.ene()[i];
            bar.ene[i] -= coef * tp.w[i];
            double g = tp.w[i] * x;
            if (branch >= 0) {
                bar.spread += g;
            }
            if (branch > 0) {
                bar.rb += g * r.hb();
                bar.hbDirect[i] -= g * lb;
            }
            tp.throughW(bar, i, coef * x);
        }
        return bar;
    }

    /** Survival adjoints to hazard adjoints; returns {flat, bucket 0, ..., bucket n-1} (spec, backward pass). */
    static double[] hazards(double[] s, double[] gs, double[] b, double[] gp, double[] t, double[] dt) {
        int n = dt.length;
        double[] out = new double[n + 1];
        double flat = 0.0;
        for (int k = 0; k <= n; k++) {
            flat += gs[k] * t[k] * s[k];
        }
        double pairs = 0.0;
        for (int i = 0; i < n; i++) {
            pairs += gp[i] * (t[i] * b[i] - dt[i] * s[i + 1]);
        }
        out[0] = -flat - pairs;
        double tail = 0.0;
        for (int j = n - 1; j >= 0; j--) {
            tail += gs[j + 1] * s[j + 1];
            out[j + 1] = -dt[j] * (tail - gp[j] * s[j + 1]);
            tail += gp[j] * b[j];
        }
        return out;
    }

    private static double[] tail(double[] h) {
        double[] out = new double[h.length - 1];
        System.arraycopy(h, 1, out, 0, out.length);
        return out;
    }

    private static Map<String, Object> gradient(Tape tp, Bar bar, String spreadKey, String profKey) {
        double[] hc = hazards(tp.sc, bar.sc, tp.bc, bar.pc, tp.t, tp.dt);
        double[] hb = hazards(tp.sb, bar.sb, tp.bb, bar.pb, tp.t, tp.dt);
        double direct = 0.0;
        double[] hbB = tail(hb);
        for (int i = 0; i < tp.n; i++) {
            direct += bar.hbDirect[i];
            hbB[i] += bar.hbDirect[i];
        }
        Map<String, Object> g = new LinkedHashMap<>();
        g.put("counterparty.hazard_rate", hc[0]);
        g.put("counterparty.hazard_buckets", tail(hc));
        g.put("counterparty.recovery", bar.rc);
        g.put("own.hazard_rate", hb[0] + direct);
        g.put("own.hazard_buckets", hbB);
        g.put("own.recovery", bar.rb);
        g.put("discount_factors", bar.df);
        g.put("ee", bar.ee);
        g.put("ene", bar.ene);
        g.put("funding.borrow_spread", 0.0);
        g.put("funding.lend_spread", 0.0);
        g.put("im", new double[tp.n]);
        g.put("im_spread", 0.0);
        g.put("capital", new double[tp.n]);
        g.put("hurdle_rate", 0.0);
        if (spreadKey != null) {
            g.put(spreadKey, bar.spread);
        }
        if (profKey != null) {
            g.put(profKey, bar.prof);
        }
        return g;
    }

    private static Map<String, Object> minus(Map<String, Object> a, Map<String, Object> b) {
        Map<String, Object> out = new LinkedHashMap<>();
        for (Map.Entry<String, Object> e : a.entrySet()) {
            Object y = b.get(e.getKey());
            if (e.getValue() instanceof double[] x) {
                double[] yy = (double[]) y;
                double[] d = new double[x.length];
                for (int i = 0; i < x.length; i++) {
                    d[i] = x[i] - yy[i];
                }
                out.put(e.getKey(), d);
            } else {
                out.put(e.getKey(), (Double) e.getValue() - (Double) y);
            }
        }
        return out;
    }

    /**
     * The gradient of every output of a validated request, restricted to {@code names} (canonical order).
     *
     * @param r the validated request
     * @param names the keys to report, a sub-list of {@link #keys(boolean, boolean)}
     * @return output name to key to derivative (a Double or a double[])
     */
    public static Map<String, Map<String, Object>> gradient(Request r, List<String> names) {
        Tape tp = new Tape(r);
        int branch = !r.excludeOverlap() ? 0 : (r.sl() - r.hb() * (1 - r.rb()) >= 0 ? 1 : -1);
        Map<String, Map<String, Object>> raw = new LinkedHashMap<>();
        raw.put("cva", gradient(tp, cva(tp, r), null, null));
        raw.put("dva", gradient(tp, dva(tp, r), null, null));
        raw.put("fca", gradient(tp, funding(tp, r.sb(), r.ee(), true), "funding.borrow_spread", null));
        raw.put("fba", gradient(tp, fba(tp, r, branch), "funding.lend_spread", null));
        raw.put("fva", minus(raw.get("fca"), raw.get("fba")));
        if (r.im() != null) {
            raw.put("mva", gradient(tp, funding(tp, r.imSpread(), r.im(), false), "im_spread", "im"));
        }
        if (r.capital() != null) {
            raw.put("kva", gradient(tp, funding(tp, r.hurdle(), r.capital(), false), "hurdle_rate", "capital"));
        }
        Map<String, Map<String, Object>> out = new LinkedHashMap<>();
        for (Map.Entry<String, Map<String, Object>> e : raw.entrySet()) {
            Map<String, Object> row = new LinkedHashMap<>();
            for (String k : names) {
                row.put(k, e.getValue().get(k));
            }
            out.put(e.getKey(), row);
        }
        return out;
    }
}
