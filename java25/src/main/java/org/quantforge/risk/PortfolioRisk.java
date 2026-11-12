package org.quantforge.risk;

import java.util.Arrays;
import org.quantforge.core.Finite;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;
import org.quantforge.core.Rng;

/** VaR, ES and backtests (var-es-and-backtests.md, rulings F-31, F-32). Losses are positive. */
public final class PortfolioRisk {
    private PortfolioRisk() {}

    public record VarEs(double var, double es, long tailCount, Double sigmaNext) {}

    public static void checkConfidence(double c) {
        Finite.check("confidence", c);
        if (!(c >= 0.5 && c < 1.0)) {
            throw new QfError("E_DOMAIN", "confidence must be in [0.5, 1)", "confidence");
        }
    }

    /** The order statistic rule on P&L scenarios (ruling F-31). */
    private static VarEs fromPnl(double[] pnl, double c, Double sigmaNext) {
        int n = pnl.length;
        double[] loss = new double[n];
        for (int i = 0; i < n; i++) {
            loss[i] = -pnl[i];
        }
        Arrays.sort(loss);
        int k = (int) Math.ceil(n * c);
        k = Math.max(1, Math.min(n, k));
        // ES by the tail weight w = n - n c (ruling R6-3.1): the m = floor(w) largest losses in full and a fraction
        // w - m of the next one, divided by w; w <= 0 gives the largest loss.
        double w = n - n * c;
        double es;
        long tail;
        if (w <= 0.0) {
            es = loss[n - 1];
            tail = 1;
        } else {
            int m = (int) Math.floor(w);
            double s = 0.0;
            for (int i = 0; i < m; i++) {
                s += loss[n - 1 - i];
            }
            if (w > m && m < n) {
                s += (w - m) * loss[n - 1 - m];
            }
            es = s / w;
            tail = (long) Math.ceil(w);
        }
        return new VarEs(loss[k - 1], es, tail, sigmaNext);
    }

    public static VarEs historical(double[] pnl, double c) {
        Finite.check("pnl", pnl);
        checkConfidence(c);
        if (pnl.length == 0) {
            throw new QfError("E_INPUT", "no pnl", "pnl");
        }
        return fromPnl(pnl, c, null);
    }

    public static VarEs filtered(double[] r, double position, double lambda, double c) {
        Finite.check("returns", r);
        Finite.check("position_value", position);
        Finite.check("lambda", lambda);
        checkConfidence(c);
        if (r.length == 0) {
            throw new QfError("E_INPUT", "no returns", "returns");
        }
        if (!(lambda > 0.0 && lambda < 1.0)) {
            throw new QfError("E_DOMAIN", "lambda must be in (0, 1)", "lambda");
        }
        int t = r.length;
        double[] var = new double[t + 1];
        double ms = 0.0;
        for (double v : r) {
            ms += v * v;
        }
        if (ms == 0.0) {
            throw new QfError("E_DOMAIN", "all returns are 0", "returns"); // ruling F-39
        }
        var[0] = ms / t;
        for (int i = 0; i < t; i++) {
            var[i + 1] = lambda * var[i] + (1.0 - lambda) * r[i] * r[i];
        }
        double next = Math.sqrt(var[t]);
        double[] pnl = new double[t];
        for (int i = 0; i < t; i++) {
            pnl[i] = position * r[i] * next / Math.sqrt(var[i]);
        }
        return fromPnl(pnl, c, next);
    }

    public static VarEs parametric(double mu, double sigma, double c) {
        Finite.check("mean", mu);
        Finite.check("std", sigma);
        checkConfidence(c);
        if (!(sigma > 0.0)) {
            throw new QfError("E_DOMAIN", "std must be positive", "std");
        }
        double z = Rng.ppnd16(c);
        return new VarEs(-mu + sigma * z, -mu + sigma * Normal.pdf(z) / (1.0 - c), 0, null);
    }

    public static VarEs monteCarlo(double[] mean, double[][] cov, double[] w, long paths, long seed, double c) {
        Finite.check("mean", mean);
        Finite.check("weights", w);
        checkConfidence(c);
        int n = mean.length;
        if (cov.length != n || w.length != n || n == 0) {
            throw new QfError("E_INPUT", "mean, covariance and weights must match", "covariance");
        }
        for (int i = 0; i < n; i++) {
            Finite.check("covariance", cov[i]);
            if (cov[i].length != n) {
                throw new QfError("E_INPUT", "covariance must be square", "covariance");
            }
            for (int j = 0; j < n; j++) {
                if (cov[i][j] != cov[j][i]) {
                    throw new QfError("E_DOMAIN", "covariance must be symmetric", "covariance");
                }
            }
        }
        if (paths < 1) {
            throw new QfError("E_DOMAIN", "paths must be at least 1", "paths");
        }
        double[][] l;
        try {
            l = LinearAlgebra.cholesky(cov);
        } catch (QfError e) {
            throw new QfError("E_NOT_POSITIVE_DEFINITE", "covariance is not positive definite", "covariance");
        }
        Rng rng = Rng.seeded(seed, 0);
        double[] pnl = new double[Math.toIntExact(paths)];
        double[] z = new double[n];
        for (int p = 0; p < pnl.length; p++) {
            for (int i = 0; i < n; i++) {
                z[i] = rng.nextNormal();
            }
            double v = 0.0;
            for (int i = 0; i < n; i++) {
                double ri = mean[i];
                for (int j = 0; j <= i; j++) {
                    ri += l[i][j] * z[j];
                }
                v += w[i] * ri;
            }
            pnl[p] = v;
        }
        return fromPnl(pnl, c, null);
    }

