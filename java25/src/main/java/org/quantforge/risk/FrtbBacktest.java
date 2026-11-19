package org.quantforge.risk;

import java.util.ArrayList;
import java.util.List;
import org.quantforge.core.QfError;

/**
 * FRTB internal models approach: backtesting zones and desk-level exception limits (plan item K-8e;
 * specifications/06-risk/frtb-ima-backtest.md, rulings KR-40 to KR-47). A port of
 * python/quantforge_core/frtb_backtest.py. The tables come from {@link FrtbBacktestTables}, generated from
 * specifications/06-risk/frtb-ima-backtest-tables.json.
 */
public final class FrtbBacktest {
    private FrtbBacktest() {}

    /**
     * The bank-wide zone.
     *
     * @param exceptions the larger of the actual and hypothetical counts
     * @param cumulativeProbability P(X &lt;= exceptions), X binomial(observations, 1%)
     * @param zone GREEN, AMBER or RED
     * @param amberFrom first count in the amber zone
     * @param redFrom first count in the red zone
     * @param multiplier the MAR32.9 multiplier at 250 observations, else null
     */
    public record Zone(long exceptions, double cumulativeProbability, String zone, long amberFrom, long redFrom,
            Double multiplier) {}

    /**
     * Desk eligibility (MAR32.19).
     *
     * @param exceptions99 the larger 99% count
     * @param exceptions975 the larger 97.5% count
     * @param cumulativeProbability99 P(X &lt;= exceptions99) at 1%
     * @param cumulativeProbability975 P(X &lt;= exceptions975) at 2.5%
     * @param breach99 more than 12 at 99%
     * @param breach975 more than 30 at 97.5%
     * @param eligible neither limit breached
     */
    public record Desk(long exceptions99, long exceptions975, double cumulativeProbability99,
            double cumulativeProbability975, boolean breach99, boolean breach975, boolean eligible) {}

    /**
     * Exception counts of a P&amp;L series against VaR.
     *
     * @param observations series length
     * @param exceptionsActual count on actual P&amp;L
     * @param exceptionsHypothetical count on hypothetical P&amp;L
     * @param exceptions the larger count
     * @param daysActual exception day indices, actual
     * @param daysHypothetical exception day indices, hypothetical
     */
    public record Count(long observations, long exceptionsActual, long exceptionsHypothetical, long exceptions,
            List<Long> daysActual, List<Long> daysHypothetical) {}

    /** Neumaier-compensated running sum of binomial terms, in log space with a running log binomial coefficient. */
    private static final class Terms {
        private final long n;
        private final double lnp;
        private final double lnq;
        private double lnChoose;
        private double sum;
        private double comp;
        private long k = -1;

        Terms(long n, double p) {
            this.n = n;
            this.lnp = Math.log(p);
            this.lnq = Math.log1p(-p);
        }

        /** Adds the next term and returns the compensated partial sum P(X &lt;= k). */
        double next() {
            k++;
            if (k > 0) {
                lnChoose += Math.log((double) (n - k + 1)) - Math.log((double) k);
            }
            double term = Math.exp(lnChoose + k * lnp + (n - k) * lnq);
            double t = sum + term;
            comp += Math.abs(sum) >= Math.abs(term) ? (sum - t) + term : (term - t) + sum;
            sum = t;
            return sum + comp;
        }
    }

    /** P(X &lt;= x) for X ~ Binomial(n, p), 0 &lt; p &lt; 1. */
    public static double binomialCdf(long n, long x, double p) {
        if (x < 0) {
            return 0.0;
        }
        if (x >= n) {
            return 1.0;
        }
        Terms t = new Terms(n, p);
        double s = 0.0;
        for (long k = 0; k <= x; k++) {
            s = t.next();
        }
        return Math.min(s, 1.0);
    }

    /** The smallest k in 0..n with P(X &lt;= k) &gt;= level. */
    static long firstAtLeast(long n, double p, double level) {
        Terms t = new Terms(n, p);
        for (long k = 0; k < n; k++) {
            if (t.next() >= level) {
                return k;
            }
        }
        return n;
    }

