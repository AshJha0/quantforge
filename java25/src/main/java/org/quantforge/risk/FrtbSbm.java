package org.quantforge.risk;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import org.quantforge.core.QfError;

/**
 * FRTB standardised approach delta for the FX, equity, CSR and commodity classes (frtb-sa-fx-equity.md, rulings
 * G-48, G-49): one MAR21.4 aggregation with the MAR21.6 scenarios, fed by per-class risk weights and correlations.
 */
public final class FrtbSbm {
    private FrtbSbm() {}

    /**
     * One weighted sensitivity.
     *
     * @param bucket bucket number (FX: index of the pair)
     * @param factor risk-factor key, compared for equality in the correlation rules
     * @param ws weighted sensitivity
     */
    public record Ws(int bucket, List<String> factor, double ws) {}

    /** Intra-bucket correlation of two distinct factors in a bucket. */
    @FunctionalInterface
    public interface Rho {
        /**
         * The base correlation.
         *
         * @param bucket the bucket
         * @param a first factor
         * @param b second factor
         * @return the correlation
         */
        double of(int bucket, List<String> a, List<String> b);
    }

    /** Cross-bucket correlation. */
    @FunctionalInterface
    public interface Gamma {
        /**
         * The base correlation.
         *
         * @param b first bucket
         * @param c second bucket
         * @return the correlation
         */
        double of(int b, int c);
    }

    private static double scale(String scenario, double x) {
        return switch (scenario) {
            case "high" -> Math.min(1.25 * x, 1.0);
            case "low" -> Math.max(2.0 * x - 1.0, 0.75 * x);
            default -> x;
        };
    }

    /**
     * MAR21.4 aggregation in the three MAR21.6 scenarios; buckets in ascending number. Buckets listed in
     * {@code simple} take {@code K} as the sum of absolute net weighted sensitivities per factor (MAR21.56, 21.79).
     *
     * @param in weighted sensitivities
     * @param names display name per bucket number (null: the number)
     * @param rho intra-bucket correlation
     * @param gamma cross-bucket correlation
     * @param simple other-sector buckets
     * @return the result in the shape of {@link FrtbGirr.Result}
     */
    public static FrtbGirr.Result aggregate(List<Ws> in, Map<Integer, String> names, Rho rho, Gamma gamma,
                                            Set<Integer> simple) {
        if (in.isEmpty()) {
            throw new QfError("E_INPUT", "no sensitivities", "sensitivities");
        }
        TreeMap<Integer, List<Ws>> buckets = new TreeMap<>();
        for (Ws w : in) {
            buckets.computeIfAbsent(w.bucket(), k -> new ArrayList<>()).add(w);
        }
        List<Integer> ids = new ArrayList<>(buckets.keySet());
        int nb = ids.size();
        List<FrtbGirr.Scenario> out = new ArrayList<>();
        double capital = Double.NEGATIVE_INFINITY;
        String binding = null;
        for (String sc : new String[] {"high", "medium", "low"}) {
            double[] k = new double[nb];
            double[] s = new double[nb];
            for (int b = 0; b < nb; b++) {
                List<Ws> ws = buckets.get(ids.get(b));
                double sb = 0.0;
                for (Ws w : ws) {
                    sb += w.ws();
                }
                s[b] = sb;
                if (simple.contains(ids.get(b))) {
                    Map<List<String>, Double> net = new HashMap<>();
                    for (Ws w : ws) {
                        net.merge(w.factor(), w.ws(), Double::sum);
                    }
                    double sum = 0.0;
                    for (Ws w : ws) {
                        Double v = net.remove(w.factor());
                        if (v != null) {
                            sum += Math.abs(v);
                        }
                    }
                    k[b] = sum;
                    continue;
                }
                double q = 0.0;
                for (int i = 0; i < ws.size(); i++) {
                    for (int j = 0; j < ws.size(); j++) {
                        double r = i == j ? 1.0 : scale(sc, rho.of(ids.get(b), ws.get(i).factor(), ws.get(j).factor()));
                        q += ws.get(i).ws() * ws.get(j).ws() * r;
                    }
                }
                k[b] = Math.sqrt(Math.max(q, 0.0));
            }
            double[] used = s.clone();
            double total = total(k, used, ids, gamma, sc);
            boolean alt = false;
            if (total < 0.0) {
                alt = true;
                for (int b = 0; b < nb; b++) {
                    used[b] = Math.max(Math.min(s[b], k[b]), -k[b]);
                }
                total = total(k, used, ids, gamma, sc);
            }
            double d = Math.sqrt(Math.max(total, 0.0));
            List<FrtbGirr.Bucket> bl = new ArrayList<>();
            for (int b = 0; b < nb; b++) {
                String nm = names == null ? Integer.toString(ids.get(b)) : names.get(ids.get(b));
                bl.add(new FrtbGirr.Bucket(nm, k[b], s[b], used[b]));
            }
            out.add(new FrtbGirr.Scenario(sc, bl, d, alt));
            if (d > capital) {
                capital = d;
                binding = sc;
            }
        }
        return new FrtbGirr.Result(out, capital, binding);
    }

