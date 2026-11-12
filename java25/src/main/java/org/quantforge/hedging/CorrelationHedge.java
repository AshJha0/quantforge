package org.quantforge.hedging;

import java.util.List;
import java.util.Map;
import java.util.Set;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/**
 * {@code hedge.correlation.neutralise} ({@code 08-hedging/credit-and-correlation-hedges.md}): quantities of exchange
 * options [M78], single-asset vanillas and the two underlyings that set chosen Greeks of a two-asset book to zero.
 * Greeks are, in order, {@code delta_1}, {@code delta_2}, {@code vega_1}, {@code vega_2} (per unit volatility) and
 * {@code correlation01} (per 0.01 of correlation, ruling I-18).
 */
public final class CorrelationHedge {
    private CorrelationHedge() {}

    /** Instrument kinds and the keys each one carries besides {@code instrument} and a book's {@code quantity}. */
    public enum Kind {
        /** Receive {@code quantity1 S1} for {@code quantity2 S2} at expiry. */
        EXCHANGE(Set.of("quantity1", "quantity2", "expiry_years")),
        /** Black-Scholes-Merton call on asset 1. */
        CALL_1(Set.of("strike", "expiry_years")),
        /** Black-Scholes-Merton put on asset 1. */
        PUT_1(Set.of("strike", "expiry_years")),
        /** Black-Scholes-Merton call on asset 2. */
        CALL_2(Set.of("strike", "expiry_years")),
        /** Black-Scholes-Merton put on asset 2. */
        PUT_2(Set.of("strike", "expiry_years")),
        /** Asset 1 itself. */
        UNDERLYING_1(Set.of()),
        /** Asset 2 itself. */
        UNDERLYING_2(Set.of());

        private final Set<String> keys;

        Kind(Set<String> keys) {
            this.keys = keys;
        }

        /**
         * The keys this kind carries.
         *
         * @return the key names
         */
        public Set<String> keys() {
            return keys;
        }
    }

    /** A Greek that can be targeted, in the order of the Greek vectors. */
    public enum Target {
        /** Delta to asset 1. */
        DELTA_1,
        /** Delta to asset 2. */
        DELTA_2,
        /** Vega to asset 1's volatility. */
        VEGA_1,
        /** Vega to asset 2's volatility. */
        VEGA_2,
        /** Correlation sensitivity per 0.01. */
        CORRELATION
    }

    /**
     * An instrument as read: its kind, its numeric keys and whether any other key was present.
     *
     * @param kind the instrument kind
     * @param values numeric keys other than {@code instrument}, {@code quantity} included for a book position
     * @param unknownKey true when a key outside every kind's set was present
     */
    public record Instrument(Kind kind, Map<String, Double> values, boolean unknownKey) {
        double get(String key) {
            return values.get(key);
        }
    }

    /**
     * The two-asset market.
     *
     * @param spot1 spot of asset 1
     * @param spot2 spot of asset 2
     * @param rate continuously compounded rate
     * @param yield1 continuous yield of asset 1
     * @param yield2 continuous yield of asset 2
     * @param vol1 volatility of asset 1
     * @param vol2 volatility of asset 2
     * @param correlation correlation of the two log returns
     */
    public record Market(double spot1, double spot2, double rate, double yield1, double yield2, double vol1,
            double vol2, double correlation) {
        double spreadVol() {
            return Math.sqrt(Math.max(0.0, vol1 * vol1 + vol2 * vol2 - 2.0 * correlation * vol1 * vol2));
        }
    }

    /**
     * The answer.
     *
     * @param quantities units of each hedge instrument
     * @param before the book's five Greeks
     * @param after the same after the hedge
     */
    public record Result(double[] quantities, double[] before, double[] after) {}

    private static QfError input(String key, String why) {
        return new QfError("E_INPUT", key + ": " + why, key);
    }

    private static QfError domain(String key) {
        return new QfError("E_DOMAIN", key + " is out of range", key);
    }

    /** The five per-unit Greeks of one instrument. */
    static double[] greeks(Market mk, Instrument in) {
        double[] g = new double[5];
        switch (in.kind()) {
            case UNDERLYING_1 -> g[0] = 1.0;
            case UNDERLYING_2 -> g[1] = 1.0;
            case EXCHANGE -> {
                double t = in.get("expiry_years");
                double sq = Math.sqrt(t);
                double s = mk.spreadVol();
                double a1 = in.get("quantity1") * Math.exp(-mk.yield1() * t);
                double a2 = in.get("quantity2") * Math.exp(-mk.yield2() * t);
                double f1 = a1 * mk.spot1();
                double f2 = a2 * mk.spot2();
                double d1 = (Math.log(f1 / f2) + 0.5 * s * s * t) / (s * sq);
                double d2 = d1 - s * sq;
                double dvds = f1 * Normal.pdf(d1) * sq;
                g[0] = a1 * Normal.cdf(d1);
                g[1] = -a2 * Normal.cdf(d2);
                g[2] = dvds * (mk.vol1() - mk.correlation() * mk.vol2()) / s;
                g[3] = dvds * (mk.vol2() - mk.correlation() * mk.vol1()) / s;
                g[4] = dvds * (-mk.vol1() * mk.vol2() / s) * 0.01;
            }
            default -> {
                boolean first = in.kind() == Kind.CALL_1 || in.kind() == Kind.PUT_1;
                boolean call = in.kind() == Kind.CALL_1 || in.kind() == Kind.CALL_2;
                double spot = first ? mk.spot1() : mk.spot2();
                double q = first ? mk.yield1() : mk.yield2();
                double v = first ? mk.vol1() : mk.vol2();
                double t = in.get("expiry_years");
                double sq = Math.sqrt(t);
                double d1 = (Math.log(spot / in.get("strike")) + (mk.rate() - q + 0.5 * v * v) * t) / (v * sq);
                double dq = Math.exp(-q * t);
                int at = first ? 0 : 1;
                g[at] = call ? dq * Normal.cdf(d1) : -dq * Normal.cdf(-d1);
                g[at + 2] = spot * dq * Normal.pdf(d1) * sq;
            }
        }
        return g;
    }

