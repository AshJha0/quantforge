package org.quantforge.risk;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.quantforge.core.Finite;
import org.quantforge.core.QfError;
import org.quantforge.research.StressDrift;

/**
 * Stage K wave 1 (PROPOSED specs, rulings KR-1 to KR-14), ported from {@code python/quantforge_core/stage_k.py}: the
 * bitemporal store query, the sequential par bootstrap and its incremental update, the recalibration trigger, the
 * intraday delta-gamma estimate with a Lagrange bound, and the Richardson guard.
 *
 * <p>Error order HR-66: structural E_INPUT (the {@code check*Shape} methods and {@link #checkLog}, which the CLI calls
 * before the finite rule), then E_DOMAIN (the finite rule first), then value-dependent E_INPUT, then E_LIMIT.
 */
public final class StageK {
    private StageK() {}

    /** KR-10. */
    public static final String LABEL = "latency-aware analytics on simulated data";
    public static final int MAX_RECORDS = 1_000_000;
    public static final int MAX_QUOTES = 200;
    public static final int MAX_CHANGES = 100_000;
    public static final int MAX_POSITIONS = 100_000;

    private static QfError input(String message, String field) {
        return new QfError("E_INPUT", message, field);
    }

    private static QfError domain(String message, String field) {
        return new QfError("E_DOMAIN", message, field);
    }

    private static QfError limit(String field, int max) {
        return new QfError("E_LIMIT", field + " is above its limit of " + max, field);
    }

    // --- bitemporal store (KR-2, KR-3, KR-14) ----------------------------------------------------------

    /** One record; instants are whole seconds since the epoch, {@code validTo} null is open. */
    public record BiRecord(long sequence, String seriesId, long validFrom, Long validTo, long knowledgeTime,
            Object value, boolean deleted) {}

    /** The answer of a query: {@code FOUND} with the row, or {@code WITHDRAWN} / {@code NONE} with null. */
    public record Answer(String status, BiRecord row) {}

    /** Log checks 2 to 4 (structural E_INPUT), in the spec's order. */
    public static void checkLog(List<BiRecord> records) {
        for (int i = 1; i < records.size(); i++) {
            if (records.get(i).sequence() <= records.get(i - 1).sequence()) {
                throw input("sequence must be strictly increasing", "records");
            }
        }
        for (int i = 1; i < records.size(); i++) {
            if (records.get(i).knowledgeTime() < records.get(i - 1).knowledgeTime()) {
                throw input("knowledge_time went backwards", "records");
            }
        }
        for (BiRecord r : records) {
            if (r.validTo() != null && r.validTo() <= r.validFrom()) {
                throw input("valid_to must be after valid_from", "records");
            }
        }
    }

    /**
     * {@code core.store.bitemporal_query}: the record with the highest sequence among those known by K (inclusive)
     * whose valid interval holds V. A deleted winner is WITHDRAWN (it masks older records).
     */
    public static Answer bitemporalQuery(List<BiRecord> records, String seriesId, long knowledgeAsOf, long validAt) {
        checkLog(records);
        for (BiRecord r : records) {
            if (r.value() instanceof Double d) {
                Finite.check("value", d);
            }
        }
        if (records.size() > MAX_RECORDS) {
            throw limit("records", MAX_RECORDS);
        }
        BiRecord best = null;
        for (BiRecord r : records) {
            if (r.seriesId().equals(seriesId) && r.knowledgeTime() <= knowledgeAsOf && r.validFrom() <= validAt
                    && (r.validTo() == null || validAt < r.validTo())
                    && (best == null || r.sequence() > best.sequence())) {
                best = r;
            }
        }
        if (best == null) {
            return new Answer("NONE", null);
        }
        if (best.deleted()) {
            return new Answer("WITHDRAWN", null);
        }
        return new Answer("FOUND", best);
    }

    // --- par bootstrap and incremental update (KR-5) ---------------------------------------------------

    public static void checkQuotesShape(int n) {
        if (n < 1) {
            throw input("quotes must hold at least one quote", "quotes");
        }
    }

    /**
     * Continues {@code P_k = (1 - S_k sum_(i<k) P_i) / (1 + S_k)} after the first {@code head} pillars of
     * {@code start}. The running sum goes left to right, so a continuation is bit-identical to a full build.
     */
    static double[] bootstrapFrom(double[] quotes, double[] start, int head) {
        double[] out = new double[quotes.length];
        double acc = 0.0;
        for (int i = 0; i < head; i++) {
            out[i] = start[i];
            acc += out[i];
        }
        for (int i = head; i < quotes.length; i++) {
            double s = quotes[i];
            double p = (1.0 - s * acc) / (1.0 + s);
            out[i] = p;
            acc += p;
        }
        return out;
    }

