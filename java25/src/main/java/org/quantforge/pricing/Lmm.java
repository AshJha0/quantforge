package org.quantforge.pricing;

import org.quantforge.core.Normal;

/**
 * LIBOR market model, closed-form layer (lmm.md, ruling G-22): Black caplets on the integrated abcd variance and
 * Rebonato's frozen-weight swaption volatility with exponential correlation.
 */
public final class Lmm {
    private Lmm() {}

    /**
     * The abcd instantaneous volatility {@code (a + b (T - t)) exp(-c (T - t)) + d}.
     *
     * @param a level at the fixing, less {@code d}
     * @param b slope
     * @param c decay, positive
     * @param d long-dated level, non-negative
     */
    public record Abcd(double a, double b, double c, double d) {
        double at(double fixing, double t) {
            double s = fixing - t;
            return (a + b * s) * Math.exp(-c * s) + d;
        }
    }

    private static final int GL_N = 20;
    private static final double[] GL_X = new double[GL_N];
    private static final double[] GL_W = new double[GL_N];

    static {
        for (int i = 0; i < GL_N; i++) {
            double x = Math.cos(Math.PI * (i + 0.75) / (GL_N + 0.5));
            double dp = 0.0;
            for (int it = 0; it < 100; it++) {
                double p0 = 1.0;
                double p1 = x;
                for (int k = 2; k <= GL_N; k++) {
                    double p2 = ((2 * k - 1) * x * p1 - (k - 1) * p0) / k;
                    p0 = p1;
                    p1 = p2;
                }
                dp = GL_N * (x * p1 - p0) / (x * x - 1.0);
                double dx = p1 / dp;
                x -= dx;
                if (Math.abs(dx) < 1e-16) {
                    break;
                }
            }
            GL_X[i] = x;
            GL_W[i] = 2.0 / ((1.0 - x * x) * dp * dp);
        }
    }

    /**
     * {@code C(Ti, Tj; u)}, the integral of {@code sigma_Ti(t) sigma_Tj(t)} over {@code [0, u]}, by composite
     * 20-point Gauss-Legendre on pieces of at most a quarter year (exact to rounding for these integrands).
     *
     * @param v the volatility
     * @param ti first fixing time
     * @param tj second fixing time
     * @param u upper limit
     * @return the covariance integral
     */
    public static double covariance(Abcd v, double ti, double tj, double u) {
        int pieces = Math.max(1, (int) Math.ceil(u / 0.25));
        double w = u / pieces;
        double sum = 0.0;
        for (int k = 0; k < pieces; k++) {
            double mid = (k + 0.5) * w;
            double part = 0.0;
            for (int i = 0; i < GL_N; i++) {
                double t = mid + 0.5 * w * GL_X[i];
                part += GL_W[i] * v.at(ti, t) * v.at(tj, t);
            }
            sum += 0.5 * w * part;
        }
        return sum;
    }

    /**
     * Black's undiscounted price for total volatility {@code sd}.
     *
     * @param f forward
     * @param k strike
     * @param sd total standard deviation {@code v sqrt(T)}
     * @param call true for a call
     * @return the price
     */
    public static double black(double f, double k, double sd, boolean call) {
        double d1 = (Math.log(f / k) + sd * sd / 2.0) / sd;
        double d2 = d1 - sd;
        return call ? f * Normal.cdf(d1) - k * Normal.cdf(d2) : k * Normal.cdf(-d2) - f * Normal.cdf(-d1);
    }

    /**
     * A cap or floor.
     *
     * @param price total
     * @param caplets caplet (floorlet) prices
     * @param forwards forward rates
     * @param vols flat Black volatilities
     */
    public record Cap(double price, double[] caplets, double[] forwards, double[] vols) {}

    /**
     * Forward rates of a schedule on the single curve.
     *
     * @param curve the curve
     * @param times period times
     * @return the simple forwards, one per period
     */
    public static double[] forwards(ShortRate.Curve curve, double[] times) {
        double[] f = new double[times.length - 1];
        for (int i = 1; i < times.length; i++) {
            f[i - 1] = (curve.df(times[i - 1]) / curve.df(times[i]) - 1.0) / (times[i] - times[i - 1]);
        }
        return f;
    }

    /**
     * Caps and floors: Black caplets on the variance integrated to each fixing date.
     *
     * @param curve the curve
     * @param v the volatility
     * @param times period times
     * @param strike strike
     * @param cap true for a cap
     * @param notional notional
     * @return the cap
     */
    public static Cap capFloor(ShortRate.Curve curve, Abcd v, double[] times, double strike, boolean cap,
                               double notional) {
        int m = times.length - 1;
        double[] f = forwards(curve, times);
        double[] pr = new double[m];
        double[] vol = new double[m];
        double total = 0.0;
        for (int i = 0; i < m; i++) {
            double fix = times[i];
            double sd = Math.sqrt(covariance(v, fix, fix, fix));
            vol[i] = sd / Math.sqrt(fix);
            pr[i] = notional * (times[i + 1] - fix) * curve.df(times[i + 1]) * black(f[i], strike, sd, cap);
            total += pr[i];
        }
        return new Cap(total, pr, f, vol);
    }

    /**
     * A Rebonato swaption.
     *
     * @param price price
     * @param swapRate forward swap rate
     * @param annuity annuity per unit notional
     * @param blackVol Black volatility
     */
    public record Swaption(double price, double swapRate, double annuity, double blackVol) {}

    /**
     * Rebonato's frozen-weight swaption [BM 6.13].
     *
     * @param curve the curve
     * @param v the volatility
     * @param beta correlation decay
     * @param t0 expiry
     * @param pay payment times
     * @param k fixed rate
     * @param payer true for a payer
     * @param notional notional
     * @return the swaption
     */
    public static Swaption rebonato(ShortRate.Curve curve, Abcd v, double beta, double t0, double[] pay, double k,
                                    boolean payer, double notional) {
        int n = pay.length;
        double[] times = new double[n + 1];
        times[0] = t0;
        System.arraycopy(pay, 0, times, 1, n);
        double[] f = forwards(curve, times);
        double[] w = new double[n];
        double ann = 0.0;
        for (int i = 0; i < n; i++) {
            w[i] = (times[i + 1] - times[i]) * curve.df(times[i + 1]);
            ann += w[i];
        }
        double s = 0.0;
        for (int i = 0; i < n; i++) {
            w[i] /= ann;
            s += w[i] * f[i];
        }
        double var = 0.0;
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                double rho = Math.exp(-beta * Math.abs(times[i] - times[j]));
                var += w[i] * w[j] * f[i] * f[j] * rho * covariance(v, times[i], times[j], t0);
            }
        }
        double sd = Math.sqrt(var) / s;
        double price = notional * ann * black(s, k, sd, payer);
        return new Swaption(price, s, ann, sd / Math.sqrt(t0));
    }
}