    private static void checkKeys(Instrument in, boolean book, String where) {
        int expected = in.kind().keys().size() + (book ? 1 : 0);
        boolean ok = !in.unknownKey() && in.values().size() == expected && in.values().keySet().stream()
                .allMatch(k -> in.kind().keys().contains(k) || (book && k.equals("quantity")));
        if (!ok) {
            throw input(where, "keys do not fit " + in.kind());
        }
    }

    private static void checkDomain(Instrument in) {
        for (String k : List.of("quantity1", "quantity2", "strike", "expiry_years")) {
            if (in.values().containsKey(k) && !(in.get(k) > 0.0)) {
                throw domain(k);
            }
        }
    }

    /**
     * Solves the hedge.
     *
     * @param mk the market
     * @param book the positions to hedge, each with {@code quantity}
     * @param hedges the hedge instruments, as many as targets
     * @param targets distinct Greeks to set to zero
     * @return the quantities and the Greeks before and after
     * @throws QfError {@code E_INPUT}, {@code E_DOMAIN} or {@code E_SINGULAR}, in the specification's order
     */
    public static Result solve(Market mk, List<Instrument> book, List<Instrument> hedges, List<Target> targets) {
        for (Instrument in : book) {
            checkKeys(in, true, "book");
        }
        for (Instrument in : hedges) {
            checkKeys(in, false, "hedges");
        }
        if (hedges.isEmpty()) {
            throw input("hedges", "no hedge instruments");
        }
        if (targets.size() != hedges.size()) {
            throw input("targets", "one target per hedge instrument");
        }
        if (targets.stream().distinct().count() != targets.size()) {
            throw input("targets", "a repeated target");
        }
        if (!(mk.spot1() > 0.0)) {
            throw domain("spot1");
        }
        if (!(mk.spot2() > 0.0)) {
            throw domain("spot2");
        }
        if (!(mk.vol1() > 0.0)) {
            throw domain("vol1");
        }
        if (!(mk.vol2() > 0.0)) {
            throw domain("vol2");
        }
        if (!(mk.correlation() >= -1.0 && mk.correlation() <= 1.0)) {
            throw domain("correlation");
        }
        boolean exchange = false;
        for (List<Instrument> list : List.of(book, hedges)) {
            for (Instrument in : list) {
                checkDomain(in);
                exchange |= in.kind() == Kind.EXCHANGE;
            }
        }
        // Golden hedgecorr_i-0015 (vol1 = vol2, correlation 1) expects E_DOMAIN, while R6-11.16 names E_SINGULAR for
        // s <= 1e-12 (v1 + v2); the golden decides until the spec lane rules (SPEC_QUESTIONS J-R6-2).
        if (exchange && !(mk.spreadVol() > 1e-12 * (mk.vol1() + mk.vol2()))) {
            throw domain("correlation");
        }
        double[] before = new double[5];
        for (Instrument in : book) {
            double[] g = greeks(mk, in);
            for (int i = 0; i < 5; i++) {
                before[i] += in.get("quantity") * g[i];
            }
        }
        int n = hedges.size();
        double[][] unit = new double[n][];
        for (int j = 0; j < n; j++) {
            unit[j] = greeks(mk, hedges.get(j));
        }
        double[][] m = new double[n][n];
        double[] rhs = new double[n];
        for (int i = 0; i < n; i++) {
            int row = targets.get(i).ordinal();
            rhs[i] = -before[row];
            for (int j = 0; j < n; j++) {
                m[i][j] = unit[j][row];
            }
        }
        double[] sv = LinearAlgebra.singularValues(m);
        if (!(sv[n - 1] > Dense.RANK_TOL * sv[0])) {
            throw new QfError("E_SINGULAR", "the hedge Greek matrix is singular", "hedges");
        }
        double[] q = LinearAlgebra.solve(m, rhs);
        double[] after = before.clone();
        for (int j = 0; j < n; j++) {
            q[j] += 0.0;
            for (int i = 0; i < 5; i++) {
                after[i] += q[j] * unit[j][i];
            }
        }
        return new Result(q, before, after);
    }
}