    private static void observations(long n) {
        if (n > FrtbBacktestTables.MAX_OBSERVATIONS) {
            throw new QfError("E_LIMIT", "observations is above its limit of " + FrtbBacktestTables.MAX_OBSERVATIONS,
                    "observations");
        }
        if (n < 1) {
            throw new QfError("E_DOMAIN", "observations must be at least 1", "observations");
        }
    }

    private static void count(long n, long x, String field) {
        if (!(0 <= x && x <= n)) {
            throw new QfError("E_DOMAIN", field + " must be in [0, observations]", field);
        }
    }

    /** Bank-wide backtesting zone (MAR32.5, MAR32.9, MAR99.8, MAR99.17). */
    public static Zone zone(long observations, long exceptionsActual, long exceptionsHypothetical) {
        observations(observations);
        count(observations, exceptionsActual, "exceptions_actual");
        count(observations, exceptionsHypothetical, "exceptions_hypothetical");
        long x = Math.max(exceptionsActual, exceptionsHypothetical);
        double p = 1.0 - FrtbBacktestTables.COVERAGE;
        double cumulative = binomialCdf(observations, x, p);
        long amber = firstAtLeast(observations, p, FrtbBacktestTables.AMBER_FROM);
        long red = firstAtLeast(observations, p, FrtbBacktestTables.RED_FROM);
        String z = x >= red ? "RED" : x >= amber ? "AMBER" : "GREEN";
        Double multiplier = null;
        if (observations == FrtbBacktestTables.TABLE_OBSERVATIONS) {
            double[] table = FrtbBacktestTables.MULTIPLIER_250;
            multiplier = x < table.length ? table[(int) x] : FrtbBacktestTables.MULTIPLIER_RED;
        }
        return new Zone(x, cumulative, z, amber, red, multiplier);
    }

    /** Trading desk backtesting eligibility (MAR32.18, MAR32.19). */
    public static Desk desk(long observations, long e99Actual, long e99Hypothetical, long e975Actual,
            long e975Hypothetical) {
        observations(observations);
        count(observations, e99Actual, "exceptions_99_actual");
        count(observations, e99Hypothetical, "exceptions_99_hypothetical");
        count(observations, e975Actual, "exceptions_975_actual");
        count(observations, e975Hypothetical, "exceptions_975_hypothetical");
        long x99 = Math.max(e99Actual, e99Hypothetical);
        long x975 = Math.max(e975Actual, e975Hypothetical);
        boolean b99 = x99 > FrtbBacktestTables.DESK_LIMIT_99;
        boolean b975 = x975 > FrtbBacktestTables.DESK_LIMIT_975;
        return new Desk(x99, x975, binomialCdf(observations, x99, 0.01), binomialCdf(observations, x975, 0.025), b99,
                b975, !(b99 || b975));
    }

    private static List<Long> days(List<Double> var, List<Double> pnl) {
        List<Long> out = new ArrayList<>();
        for (int t = 0; t < var.size(); t++) {
            Double v = var.get(t);
            Double q = pnl.get(t);
            if (v == null || q == null || -q > v) {
                out.add((long) t);
            }
        }
        return out;
    }

    /**
     * Exceptions of a daily P&amp;L series against a daily VaR (MAR32.5(1)-(2), MAR32.18(1)-(2)). VaR is positive for a
     * loss; a day is an exception when -pnl strictly exceeds VaR or either value is missing (null).
     */
    public static Count countExceptions(List<Double> var, List<Double> actual, List<Double> hypothetical) {
        int n = var.size();
        if (n == 0) {
            throw new QfError("E_INPUT", "var is empty", "var");
        }
        if (actual.size() != n) {
            throw new QfError("E_INPUT", "actual and var differ in length", "actual");
        }
        if (hypothetical.size() != n) {
            throw new QfError("E_INPUT", "hypothetical and var differ in length", "hypothetical");
        }
        List<Long> a = days(var, actual);
        List<Long> h = days(var, hypothetical);
        return new Count(n, a.size(), h.size(), Math.max(a.size(), h.size()), a, h);
    }
}
