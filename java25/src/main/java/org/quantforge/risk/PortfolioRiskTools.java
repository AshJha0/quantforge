package org.quantforge.risk;

import java.util.Arrays;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/**
 * Stage F carry-over tools: F3 sensitivities (f3-sensitivities.md, ruling G-47) and F4 portfolio-risk tools
 * (portfolio-risk-tools.md, ruling G-46). Every one is a closed form on its inputs.
 */
public final class PortfolioRiskTools {
    private PortfolioRiskTools() {}

    private static QfError domain(String key, String why) {
        return new QfError("E_DOMAIN", why, key);
    }

    // ---- F3 ----

    /**
     * Receive-inflation zero-coupon swap value.
     *
     * @param n notional
     * @param years years
     * @param k fixed rate
     * @param z market rate
     * @param p discount factor
     * @return the value
     */
    public static double zcisPv(double n, long years, double k, double z, double p) {
        return n * p * (Math.pow(1.0 + z, years) - Math.pow(1.0 + k, years));
    }

    /**
     * Analytic inflation01 per 1 bp.
     *
     * @param n notional
     * @param years years
     * @param z market rate
     * @param p discount factor
     * @return the sensitivity
     */
    public static double inflation01(double n, long years, double z, double p) {
        return n * p * years * Math.pow(1.0 + z, years - 1) * 1e-4;
    }

    /**
     * Black-Scholes-Merton price and dV/dy with yield {@code y}.
     *
     * @param call true for a call
     * @param s spot
     * @param k strike
     * @param t expiry
     * @param r rate
     * @param y total yield
     * @param v volatility
     * @return {price, dV/dy}
     */
    public static double[] bsmYield(boolean call, double s, double k, double t, double r, double y, double v) {
        double sd = v * Math.sqrt(t);
        double d1 = (Math.log(s / k) + (r - y + v * v / 2.0) * t) / sd;
        double d2 = d1 - sd;
        double fs = s * Math.exp(-y * t);
        double dk = k * Math.exp(-r * t);
        if (call) {
            return new double[] {fs * Normal.cdf(d1) - dk * Normal.cdf(d2), -t * fs * Normal.cdf(d1)};
        }
        return new double[] {dk * Normal.cdf(-d2) - fs * Normal.cdf(-d1), t * fs * Normal.cdf(-d1)};
    }

    /**
     * Margrabe exchange option and its correlation sensitivity per 1 point.
     *
     * @param f1 forward of the received asset {@code Q1 S1 e^(-q1 T)}
     * @param f2 forward of the delivered asset
     * @param v1 volatility 1
     * @param v2 volatility 2
     * @param rho correlation
     * @param t expiry
     * @return {price, correlation01, spread vol}
     */
    public static double[] margrabe(double f1, double f2, double v1, double v2, double rho, double t) {
        double var = v1 * v1 + v2 * v2 - 2.0 * rho * v1 * v2;
        double s = Math.sqrt(Math.max(var, 0.0));
        if (!(s > 0.0)) {
            throw domain("correlation", "spread volatility is zero");
        }
        double sq = s * Math.sqrt(t);
        double d1 = (Math.log(f1 / f2) + sq * sq / 2.0) / sq;
        double price = f1 * Normal.cdf(d1) - f2 * Normal.cdf(d1 - sq);
        double dVds = f1 * Normal.pdf(d1) * Math.sqrt(t);
        return new double[] {price, dVds * (-v1 * v2 / s) * 0.01, s};
    }

    // ---- F4 ----

    /**
     * Reverse stress: smallest {@code k > 0} with {@code b k + a k^2 = -L}.
     *
     * @param d direction
     * @param delta deltas
     * @param gamma gamma matrix
     * @param loss target loss
     * @return the scale
     */
    public static double reverseScale(double[] d, double[] delta, double[][] gamma, double loss) {
        double b = 0.0;
        double a = 0.0;
        for (int i = 0; i < d.length; i++) {
            b += delta[i] * d[i];
            for (int j = 0; j < d.length; j++) {
                a += d[i] * gamma[i][j] * d[j];
            }
        }
        a /= 2.0;
        double best = Double.POSITIVE_INFINITY;
        if (a == 0.0) {
            if (b != 0.0) {
                best = -loss / b;
            }
        } else {
            double disc = b * b - 4.0 * a * loss;
            if (disc >= 0.0) {
                double sg = b >= 0.0 ? 1.0 : -1.0;
                double q = -(b + sg * Math.sqrt(disc)) / 2.0;
                for (double k : new double[] {q / a, q == 0.0 ? Double.NaN : loss / q}) {
                    if (k > 0.0 && k < best) {
                        best = k;
                    }
                }
            }
        }
        if (!(best > 0.0 && best < Double.POSITIVE_INFINITY)) {
            throw domain("target_loss", "no positive scale reaches the loss");
        }
        return best;
    }

    /**
     * Concentration weights.
     *
     * @param x exposures
     * @return {@code |x_i| / sum |x|}
     */
    public static double[] weights(double[] x) {
        double sum = 0.0;
        for (double v : x) {
            sum += Math.abs(v);
        }
        if (!(sum > 0.0)) {
            throw domain("exposures", "all exposures are zero");
        }
        double[] w = new double[x.length];
        for (int i = 0; i < x.length; i++) {
            w[i] = Math.abs(x[i]) / sum;
        }
        return w;
    }

    /**
     * Sum of the {@code n} largest weights.
     *
     * @param w weights
     * @param n count
     * @return the share
     */
    public static double topShare(double[] w, int n) {
        double[] s = w.clone();
        Arrays.sort(s);
        double t = 0.0;
        for (int i = 0; i < n; i++) {
            t += s[s.length - 1 - i];
        }
        return t;
    }

    /**
     * Variance ratio of an h-day sum under AR(1) daily returns.
     *
     * @param rho AR(1) coefficient
     * @param h horizon in days
     * @return {@code Var / (h sigma^2)}
     */
    public static double varianceRatio(double rho, long h) {
        double sum = h;
        double pk = 1.0;
        for (long k = 1; k < h; k++) {
            pk *= rho;
            sum += 2.0 * (h - k) * pk;
        }
        return sum / h;
    }
}
