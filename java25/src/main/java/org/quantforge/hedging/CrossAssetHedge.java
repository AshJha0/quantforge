package org.quantforge.hedging;

import java.util.List;
import java.util.Map;
import java.util.Set;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/**
 * {@code hedge.crossasset.solve} ({@code 08-hedging/cross-asset-hedge.md}): one weighted least-squares hedge of the
 * equity move and the key rates together. Risks are repricing half-differences (ruling I-21): {@code EQ01} from spot
 * times 1.01 and 0.99, {@code KR01_k} from pillar {@code k}'s zero rate plus and minus 1bp. The solve is
 * {@link LeastSquaresHedge#solve} without bounds or equalities.
 */
public final class CrossAssetHedge {
    private CrossAssetHedge() {}

    private static final double BP = 1e-4;

    /** Instrument kinds and the keys each carries besides {@code instrument} and a book's {@code quantity}. */
    public enum Kind {
        /** European call, Black-Scholes-Merton with rate {@code z(T)}. */
        CALL(Set.of("strike", "expiry_years")),
        /** European put. */
        PUT(Set.of("strike", "expiry_years")),
        /** Long forward, {@code S e^{-qT} - K P(T)}. */
        FORWARD(Set.of("strike", "expiry_years")),
        /** Zero-coupon bond, {@code notional P(T)} (ruling I-22). */
        ZCB(Set.of("expiry_years", "notional")),
        /** The equity itself. */
        UNDERLYING(Set.of());

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
     * The market: one equity and a zero curve, linear in zero rate between pillars, flat before the first and
     * undefined after the last (ruling I-20).
     *
     * @param spot equity spot
     * @param dividendYield continuous dividend yield
     * @param volatility flat volatility
     * @param times pillar times in years, strictly increasing, the first above 0
     * @param zeroRates continuously compounded zero rates, one per pillar
     */
    public record Market(double spot, double dividendYield, double volatility, double[] times, double[] zeroRates) {
        double zero(double t, double[] z) {
            if (t <= times[0]) {
                return z[0];
            }
            int k = 1;
            while (times[k] < t) {
                k++;
            }
            double w = (t - times[k - 1]) / (times[k] - times[k - 1]);
            return z[k - 1] + w * (z[k] - z[k - 1]);
        }
    }

    /**
     * The answer.
     *
     * @param positions units of each hedge
     * @param bookRisk {@code EQ01, KR01_1..KR01_P} of the book
     * @param residualRisk {@code bookRisk + A positions}
     * @param objective weighted squared residual plus the ridge term
     */
    public record Result(double[] positions, double[] bookRisk, double[] residualRisk, double objective) {}

    private static QfError input(String key, String why) {
        return new QfError("E_INPUT", key + ": " + why, key);
    }

    private static QfError domain(String key) {
        return new QfError("E_DOMAIN", key + " is out of range", key);
    }

    /** The value of one unit at spot {@code s} on zero rates {@code z}. */
    static double value(Market mk, Instrument in, double s, double[] z) {
        if (in.kind() == Kind.UNDERLYING) {
            return s;
        }
        double t = in.get("expiry_years");
        double r = mk.zero(t, z);
        double df = Math.exp(-r * t);
        double fwd = s * Math.exp(-mk.dividendYield() * t);
        return switch (in.kind()) {
            case ZCB -> in.get("notional") * df;
            case FORWARD -> fwd - in.get("strike") * df;
            default -> {
                double k = in.get("strike");
                double v = mk.volatility();
                double sq = Math.sqrt(t);
                double d1 = (Math.log(s / k) + (r - mk.dividendYield() + 0.5 * v * v) * t) / (v * sq);
                double d2 = d1 - v * sq;
                yield in.kind() == Kind.CALL ? fwd * Normal.cdf(d1) - k * df * Normal.cdf(d2)
                        : k * df * Normal.cdf(-d2) - fwd * Normal.cdf(-d1);
            }
        };
    }

