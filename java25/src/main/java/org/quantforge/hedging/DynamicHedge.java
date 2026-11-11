package org.quantforge.hedging;

import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/**
 * Stage I wave 4b ({@code 08-hedging/dynamic-hedge-and-effectiveness.md}): the self-financing delta-hedge replay of
 * {@code hedge.backtest.delta} (ruling I-29) and the effectiveness statistics of {@code hedge.effectiveness}
 * (rulings I-30, I-31).
 */
public final class DynamicHedge {
    private DynamicHedge() {}

    /**
     * Effectiveness statistics of a hedge leg against a hedged item.
     *
     * @param dollarOffset {@code -sum(y) / sum(x)}, cumulative (I-30)
     * @param regressionSlope {@code cov(x, y) / var(x)}
     * @param regressionR2 {@code cov(x, y)^2 / (var(x) var(y))}
     * @param varianceReduction {@code 1 - var(x + y) / var(x)}
     */
    public record Effectiveness(double dollarOffset, double regressionSlope, double regressionR2,
            double varianceReduction) {}

    /**
     * A backtest result.
     *
     * @param optionValues the option's mark on each date
     * @param shares shares held over each step
     * @param portfolioValues the hedged portfolio's value on each date, 0 at the start
     * @param finalPnl the last portfolio value
     * @param effectiveness statistics of the item and hedge changes
     */
    public record Backtest(double[] optionValues, double[] shares, double[] portfolioValues, double finalPnl,
            Effectiveness effectiveness) {}

    private static boolean constant(double[] v) {
        for (double x : v) {
            if (x != v[0]) {
                return false;
            }
        }
        return true;
    }

    /**
     * {@code hedge.effectiveness} with sample (co)variances over {@code n - 1}.
     *
     * @param item the hedged item's changes {@code x}
     * @param hedge the hedge leg's changes {@code y}
     * @return the four statistics
     * @throws QfError {@code E_INPUT} for unequal or short series; {@code E_DOMAIN} when {@code sum(x) = 0} or a
     *     series has zero variance (I-31)
     */
    public static Effectiveness effectiveness(double[] item, double[] hedge) {
        int n = item.length;
        if (hedge.length != n) {
            throw new QfError("E_INPUT", "series of unequal length", "hedge_changes");
        }
        if (n < 3) {
            throw new QfError("E_INPUT", "fewer than 3 values", "item_changes");
        }
        double sx = 0.0;
        double sy = 0.0;
        for (int i = 0; i < n; i++) {
            sx += item[i];
            sy += hedge[i];
        }
        if (sx == 0.0) {
            throw new QfError("E_DOMAIN", "the hedged item's changes sum to zero", "item_changes");
        }
        if (constant(item)) {
            throw new QfError("E_DOMAIN", "the hedged item has no variance", "item_changes");
        }
        if (constant(hedge)) {
            throw new QfError("E_DOMAIN", "the hedge has no variance", "hedge_changes");
        }
        double mx = sx / n;
        double my = sy / n;
        double vx = 0.0;
        double vy = 0.0;
        double cxy = 0.0;
        double vs = 0.0;
        for (int i = 0; i < n; i++) {
            double dx = item[i] - mx;
            double dy = hedge[i] - my;
            vx += dx * dx;
            vy += dy * dy;
            cxy += dx * dy;
            vs += (dx + dy) * (dx + dy);
        }
        vx /= n - 1;
        vy /= n - 1;
        cxy /= n - 1;
        vs /= n - 1;
        return new Effectiveness(-sy / sx, cxy / vx, cxy * cxy / (vx * vy), 1.0 - vs / vx);
    }

