package org.quantforge.hedging;

import java.util.List;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/**
 * Stage I closed-form hedges ({@code hedge-solvers.md}): the minimum-variance ratio, Black-Scholes-Merton Greek
 * neutralisation, the equity-beta futures hedge and the residual-risk report. Every rank or singularity decision
 * uses the relative threshold {@code 1e-12} (ruling I-3).
 */
public final class HedgeRatios {
    private HedgeRatios() {}

    private static QfError input(String key, String why) {
        return new QfError("E_INPUT", key + ": " + why, key);
    }

    private static QfError domain(String key) {
        return new QfError("E_DOMAIN", key + " is out of range", key);
    }

    /**
     * A minimum-variance answer.
     *
     * @param hedge units held of each hedge instrument (negative is short)
     * @param varianceBefore the exposure's variance
     * @param varianceAfter the hedged variance
     * @param effectiveness {@code 1 - varianceAfter / varianceBefore}
     */
    public record MinVariance(double[] hedge, double varianceBefore, double varianceAfter, double effectiveness) {}

    private static double maxAbs(double[][] s) {
        double m = 0.0;
        for (double[] row : s) {
            for (double v : row) {
                m = Math.max(m, Math.abs(v));
            }
        }
        return m;
    }

    private static boolean symmetric(double[][] s) {
        double limit = 1e-12 * maxAbs(s);
        for (int i = 0; i < s.length; i++) {
            for (int j = 0; j < i; j++) {
                if (Math.abs(s[i][j] - s[j][i]) > limit) {
                    return false;
                }
            }
        }
        return true;
    }

    private static boolean square(double[][] s) {
        for (double[] row : s) {
            if (row.length != s.length) {
                return false;
            }
        }
        return true;
    }

    /**
     * The sample covariance (divisor {@code T - 1}) of the exposure and hedge series, exposure first.
     *
     * @param exposure value changes of the position, length {@code T}
     * @param hedges value changes of one unit of each hedge, {@code k} series of length {@code T}
     * @return the {@code (k+1) x (k+1)} covariance
     * @throws QfError {@code E_INPUT} for unequal lengths, no hedge series, or fewer than {@code k + 2} observations
     */
    public static double[][] sampleCovariance(double[] exposure, double[][] hedges) {
        int k = hedges.length;
        if (k < 1) {
            throw input("hedge_changes", "no hedge series");
        }
        int t = exposure.length;
        for (double[] h : hedges) {
            if (h.length != t) {
                throw input("hedge_changes", "series of unequal length");
            }
        }
        if (t < k + 2) {
            throw input("exposure_changes", "fewer than k + 2 observations");
        }
        double[][] series = new double[k + 1][];
        series[0] = exposure;
        System.arraycopy(hedges, 0, series, 1, k);
        double[] mean = new double[k + 1];
        for (int i = 0; i <= k; i++) {
            double s = 0.0;
            for (double v : series[i]) {
                s += v;
            }
            mean[i] = s / t;
        }
        double[][] cov = new double[k + 1][k + 1];
        for (int i = 0; i <= k; i++) {
            for (int j = 0; j <= i; j++) {
                double s = 0.0;
                for (int p = 0; p < t; p++) {
                    s += (series[i][p] - mean[i]) * (series[j][p] - mean[j]);
                }
                cov[i][j] = s / (t - 1);
                cov[j][i] = cov[i][j];
            }
        }
        return cov;
    }