    private static double total(double[] k, double[] s, List<Integer> ids, Gamma gamma, String sc) {
        double t = 0.0;
        for (int b = 0; b < k.length; b++) {
            t += k[b] * k[b];
        }
        for (int b = 0; b < k.length; b++) {
            for (int c = 0; c < k.length; c++) {
                if (b != c) {
                    t += scale(sc, gamma.of(ids.get(b), ids.get(c))) * s[b] * s[c];
                }
            }
        }
        return t;
    }

    private static final double[] EQ_RW = {0, 0.55, 0.60, 0.45, 0.55, 0.30, 0.35, 0.40, 0.50, 0.70, 0.50, 0.70, 0.15,
        0.25};
    static final double[] EQ_RHO = {0, 0.15, 0.15, 0.15, 0.15, 0.25, 0.25, 0.25, 0.25, 0.075, 0.125, 0, 0.80,
        0.80};
    private static final double[] CSR_RW = {0, 0.005, 0.01, 0.05, 0.03, 0.03, 0.02, 0.015, 0.025, 0.02, 0.04, 0.12,
        0.07, 0.085, 0.055, 0.05, 0.12, 0.015, 0.05};
    private static final int[][] T5 = {{-1, 75, 10, 20, 25, 20, 15, 10, 0, 45, 45},
        {75, -1, 5, 15, 20, 15, 10, 10, 0, 45, 45}, {10, 5, -1, 5, 15, 20, 5, 20, 0, 45, 45},
        {20, 15, 5, -1, 20, 25, 5, 5, 0, 45, 45}, {25, 20, 15, 20, -1, 25, 5, 15, 0, 45, 45},
        {20, 15, 20, 25, 25, -1, 5, 20, 0, 45, 45}, {15, 10, 5, 5, 5, 5, -1, 5, 0, 45, 45},
        {10, 10, 20, 5, 15, 20, 5, -1, 0, 45, 45}, {0, 0, 0, 0, 0, 0, 0, 0, -1, 0, 0},
        {45, 45, 45, 45, 45, 45, 45, 45, 0, -1, 75}, {45, 45, 45, 45, 45, 45, 45, 45, 0, 75, -1}};
    private static final double[] CM_RW = {0, 0.30, 0.35, 0.60, 0.80, 0.40, 0.45, 0.20, 0.35, 0.25, 0.35, 0.50};
    static final double[] CM_RHO = {0, 0.55, 0.95, 0.40, 0.80, 0.60, 0.65, 0.55, 0.45, 0.15, 0.40, 0.15};
    private static final Set<String> CSR_TENORS = Set.of("0.5Y", "1Y", "3Y", "5Y", "10Y");

    private static QfError input(String why) {
        return new QfError("E_INPUT", why, "sensitivities");
    }

    /**
     * FX delta (MAR21.86 to 21.89).
     *
     * @param pairs currency pairs
     * @param s sensitivities
     * @param specified pairs under MAR21.88
     * @return the result
     */
    public static FrtbGirr.Result fx(List<String> pairs, double[] s, Set<String> specified) {
        TreeMap<String, Integer> idx = new TreeMap<>();
        for (String p : pairs) {
            if (idx.put(p, 0) != null) {
                throw input("pair twice");
            }
        }
        int n = 0;
        for (String p : idx.keySet()) {
            idx.put(p, n++);
        }
        List<Ws> ws = new ArrayList<>();
        Map<Integer, String> names = new HashMap<>();
        for (int i = 0; i < pairs.size(); i++) {
            double rw = specified.contains(pairs.get(i)) ? 0.15 / Math.sqrt(2.0) : 0.15;
            int b = idx.get(pairs.get(i));
            names.put(b, pairs.get(i));
            ws.add(new Ws(b, List.of("FX"), rw * s[i]));
        }
        return aggregate(ws, names, (b, x, y) -> 1.0, (b, c) -> 0.60, Set.of());
    }