    /** Black-Scholes-Merton value and delta; at {@code tau <= 0} the payoff and no delta. */
    static double[] valueDelta(boolean call, double s, double k, double tau, double r, double q, double v) {
        if (tau <= 0.0) {
            return new double[] {Math.max(call ? s - k : k - s, 0.0), Double.NaN};
        }
        double sq = Math.sqrt(tau);
        double d1 = (Math.log(s / k) + (r - q + 0.5 * v * v) * tau) / (v * sq);
        double d2 = d1 - v * sq;
        double fq = s * Math.exp(-q * tau);
        double kr = k * Math.exp(-r * tau);
        double dq = Math.exp(-q * tau);
        return call ? new double[] {fq * Normal.cdf(d1) - kr * Normal.cdf(d2), dq * Normal.cdf(d1)}
                : new double[] {kr * Normal.cdf(-d2) - fq * Normal.cdf(-d1), -dq * Normal.cdf(-d1)};
    }

    /**
     * {@code hedge.backtest.delta}: replays the path in the I-29 order (interest on cash, dividends on the shares held
     * at the step's start, the mark, then the rebalance except on the last date).
     *
     * @param call true for a call, false for a put
     * @param strike option strike
     * @param expiry option expiry in years
     * @param quantity options held, negative short
     * @param rate continuously compounded rate
     * @param dividendYield continuous dividend yield
     * @param vol hedge volatility, for marks and deltas
     * @param times dates in years, from 0, strictly increasing, the last at or before expiry
     * @param spots the spot path, one per date
     * @return the marks, shares, portfolio values, final P&amp;L and the effectiveness of the hedge leg
     * @throws QfError {@code E_INPUT}, then {@code E_DOMAIN}, in the specification's order
     */
    public static Backtest backtest(boolean call, double strike, double expiry, double quantity, double rate,
            double dividendYield, double vol, double[] times, double[] spots) {
        int m = times.length;
        if (spots.length != m) {
            throw new QfError("E_INPUT", "times and spots differ in length", "spots");
        }
        if (m < 4) {
            throw new QfError("E_INPUT", "fewer than 4 dates", "times");
        }
        if (times[0] != 0.0) {
            throw new QfError("E_INPUT", "times must start at 0", "times");
        }
        for (int i = 1; i < m; i++) {
            if (!(times[i] > times[i - 1])) {
                throw new QfError("E_INPUT", "times must increase strictly", "times");
            }
        }
        if (times[m - 1] > expiry) {
            throw new QfError("E_INPUT", "the path goes beyond expiry", "times");
        }
        for (double s : spots) {
            if (!(s > 0.0)) {
                throw new QfError("E_DOMAIN", "spot at or below 0", "spots");
            }
        }
        if (!(strike > 0.0)) {
            throw new QfError("E_DOMAIN", "strike at or below 0", "strike");
        }
        if (!(expiry > 0.0)) {
            throw new QfError("E_DOMAIN", "expiry at or below 0", "expiry_years");
        }
        if (!(vol > 0.0)) {
            throw new QfError("E_DOMAIN", "hedge volatility at or below 0", "hedge_volatility");
        }
        double[] v = new double[m];
        double[] delta = new double[m];
        for (int i = 0; i < m; i++) {
            double[] vd = valueDelta(call, spots[i], strike, expiry - times[i], rate, dividendYield, vol);
            v[i] = vd[0];
            delta[i] = vd[1];
        }
        double[] h = new double[m - 1];
        for (int i = 0; i < m - 1; i++) {
            h[i] = -quantity * delta[i] + 0.0;
        }
        double[] pi = new double[m];
        double cash = -quantity * v[0] - h[0] * spots[0];
        double[] item = new double[m - 1];
        double[] hedge = new double[m - 1];
        for (int i = 0; i < m - 1; i++) {
            double dt = times[i + 1] - times[i];
            cash = cash * Math.exp(rate * dt) + h[i] * spots[i] * Math.expm1(dividendYield * dt);
            pi[i + 1] = quantity * v[i + 1] + h[i] * spots[i + 1] + cash;
            if (i + 1 < m - 1) {
                cash -= (h[i + 1] - h[i]) * spots[i + 1];
            }
            item[i] = quantity * (v[i + 1] - v[i]);
            hedge[i] = (pi[i + 1] - pi[i]) - item[i];
        }
        return new Backtest(v, h, pi, pi[m - 1], effectiveness(item, hedge));
    }
}