    // ---- backtests ----

    private static double xlnx(double count, double p) {
        return count == 0.0 ? 0.0 : count * Math.log(p);
    }

    private static double floor(double lr) {
        return lr < 1e-12 ? 0.0 : lr;
    }

    /** P(chi^2_1 > x). */
    public static double chi2Sf1(double x) {
        return x == 0.0 ? 1.0 : 2.0 * Normal.cdf(-Math.sqrt(x));
    }

    /** P(chi^2_2 > x). */
    public static double chi2Sf2(double x) {
        return Math.exp(-x / 2.0);
    }

    public static double lrUc(long n, long x, double c) {
        double p = 1.0 - c;
        double ph = (double) x / n;
        double lr = -2.0 * (xlnx(n - x, 1.0 - p) + xlnx(x, p)) + 2.0 * (xlnx(n - x, 1.0 - ph) + xlnx(x, ph));
        return floor(lr);
    }

    public record Kupiec(double lr, double pValue) {}

    public static Kupiec kupiec(long n, long x, double c) {
        checkConfidence(c);
        if (n < 1 || x < 0 || x > n) {
            throw new QfError("E_DOMAIN", "need n >= 1 and 0 <= exceptions <= n", "exceptions");
        }
        double lr = lrUc(n, x, c);
        return new Kupiec(lr, chi2Sf1(lr));
    }

    public record Christoffersen(double lrUc, double lrInd, double lrCc, double pUc, double pInd, double pCc,
                                 long n00, long n01, long n10, long n11) {}

    public static Christoffersen christoffersen(boolean[] e, double c) {
        checkConfidence(c);
        int n = e.length;
        if (n < 2) {
            throw new QfError("E_INPUT", "need at least 2 days", "exceptions");
        }
        long x = 0;
        for (boolean b : e) {
            x += b ? 1 : 0;
        }
        long[][] t = new long[2][2];
        for (int i = 1; i < n; i++) {
            t[e[i - 1] ? 1 : 0][e[i] ? 1 : 0]++;
        }
        long n00 = t[0][0];
        long n01 = t[0][1];
        long n10 = t[1][0];
        long n11 = t[1][1];
        double pi01 = n00 + n01 == 0 ? 0.0 : (double) n01 / (n00 + n01);
        double pi11 = n10 + n11 == 0 ? 0.0 : (double) n11 / (n10 + n11);
        double pi = (double) (n01 + n11) / (n - 1);
        double lrInd = floor(-2.0 * (xlnx(n00 + n10, 1.0 - pi) + xlnx(n01 + n11, pi)
                - xlnx(n00, 1.0 - pi01) - xlnx(n01, pi01) - xlnx(n10, 1.0 - pi11) - xlnx(n11, pi11)));
        double lrUc = lrUc(n, x, c);
        double lrCc = lrUc + lrInd;
        return new Christoffersen(lrUc, lrInd, lrCc, chi2Sf1(lrUc), chi2Sf1(lrInd), chi2Sf2(lrCc),
                n00, n01, n10, n11);
    }

    public record TrafficLight(double cumulative, String zone, Double plusFactor) {}

    private static final double[] PLUS = {0.40, 0.50, 0.65, 0.75, 0.85};

    public static TrafficLight trafficLight(long n, long x, double c) {
        checkConfidence(c);
        if (n < 1 || x < 0 || x > n) {
            throw new QfError("E_DOMAIN", "need n >= 1 and 0 <= exceptions <= n", "exceptions");
        }
        double p = 1.0 - c;
        // P(X <= x) by summing pmfs in log space.
        double lnq = Math.log1p(-p);
        double lnp = Math.log(p);
        double s = 0.0;
        double lnChoose = 0.0;
        for (long k = 0; k <= x; k++) {
            if (k > 0) {
                lnChoose += Math.log((double) (n - k + 1)) - Math.log((double) k);
            }
            s += Math.exp(lnChoose + k * lnp + (n - k) * lnq);
        }
        String zone = s < 0.95 ? "GREEN" : s < 0.9999 ? "YELLOW" : "RED";
        Double plus = null;
        if (n == 250 && c == 0.99) {
            plus = x <= 4 ? 0.0 : x <= 9 ? PLUS[(int) x - 5] : 1.0;
        }
        return new TrafficLight(s, zone, plus);
    }
}