    /** {@code EQ01, KR01_1..KR01_P} of one unit (ruling I-21). */
    static double[] risk(Market mk, Instrument in) {
        int p = mk.times().length;
        double[] out = new double[1 + p];
        double[] z = mk.zeroRates();
        out[0] = (value(mk, in, 1.01 * mk.spot(), z) - value(mk, in, 0.99 * mk.spot(), z)) / 2.0;
        for (int k = 0; k < p; k++) {
            double[] up = z.clone();
            double[] dn = z.clone();
            up[k] += BP;
            dn[k] -= BP;
            out[1 + k] = (value(mk, in, mk.spot(), up) - value(mk, in, mk.spot(), dn)) / 2.0;
        }
        return out;
    }

    private static void checkKeys(Instrument in, boolean book, String where) {
        int expected = in.kind().keys().size() + (book ? 1 : 0);
        boolean ok = !in.unknownKey() && in.values().size() == expected && in.values().keySet().stream()
                .allMatch(k -> in.kind().keys().contains(k) || (book && k.equals("quantity")));
        if (!ok) {
            throw input(where, "keys do not fit " + in.kind());
        }
    }

    /**
     * Solves the hedge.
     *
     * @param mk the market
     * @param book the positions to hedge, each with {@code quantity}
     * @param hedges the hedge instruments
     * @param weights one per risk factor, {@code 1 + P}
     * @param ridge Tikhonov weight, {@code >= 0}
     * @return the positions and the risks before and after
     * @throws QfError {@code E_INPUT}, {@code E_DOMAIN} or {@code E_SINGULAR}, in the specification's order
     */
    public static Result solve(Market mk, List<Instrument> book, List<Instrument> hedges, double[] weights,
            double ridge) {
        double[] times = mk.times();
        int p = times.length;
        if (p == 0 || mk.zeroRates().length != p) {
            throw input("curve", "no pillars, or zero_rates of another length");
        }
        if (!(times[0] > 0.0)) {
            throw input("curve", "first time at or below 0");
        }
        for (int k = 1; k < p; k++) {
            if (!(times[k] > times[k - 1])) {
                throw input("curve", "times not strictly increasing");
            }
        }
        for (Instrument in : book) {
            checkKeys(in, true, "book");
        }
        for (Instrument in : hedges) {
            checkKeys(in, false, "hedges");
        }
        if (book.isEmpty()) {
            throw input("book", "empty");
        }
        if (hedges.isEmpty()) {
            throw input("hedges", "empty");
        }
        if (weights.length != 1 + p) {
            throw input("weights", "one weight per risk factor");
        }
        for (List<Instrument> list : List.of(book, hedges)) {
            for (Instrument in : list) {
                if (in.values().containsKey("expiry_years") && in.get("expiry_years") > times[p - 1]) {
                    throw input("expiry_years", "beyond the last pillar");
                }
            }
        }
        if (!(mk.spot() > 0.0)) {
            throw domain("spot");
        }
        if (!(mk.volatility() > 0.0)) {
            throw domain("volatility");
        }
        for (double w : weights) {
            if (!(w > 0.0)) {
                throw domain("weights");
            }
        }
        if (!(ridge >= 0.0)) {
            throw domain("ridge");
        }
        for (List<Instrument> list : List.of(book, hedges)) {
            for (Instrument in : list) {
                for (String k : List.of("strike", "expiry_years", "notional")) {
                    if (in.values().containsKey(k) && !(in.get(k) > 0.0)) {
                        throw domain(k);
                    }
                }
            }
        }
        double[] b = new double[1 + p];
        for (Instrument in : book) {
            double[] r = risk(mk, in);
            for (int f = 0; f <= p; f++) {
                b[f] += in.get("quantity") * r[f];
            }
        }
        int n = hedges.size();
        double[][] a = new double[1 + p][n];
        for (int j = 0; j < n; j++) {
            double[] r = risk(mk, hedges.get(j));
            for (int f = 0; f <= p; f++) {
                a[f][j] = r[f];
            }
        }
        LeastSquaresHedge.Solution s = LeastSquaresHedge.solve(a, b, weights, ridge, null, null, null, null, false);
        return new Result(s.x(), b, s.residual(), s.objective());
    }
}