    /**
     * Equity delta (MAR21.77 to 21.80).
     *
     * @param issuer issuers
     * @param bucket buckets 1 to 13
     * @param kind SPOT or REPO
     * @param s sensitivities
     * @return the result
     */
    public static FrtbGirr.Result equity(List<String> issuer, long[] bucket, List<String> kind, double[] s) {
        List<Ws> ws = new ArrayList<>();
        Set<List<String>> seen = new HashSet<>();
        for (int i = 0; i < s.length; i++) {
            long b = bucket[i];
            if (b < 1 || b > 13) {
                throw input("unknown equity bucket");
            }
            String k = kind.get(i);
            if (!k.equals("SPOT") && !k.equals("REPO")) {
                throw input("unknown kind");
            }
            List<String> f = List.of(issuer.get(i), k);
            if (!seen.add(List.of(Long.toString(b), issuer.get(i), k))) {
                throw input("same factor twice");
            }
            double rw = EQ_RW[(int) b] / (k.equals("REPO") ? 100.0 : 1.0);
            ws.add(new Ws((int) b, f, rw * s[i]));
        }
        return aggregate(ws, null, (b, x, y) -> {
            if (x.get(0).equals(y.get(0))) {
                return 0.999;
            }
            double r = EQ_RHO[b];
            return x.get(1).equals(y.get(1)) ? r : r * 0.999;
        }, FrtbSbm::eqGamma, Set.of(11));
    }

    private static int sector(int b) {
        if (b >= 16) {
            return b - 8;
        }
        return b == 8 ? 7 : (b - 1) % 8;
    }

    /**
     * CSR non-securitisation delta (MAR21.51 to 21.57).
     *
     * @param issuer issuers
     * @param bucket buckets 1 to 18
     * @param tenor tenors
     * @param curve BOND or CDS
     * @param s sensitivities
     * @return the result
     */
    public static FrtbGirr.Result csr(List<String> issuer, long[] bucket, List<String> tenor, List<String> curve,
                                      double[] s) {
        List<Ws> ws = new ArrayList<>();
        for (int i = 0; i < s.length; i++) {
            long b = bucket[i];
            if (b < 1 || b > 18) {
                throw input("unknown CSR bucket");
            }
            if (!CSR_TENORS.contains(tenor.get(i))) {
                throw input("unknown CSR tenor");
            }
            if (!curve.get(i).equals("BOND") && !curve.get(i).equals("CDS")) {
                throw input("unknown CSR curve");
            }
            ws.add(new Ws((int) b, List.of(issuer.get(i), tenor.get(i), curve.get(i)), CSR_RW[(int) b] * s[i]));
        }
        return aggregate(ws, null, (b, x, y) -> {
            double name = x.get(0).equals(y.get(0)) ? 1.0 : (b == 17 || b == 18 ? 0.80 : 0.35);
            double ten = x.get(1).equals(y.get(1)) ? 1.0 : 0.65;
            double basis = x.get(2).equals(y.get(2)) ? 1.0 : 0.999;
            return name * ten * basis;
        }, FrtbSbm::csrGamma, Set.of(16));
    }

    /**
     * Commodity delta (MAR21.82 to 21.85).
     *
     * @param cty commodities
     * @param bucket buckets 1 to 11
     * @param tenor tenors
     * @param location delivery locations
     * @param s sensitivities
     * @return the result
     */
    public static FrtbGirr.Result commodity(List<String> cty, long[] bucket, List<String> tenor,
                                            List<String> location, double[] s) {
        List<Ws> ws = new ArrayList<>();
        for (int i = 0; i < s.length; i++) {
            long b = bucket[i];
            if (b < 1 || b > 11) {
                throw input("unknown commodity bucket");
            }
            ws.add(new Ws((int) b, List.of(cty.get(i), tenor.get(i), location.get(i)), CM_RW[(int) b] * s[i]));
        }
        return aggregate(ws, null, (b, x, y) -> {
            double name = x.get(0).equals(y.get(0)) ? 1.0 : CM_RHO[b];
            double ten = x.get(1).equals(y.get(1)) ? 1.0 : 0.99;
            double loc = x.get(2).equals(y.get(2)) ? 1.0 : 0.999;
            return name * ten * loc;
        }, (b, c) -> b == 11 || c == 11 ? 0.0 : 0.20, Set.of());
    }

    /** Equity cross-bucket correlation (MAR21.80). */
    static double eqGamma(int b, int c) {
        if (b == 11 || c == 11) {
            return 0.0;
        }
        if (b <= 10 && c <= 10) {
            return 0.15;
        }
        return (b == 12 && c == 13) || (b == 13 && c == 12) ? 0.75 : 0.45;
    }

    /** CSR cross-bucket correlation, rating times sector (MAR21.57). */
    static double csrGamma(int b, int c) {
        int sb = sector(b);
        int scc = sector(c);
        double sec = sb == scc ? 1.0 : T5[sb][scc] / 100.0;
        double rating = b <= 15 && c <= 15 && (b <= 8) != (c <= 8) ? 0.5 : 1.0;
        return rating * sec;
    }
}