    /**
     * {@code hedge.minvar.ratio} on a covariance of value changes, index 0 the position and 1 to {@code k} one unit
     * of each hedge: {@code hedge = -S_hh^{-1} S_he} (ruling I-8).
     *
     * @param s the covariance of value changes
     * @return the hedge, the variances before and after, and the effectiveness
     * @throws QfError {@code E_INPUT}, {@code E_DOMAIN}, {@code E_SINGULAR} or {@code E_NOT_POSITIVE_DEFINITE}, in
     *     the specification's order
     */
    public static MinVariance minimumVariance(double[][] s) {
        if (s.length < 2 || !square(s)) {
            throw input("covariance", "not square or smaller than 2 x 2");
        }
        if (!symmetric(s)) {
            throw input("covariance", "not symmetric");
        }
        if (!(s[0][0] > 0.0)) {
            throw domain("covariance");
        }
        int k = s.length - 1;
        double maxDiag = 0.0;
        for (int i = 1; i <= k; i++) {
            maxDiag = Math.max(maxDiag, s[i][i]);
        }
        double[][] l = new double[k][k]; // Cholesky of S_hh with the pivot test of check 3
        for (int j = 0; j < k; j++) {
            double d = s[j + 1][j + 1];
            for (int p = 0; p < j; p++) {
                d -= l[j][p] * l[j][p];
            }
            if (!(d > Dense.RANK_TOL * maxDiag)) {
                throw new QfError("E_SINGULAR", "the hedge covariance block is singular", "covariance");
            }
            l[j][j] = Math.sqrt(d);
            for (int i = j + 1; i < k; i++) {
                double v = s[i + 1][j + 1];
                for (int p = 0; p < j; p++) {
                    v -= l[i][p] * l[j][p];
                }
                l[i][j] = v / l[j][j];
            }
        }
        double[] she = new double[k];
        for (int i = 0; i < k; i++) {
            she[i] = s[i + 1][0];
        }
        double[] tmp = new double[k];
        for (int i = 0; i < k; i++) {
            double v = she[i];
            for (int p = 0; p < i; p++) {
                v -= l[i][p] * tmp[p];
            }
            tmp[i] = v / l[i][i];
        }
        double[] hedge = new double[k];
        for (int i = k - 1; i >= 0; i--) {
            double v = tmp[i];
            for (int p = i + 1; p < k; p++) {
                v -= l[p][i] * hedge[p];
            }
            hedge[i] = v / l[i][i];
        }
        for (int i = 0; i < k; i++) {
            hedge[i] = -hedge[i] + 0.0;
        }
        double after = s[0][0] + Dense.dot(she, hedge);
        if (after < 0.0) {
            throw new QfError("E_NOT_POSITIVE_DEFINITE", "the hedged variance is negative", "covariance");
        }
        return new MinVariance(hedge, s[0][0], after, 1.0 - after / s[0][0]);
    }

    /** An instrument for the Greek hedge. */
    public enum Instrument {
        /** A European call. */
        CALL,
        /** A European put. */
        PUT,
        /** The underlying itself: delta 1, gamma 0, vega 0. */
        UNDERLYING
    }

    /** A Greek that can be neutralised. */
    public enum Greek {
        /** First derivative in spot. */
        DELTA,
        /** Second derivative in spot. */
        GAMMA,
        /** Derivative in volatility, per unit of volatility (ruling I-9). */
        VEGA
    }

    /**
     * A position or hedge instrument. Options carry {@code strike} and {@code expiryYears}; the underlying carries
     * neither (null).
     *
     * @param instrument call, put or the underlying
     * @param strike option strike, null for the underlying
     * @param expiryYears option expiry in years, null for the underlying
     * @param quantity units held (unused for a hedge instrument)
     */
    public record Position(Instrument instrument, Double strike, Double expiryYears, double quantity) {}

    /**
     * The flat Black-Scholes-Merton market of the Greek hedge.
     *
     * @param spot spot price
     * @param rate continuously compounded rate
     * @param dividendYield continuous dividend yield
     * @param volatility lognormal volatility
     */
    public record Market(double spot, double rate, double dividendYield, double volatility) {}

    /**
     * A Greek-hedge answer.
     *
     * @param quantities units of each hedge instrument
     * @param before the book's delta, gamma and vega before the hedge
     * @param after the same after the hedge
     */
    public record GreekHedge(double[] quantities, double[] before, double[] after) {}