    private static void checkQuotes(double[] quotes, String field) {
        for (double s : quotes) {
            if (!(s > -1)) {
                throw domain("every quote must be above -1", field);
            }
        }
    }

    /** {@code curve.bootstrap.par_annual}: discount factors of annual par swaps with accrual 1. */
    public static double[] parAnnual(double[] quotes) {
        checkQuotesShape(quotes.length);
        Finite.check("quotes", quotes);
        checkQuotes(quotes, "quotes");
        if (quotes.length > MAX_QUOTES) {
            throw limit("quotes", MAX_QUOTES);
        }
        return bootstrapFrom(quotes, quotes, 0);
    }

    public static void checkUpdateShape(int nPrevious, int nDfs, int nNew) {
        if (nPrevious < 1 || nPrevious != nDfs || nDfs != nNew) {
            throw input("previous_quotes, previous_discount_factors and new_quotes must have one equal, "
                    + "non-zero length", "new_quotes");
        }
    }

    /** Result of an incremental update; {@code firstChangedIndex} null when no quote changed. */
    public record Update(double[] discountFactors, Integer firstChangedIndex, int recomputed) {}

    /**
     * {@code curve.incremental.update}: copies the pillars before the first changed quote and solves the rest. The
     * cache must equal the bootstrap of {@code previousQuotes} bit for bit (E_INPUT otherwise).
     */
    public static Update incrementalUpdate(double[] previousQuotes, double[] previousDfs, double[] newQuotes) {
        checkUpdateShape(previousQuotes.length, previousDfs.length, newQuotes.length);
        Finite.check("previous_quotes", previousQuotes);
        Finite.check("previous_discount_factors", previousDfs);
        Finite.check("new_quotes", newQuotes);
        checkQuotes(previousQuotes, "previous_quotes");
        checkQuotes(newQuotes, "new_quotes");
        double[] fresh = bootstrapFrom(previousQuotes, previousQuotes, 0);
        for (int i = 0; i < fresh.length; i++) {
            if (Double.doubleToRawLongBits(fresh[i]) != Double.doubleToRawLongBits(previousDfs[i])) {
                throw input("previous_discount_factors is not the bootstrap of previous_quotes",
                        "previous_discount_factors");
            }
        }
        if (newQuotes.length > MAX_QUOTES) {
            throw limit("new_quotes", MAX_QUOTES);
        }
        int j = -1;
        for (int i = 0; i < newQuotes.length; i++) {
            if (previousQuotes[i] != newQuotes[i]) {
                j = i;
                break;
            }
        }
        if (j < 0) {
            return new Update(previousDfs.clone(), null, 0);
        }
        return new Update(bootstrapFrom(newQuotes, previousDfs, j), j, newQuotes.length - j);
    }

    // --- recalibration trigger (KR-6, KR-13) -----------------------------------------------------------

    public static void checkChangesShape(int n) {
        if (n < 2) {
            throw input("changes must hold at least two one-day changes", "changes");
        }
    }

    static double sampleSd(double[] xs) {
        double mean = StressDrift.fsum(xs) / xs.length;
        double[] sq = new double[xs.length];
        for (int i = 0; i < xs.length; i++) {
            sq[i] = (xs[i] - mean) * (xs[i] - mean);
        }
        return Math.sqrt(StressDrift.fsum(sq) / (xs.length - 1));
    }

    /** Output of the trigger check. */
    public record Trigger(boolean fire, double sigma, double threshold, double falseAlarmRate) {}

    /** {@code calib.trigger.check}: fires iff {@code |x_now - x_ref| > k sigma sqrt(d)}, strictly. */
    public static Trigger triggerCheck(double[] changes, double xRef, double xNow, double daysSince, double k) {
        checkChangesShape(changes.length);
        Finite.check("changes", changes);
        Finite.check("x_ref", xRef);
        Finite.check("x_now", xNow);
        Finite.check("days_since", daysSince);
        Finite.check("k", k);
        if (!(k > 0)) {
            throw domain("k must be above 0", "k");
        }
        if (!(daysSince >= 1)) {
            throw domain("days_since must be at least 1", "days_since");
        }
        double sigma = sampleSd(changes);
        if (sigma == 0) {
            throw domain("the changes have zero standard deviation: no noise scale", "changes");
        }
        if (changes.length > MAX_CHANGES) {
            throw limit("changes", MAX_CHANGES);
        }
        double threshold = k * sigma * Math.sqrt(daysSince);
        // 2 (1 - N(k)) of KR-6, as 2 N(-k): Normal.cdf works on the tail in k itself, so it keeps full
        // precision far out (a bare erfc(k / sqrt 2) loses 1.2e-13 relative at k = 30, trig_k-0009).
        return new Trigger(Math.abs(xNow - xRef) > threshold, sigma, threshold,
                2.0 * org.quantforge.core.Normal.cdf(-k));
    }

