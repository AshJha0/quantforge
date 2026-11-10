package org.quantforge.risk;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeMap;
import org.quantforge.core.Finite;
import org.quantforge.core.QfError;

/** FRTB-SA GIRR delta under MAR21 (frtb-sa-girr.md, ruling F-33). */
public final class FrtbGirr {
    private FrtbGirr() {}

    public record Sensitivity(String currency, String curve, String riskFactor, double value) {}

    public record Bucket(String currency, double k, double s, double sUsed) {}

    public record Scenario(String name, List<Bucket> buckets, double delta, boolean alternativeUsed) {}

    public record Result(List<Scenario> scenarios, double capital, String binding) {}

    private static final String[] TENORS = {"0.25Y", "0.5Y", "1Y", "2Y", "3Y", "5Y", "10Y", "15Y", "20Y", "30Y"};
    private static final double[] YEARS = {0.25, 0.5, 1, 2, 3, 5, 10, 15, 20, 30};
    private static final double[] RW = {0.017, 0.017, 0.016, 0.013, 0.012, 0.011, 0.011, 0.011, 0.011, 0.011};
    private static final Set<String> REDUCED = Set.of("EUR", "USD", "GBP", "AUD", "JPY", "SEK", "CAD");

    /** Index of a tenor, -1 for INFLATION, -2 for XCCY_BASIS; else E_SCHEMA. */
    public static int factor(String rf) {
        for (int i = 0; i < TENORS.length; i++) {
            if (TENORS[i].equals(rf)) {
                return i;
            }
        }
        if (rf.equals("INFLATION")) {
            return -1;
        }
        if (rf.equals("XCCY_BASIS")) {
            return -2;
        }
        throw new QfError("E_SCHEMA", "unknown risk_factor " + rf, "risk_factor");
    }

    private static double rho(Sensitivity a, int fa, Sensitivity b, int fb) {
        if (fa == -2 || fb == -2) {
            return 0.0;
        }
        boolean sameCurve = a.curve().equals(b.curve());
        if (fa == -1 && fb == -1) {
            return sameCurve ? 1.0 : 0.999;
        }
        if (fa == -1 || fb == -1) {
            return 0.4;
        }
        double ta = YEARS[fa];
        double tb = YEARS[fb];
        double r = Math.max(Math.exp(-0.03 * Math.abs(ta - tb) / Math.min(ta, tb)), 0.4);
        return sameCurve ? r : r * 0.999;
    }

    private static double scale(String scenario, double x) {
        return switch (scenario) {
            case "high" -> Math.min(1.25 * x, 1.0);
            case "low" -> Math.max(2.0 * x - 1.0, 0.75 * x);
            default -> x;
        };
    }

    public static Result delta(List<Sensitivity> in, boolean reduction, String reporting) {
        if (in.isEmpty()) {
            throw new QfError("E_INPUT", "no sensitivities", "sensitivities");
        }
        Set<String> keys = new HashSet<>();
        TreeMap<String, List<Integer>> buckets = new TreeMap<>();
        int[] f = new int[in.size()];
        double[] ws = new double[in.size()];
        for (int i = 0; i < in.size(); i++) {
            Sensitivity s = in.get(i);
            Finite.check("sensitivity", s.value());
            f[i] = factor(s.riskFactor());
            if (!keys.add(s.currency() + "\u0000" + s.curve() + "\u0000" + s.riskFactor())) {
                throw new QfError("E_INPUT", "duplicate sensitivity", "sensitivities");
            }
            double rw = f[i] >= 0 ? RW[f[i]] : 0.016;
            if (reduction && (REDUCED.contains(s.currency()) || s.currency().equals(reporting))) {
                rw /= Math.sqrt(2.0);
            }
            ws[i] = rw * s.value();
            buckets.computeIfAbsent(s.currency(), k -> new ArrayList<>()).add(i);
        }
        List<Scenario> scenarios = new ArrayList<>();
        double capital = Double.NEGATIVE_INFINITY;
        String binding = null;
        for (String sc : new String[] {"high", "medium", "low"}) {
            List<String> ccy = new ArrayList<>(buckets.keySet());
            int nb = ccy.size();
            double[] k = new double[nb];
            double[] s = new double[nb];
            for (int b = 0; b < nb; b++) {
                List<Integer> idx = buckets.get(ccy.get(b));
                double sum = 0.0;
                double sb = 0.0;
                for (int x : idx) {
                    sb += ws[x];
                    for (int y : idx) {
                        double r = x == y ? 1.0 : scale(sc, rho(in.get(x), f[x], in.get(y), f[y]));
                        sum += r * ws[x] * ws[y];
                    }
                }
                k[b] = Math.sqrt(Math.max(0.0, sum));
                s[b] = sb;
            }
            double g = scale(sc, 0.5);
            double[] used = s.clone();
            double total = aggregate(k, used, g);
            boolean alt = false;
            if (total < 0.0) {
                alt = true;
                for (int b = 0; b < nb; b++) {
                    used[b] = Math.max(Math.min(s[b], k[b]), -k[b]);
                }
                total = Math.max(0.0, aggregate(k, used, g));
            }
            double d = Math.sqrt(total);
            List<Bucket> bl = new ArrayList<>();
            for (int b = 0; b < nb; b++) {
                bl.add(new Bucket(ccy.get(b), k[b], s[b], used[b]));
            }
            scenarios.add(new Scenario(sc, bl, d, alt));
            if (d > capital) {
                capital = d;
                binding = sc;
            }
        }
        return new Result(scenarios, capital, binding);
    }

    private static double aggregate(double[] k, double[] s, double g) {
        double t = 0.0;
        for (int b = 0; b < k.length; b++) {
            t += k[b] * k[b];
            for (int c = 0; c < k.length; c++) {
                if (c != b) {
                    t += g * s[b] * s[c];
                }
            }
        }
        return t;
    }
}