    /** Per-unit delta, gamma and vega of one instrument. */
    static double[] greeks(Market mk, Position p) {
        if (p.instrument() == Instrument.UNDERLYING) {
            return new double[] {1.0, 0.0, 0.0};
        }
        double t = p.expiryYears();
        double v = mk.volatility();
        double sq = Math.sqrt(t);
        double d1 = (Math.log(mk.spot() / p.strike()) + (mk.rate() - mk.dividendYield() + 0.5 * v * v) * t) / (v * sq);
        double dq = Math.exp(-mk.dividendYield() * t);
        double delta = p.instrument() == Instrument.CALL ? dq * Normal.cdf(d1) : -dq * Normal.cdf(-d1);
        double pdf = Normal.pdf(d1);
        return new double[] {delta, dq * pdf / (mk.spot() * v * sq), mk.spot() * dq * pdf * sq};
    }

    /**
     * {@code hedge.greeks.neutralise}: the hedge quantities {@code q} with {@code G q = -g_book} on the targets.
     *
     * @param mk the market
     * @param book the positions to hedge
     * @param hedges the hedge instruments, as many as targets
     * @param targets the Greeks to set to zero, distinct
     * @return the quantities and the book's Greeks before and after
     * @throws QfError {@code E_INPUT}, {@code E_DOMAIN} or {@code E_SINGULAR}, in the specification's order
     */
    public static GreekHedge neutralise(Market mk, List<Position> book, List<Position> hedges, List<Greek> targets) {
        for (List<Position> list : List.of(book, hedges)) {
            for (Position p : list) {
                boolean underlying = p.instrument() == Instrument.UNDERLYING;
                if (underlying ? p.strike() != null || p.expiryYears() != null
                        : p.strike() == null || p.expiryYears() == null) {
                    throw input(list == book ? "portfolio" : "hedges", "strike and expiry_years do not fit "
                            + p.instrument());
                }
            }
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
        if (!(mk.spot() > 0.0)) {
            throw domain("spot");
        }
        if (!(mk.volatility() > 0.0)) {
            throw domain("volatility");
        }
        for (List<Position> list : List.of(book, hedges)) {
            for (Position p : list) {
                if (p.instrument() != Instrument.UNDERLYING && !(p.strike() > 0.0)) {
                    throw domain("strike");
                }
                if (p.instrument() != Instrument.UNDERLYING && !(p.expiryYears() > 0.0)) {
                    throw domain("expiry_years");
                }
            }
        }
        double[] before = new double[3];
        for (Position p : book) {
            double[] g = greeks(mk, p);
            for (int i = 0; i < 3; i++) {
                before[i] += p.quantity() * g[i];
            }
        }
        int n = hedges.size();
        double[][] unit = new double[n][];
        for (int j = 0; j < n; j++) {
            unit[j] = greeks(mk, hedges.get(j));
        }
        double[][] g = new double[n][n];
        double[] rhs = new double[n];
        for (int i = 0; i < n; i++) {
            int row = targets.get(i).ordinal();
            rhs[i] = -before[row];
            for (int j = 0; j < n; j++) {
                g[i][j] = unit[j][row];
            }
        }
        double[] sv = LinearAlgebra.singularValues(g);
        if (!(sv[n - 1] > Dense.RANK_TOL * sv[0])) {
            throw new QfError("E_SINGULAR", "the hedge Greek matrix is singular", "hedges");
        }
        double[] q = LinearAlgebra.solve(g, rhs);
        double[] after = before.clone();
        for (int j = 0; j < n; j++) {
            q[j] += 0.0;
            for (int i = 0; i < 3; i++) {
                after[i] += q[j] * unit[j][i];
            }
        }
        return new GreekHedge(q, before, after);
    }

    /**
     * An equity-beta futures answer.
     *
     * @param contracts {@code (beta* - beta) V / (F m)}, positive is long
     * @param contractsHeld the contracts after rounding
     * @param betaAfter {@code beta + contractsHeld F m / V}
     */
    public record BetaHedge(double contracts, double contractsHeld, double betaAfter) {}

    /**
     * {@code hedge.beta.futures}. With {@code round}, contracts are rounded half away from zero (ruling I-10).
     *
     * @param value portfolio value {@code V}
     * @param beta portfolio beta
     * @param targetBeta beta after the hedge
     * @param futuresPrice futures price {@code F}
     * @param multiplier contract multiplier {@code m}
     * @param round true for {@code NEAREST}, false for {@code NONE}
     * @return the exact and held contracts and the beta after
     * @throws QfError {@code E_DOMAIN} when the value, futures price or multiplier is not positive
     */
    public static BetaHedge betaFutures(double value, double beta, double targetBeta, double futuresPrice,
            double multiplier, boolean round) {
        if (!(value > 0.0)) {
            throw domain("portfolio_value");
        }
        if (!(futuresPrice > 0.0)) {
            throw domain("futures_price");
        }
        if (!(multiplier > 0.0)) {
            throw domain("multiplier");
        }
        double contracts = (targetBeta - beta) * value / (futuresPrice * multiplier) + 0.0;
        double held = round ? LeastSquaresHedge.roundHalfAway(contracts) : contracts;
        return new BetaHedge(contracts, held, beta + held * futuresPrice * multiplier / value);
    }

    /**
     * A residual-risk report.
     *
     * @param residual {@code A x + b}
     * @param varianceBefore {@code b'Sb}
     * @param varianceAfter {@code r'Sr}
     * @param volatilityAfter {@code sqrt(max(varianceAfter, 0))}
     * @param effectiveness {@code 1 - varianceAfter / varianceBefore}
     * @param contributions {@code r_i (S r)_i}, summing to {@code varianceAfter} (ruling I-11)
     */
    public record Residual(double[] residual, double varianceBefore, double varianceAfter, double volatilityAfter,
            double effectiveness, double[] contributions) {}

    /**
     * {@code hedge.residual.report}.
     *
     * @param a factor-by-instrument sensitivities, {@code m x n}
     * @param b the book's factor exposures, length {@code m}
     * @param x hedge positions, length {@code n}
     * @param cov covariance of the factor moves, {@code m x m}
     * @return the residual, variances, effectiveness and Euler contributions
     * @throws QfError {@code E_INPUT}, {@code E_NOT_POSITIVE_DEFINITE} or {@code E_DOMAIN}, in the specification's
     *     order
     */
    public static Residual residualReport(double[][] a, double[] b, double[] x, double[][] cov) {
        int m = a.length;
        if (m == 0 || a[0].length == 0) {
            throw input("a", "empty");
        }
        int n = a[0].length;
        for (double[] row : a) {
            if (row.length != n) {
                throw input("a", "ragged");
            }
        }
        if (b.length != m) {
            throw input("b", "wrong length");
        }
        if (x.length != n) {
            throw input("x", "wrong length");
        }
        if (cov.length != m || !square(cov)) {
            throw input("covariance", "not m x m");
        }
        if (!symmetric(cov)) {
            throw input("covariance", "not symmetric");
        }
        Dense.Eigen e = Dense.eigen(cov);
        double max = e.maxAbs();
        for (double v : e.values()) {
            if (v < -Dense.RANK_TOL * max) {
                throw new QfError("E_NOT_POSITIVE_DEFINITE", "the covariance has a negative eigenvalue",
                        "covariance");
            }
        }
        double before = Dense.dot(b, Dense.mul(cov, b));
        if (!(before > 0.0)) {
            throw domain("b");
        }
        double[] r = LeastSquaresHedge.residual(a, b, x);
        double[] sr = Dense.mul(cov, r);
        double[] contrib = new double[m];
        double after = 0.0;
        for (int i = 0; i < m; i++) {
            contrib[i] = r[i] * sr[i] + 0.0;
            after += contrib[i];
        }
        return new Residual(r, before, after, Math.sqrt(Math.max(after, 0.0)), 1.0 - after / before, contrib);
    }
}