    // --- intraday delta-gamma with a Lagrange bound (KR-7, KR-10, KR-12) ------------------------------

    /** A zero-coupon position: notional, maturity in years, continuously compounded yield. */
    public record ZeroPosition(double notional, double maturity, double yield) {}

    public static void checkPositionsShape(int n) {
        if (n < 1) {
            throw input("positions must not be empty", "positions");
        }
    }

    /** {@code |h|^3 M3 / 6} with {@code M3 = T^3 |N| exp(-T min(y, y + h))}. */
    static double positionBound(ZeroPosition p, double shift) {
        double t = p.maturity();
        double m3 = Math.pow(t, 3) * Math.abs(p.notional()) * Math.exp(-t * Math.min(p.yield(), p.yield() + shift));
        return Math.pow(Math.abs(shift), 3) * m3 / 6;
    }

    /** {@code V' h + V'' h^2 / 2} with {@code V = N exp(-y T)}. */
    static double positionEstimate(ZeroPosition p, double shift) {
        double t = p.maturity();
        double v = p.notional() * Math.exp(-p.yield() * t);
        return v * (-t * shift + t * t * shift * shift / 2);
    }

    /** Output of the intraday bound. */
    public record Intraday(double estimatePnl, double bound, String label) {}

    /**
     * {@code risk.intraday.delta_gamma_bound}: the delta-gamma P&amp;L of a parallel yield move and the sum of the
     * per-position remainder bounds (no netting: their signs are unknown in general).
     */
    public static Intraday deltaGammaBound(List<ZeroPosition> positions, double shift) {
        checkPositionsShape(positions.size());
        for (ZeroPosition p : positions) {
            Finite.check("notional", p.notional());
            Finite.check("maturity", p.maturity());
            Finite.check("yield", p.yield());
        }
        Finite.check("shift", shift);
        for (ZeroPosition p : positions) {
            if (!(p.maturity() > 0)) {
                throw domain("every maturity must be above 0", "positions.maturity");
            }
        }
        if (positions.size() > MAX_POSITIONS) {
            throw limit("positions", MAX_POSITIONS);
        }
        double[] est = new double[positions.size()];
        double[] bound = new double[positions.size()];
        for (int i = 0; i < est.length; i++) {
            est[i] = positionEstimate(positions.get(i), shift);
            bound[i] = positionBound(positions.get(i), shift);
        }
        return new Intraday(StressDrift.fsum(est), StressDrift.fsum(bound), LABEL);
    }

    /** Full revaluation {@code sum N (exp(-(y + h) T) - exp(-y T))}; a test helper, not an operation. */
    public static double zeroRevalue(List<ZeroPosition> positions, double shift) {
        double[] v = new double[positions.size()];
        for (int i = 0; i < v.length; i++) {
            ZeroPosition p = positions.get(i);
            v[i] = p.notional() * Math.exp(-p.yield() * p.maturity()) * Math.expm1(-shift * p.maturity());
        }
        return StressDrift.fsum(v);
    }

    // --- Richardson guard (KR-9, KR-12) ----------------------------------------------------------------

    public static void checkValuesShape(int n) {
        if (n != 3) {
            throw input("values must hold exactly three grid values", "values");
        }
    }

    /** Output of the guard; {@code observedOrder} and {@code extrapolated} may be null. */
    public record Richardson(String status, Double observedOrder, Double extrapolated) {
        public Map<String, Object> toMap() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("status", status);
            m.put("observed_order", observedOrder);
            m.put("extrapolated", extrapolated);
            return m;
        }
    }

    /**
     * {@code num.richardson.check}: extrapolates only when the differences keep one sign and the observed order is
     * within 0.5 of the assumed order.
     */
    public static Richardson richardsonCheck(double[] values, double ratio, double assumedOrder) {
        checkValuesShape(values.length);
        Finite.check("values", values);
        Finite.check("ratio", ratio);
        Finite.check("assumed_order", assumedOrder);
        if (!(ratio > 1)) {
            throw domain("ratio must be above 1", "ratio");
        }
        if (!(assumedOrder > 0)) {
            throw domain("assumed_order must be above 0", "assumed_order");
        }
        double f1 = values[0];
        double f2 = values[1];
        double f3 = values[2];
        double d1 = f1 - f2;
        double d2 = f2 - f3;
        if (d1 == 0 || d2 == 0 || (d1 > 0) != (d2 > 0)) {
            return new Richardson("NON_MONOTONE", null, null);
        }
        double observed = Math.log(d1 / d2) / Math.log(ratio);
        if (!(Math.abs(observed - assumedOrder) <= 0.5)) {
            return new Richardson("ORDER_MISMATCH", observed, null);
        }
        double rp = Math.pow(ratio, assumedOrder);
        return new Richardson("OK", observed, (rp * f3 - f2) / (rp - 1));
    }
}
