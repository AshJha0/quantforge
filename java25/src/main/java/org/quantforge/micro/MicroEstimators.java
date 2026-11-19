package org.quantforge.micro;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;
import org.quantforge.core.QfError;
import org.quantforge.research.StressDrift;

/**
 * Microstructure estimators with planted truth ({@code specifications/09-microstructure/micro-estimators.md}, stage H
 * H-4b; rulings HR-70, HR-71, HR-74, HR-75 as amended (HR-66)). A port of the Python build's {@code micro_est.py}: each estimator returns
 * its point estimate and a standard error {@code se}; sums are correctly rounded (Python's {@code math.fsum}), so an
 * exact fit (HR-74) gives SE 0 or a value at the rounding floor. Error order HR-75 as amended (HR-66): a non-finite input
 * ({@code E_DOMAIN}, F-2), structural {@code E_INPUT}, then {@code E_DOMAIN}, then value-dependent {@code E_INPUT}.
 */
public final class MicroEstimators {
    private MicroEstimators() {}

    /** Code-point order, as Python sorts strings. */
    public static final Comparator<String> CODE_POINT = (a, b) -> {
        int i = 0;
        int j = 0;
        while (i < a.length() && j < b.length()) {
            int ca = a.codePointAt(i);
            int cb = b.codePointAt(j);
            if (ca != cb) {
                return Integer.compare(ca, cb);
            }
            i += Character.charCount(ca);
            j += Character.charCount(cb);
        }
        return Integer.compare(a.length() - i, b.length() - j);
    };

    /** An estimate and its standard error. */
    public record Estimate(double value, double se) {}

    /** A cancel-rate observation: lifetime and whether the order was cancelled (else filled). */
    public record Order(double lifetime, boolean cancelled) {}

    /** A regime's impact sample. */
    public record Sample(double[] x, double[] y) {}

    /** {@code micro.est.regime_impact}: per-label estimates in code-point order and the stressed / calm ratio. */
    public record RegimeImpact(Map<String, Estimate> regimes, double ratio) {}

    private static QfError fail(String code, String message, String field) {
        return new QfError(code, message, field);
    }

    private static void finite(String field, double... v) {
        for (double a : v) {
            if (!Double.isFinite(a)) {
                throw fail("E_DOMAIN", field + " must be finite", field);
            }
        }
    }

    private static double fsum(double[] v) {
        return StressDrift.fsum(v);
    }

    /** OLS through the origin: beta = sum xy / sum x^2, s2 = SSR / (n - 1), SE = sqrt(s2 / sum x^2). */
    static Estimate olsOrigin(double[] x, double[] y, String field) {
        if (x.length != y.length || x.length < 2) {
            throw fail("E_INPUT", "x and y need equal lengths of at least 2", field);
        }
        int n = x.length;
        double[] t = new double[n];
        for (int i = 0; i < n; i++) {
            t[i] = x[i] * x[i];
        }
        double sxx = fsum(t);
        if (sxx == 0) {
            throw fail("E_INPUT", "the sum of x^2 is 0", field);
        }
        for (int i = 0; i < n; i++) {
            t[i] = x[i] * y[i];
        }
        double beta = fsum(t) / sxx;
        for (int i = 0; i < n; i++) {
            double r = y[i] - beta * x[i];
            t[i] = r * r;
        }
        return new Estimate(beta, Math.sqrt(fsum(t) / (n - 1) / sxx));
    }

    /** OLS with intercept: the slope and its SE with n - 2 degrees of freedom. */
    private static Estimate olsSlope(double[] t, double[] y, String field) {
        int n = t.length;
        double tm = fsum(t) / n;
        double ym = fsum(y) / n;
        double[] w = new double[n];
        for (int i = 0; i < n; i++) {
            w[i] = (t[i] - tm) * (t[i] - tm);
        }
        double stt = fsum(w);
        if (stt == 0) {
            throw fail("E_INPUT", "all abscissae are equal", field);
        }
        for (int i = 0; i < n; i++) {
            w[i] = (t[i] - tm) * (y[i] - ym);
        }
        double slope = fsum(w) / stt;
        double icpt = ym - slope * tm;
        for (int i = 0; i < n; i++) {
            double r = y[i] - icpt - slope * t[i];
            w[i] = r * r;
        }
        return new Estimate(slope, Math.sqrt(fsum(w) / (n - 2) / stt));
    }

    /** {@code micro.est.arrival_rate}: Poisson MLE lambda = N / T, SE = sqrt(lambda / T). */
    public static Estimate arrivalRate(long count, double window) {
        finite("window", window);
        if (count < 0) {
            throw fail("E_DOMAIN", "count must be non-negative", "count");
        }
        if (window <= 0) {
            throw fail("E_DOMAIN", "window must be positive", "window");
        }
        double lam = count / window;
        return new Estimate(lam, Math.sqrt(lam / window));
    }

    /** {@code micro.est.cancel_rate}: censored exponential MLE theta = C / sum L, SE = theta / sqrt(C). */
    public static Estimate cancelRate(Order[] orders) {
        double[] life = new double[orders.length];
        int c = 0;
        for (int i = 0; i < orders.length; i++) {
            life[i] = orders[i].lifetime();
            c += orders[i].cancelled() ? 1 : 0;
        }
        finite("orders", life);
        for (double l : life) {
            if (l <= 0) {
                throw fail("E_DOMAIN", "lifetimes must be positive", "orders");
            }
        }
        if (c == 0) {
            throw fail("E_INPUT", "no cancelled order", "orders");
        }
        double theta = c / fsum(life);
        return new Estimate(theta, theta / Math.sqrt(c));
    }

    /** {@code micro.est.resilience}: kappa = -slope of ln(S - S_inf) on t (OLS with intercept); points are (t, S). */
    public static Estimate resilience(double sInf, double[][] points) {
        finite("s_inf", sInf);
        for (double[] p : points) {
            finite("points", p);
        }
        if (points.length < 3) {
            throw fail("E_INPUT", "need at least 3 points", "points");
        }
        for (double[] p : points) {
            if (p[1] <= sInf) {
                throw fail("E_DOMAIN", "every spread must exceed s_inf", "points");
            }
        }
        double[] t = new double[points.length];
        double[] y = new double[points.length];
        for (int i = 0; i < points.length; i++) {
            t[i] = points[i][0];
            y[i] = Math.log(points[i][1] - sInf);
        }
        Estimate e = olsSlope(t, y, "points");
        return new Estimate(-e.value(), e.se());
    }

    /** {@code micro.est.liquidity_decay}: alpha = -slope of ln D on k; levels are (k, D). */
    public static Estimate liquidityDecay(double[][] levels) {
        for (double[] p : levels) {
            finite("levels", p);
        }
        if (levels.length < 3) {
            throw fail("E_INPUT", "need at least 3 levels", "levels");
        }
        for (double[] p : levels) {
            if (p[1] <= 0) {
                throw fail("E_DOMAIN", "every depth must be positive", "levels");
            }
        }
        double[] k = new double[levels.length];
        double[] y = new double[levels.length];
        for (int i = 0; i < levels.length; i++) {
            k[i] = levels[i][0];
            y[i] = Math.log(levels[i][1]);
        }
        Estimate e = olsSlope(k, y, "levels");
        return new Estimate(-e.value(), e.se());
    }

    /** {@code micro.est.adverse_selection}: dm = lambda_as s q + e, OLS through the origin. */
    public static Estimate adverseSelection(double[] x, double[] y) {
        finite("x", x);
        finite("y", y);
        return olsOrigin(x, y, "x");
    }

    /** {@code micro.est.regime_impact}: adverse selection per regime label; ratio stressed / calm. */
    public static RegimeImpact regimeImpact(Map<String, Sample> regimes) {
        Map<String, Sample> sorted = new TreeMap<>(CODE_POINT);
        sorted.putAll(regimes);
        for (Map.Entry<String, Sample> e : sorted.entrySet()) {
            finite("regimes." + e.getKey(), e.getValue().x());
            finite("regimes." + e.getKey(), e.getValue().y());
        }
        for (String need : new String[] {"calm", "stressed"}) {
            if (!sorted.containsKey(need)) {
                throw fail("E_INPUT", "regime '" + need + "' is missing", "regimes");
            }
        }
        for (Map.Entry<String, Sample> e : sorted.entrySet()) {
            Sample s = e.getValue();
            if (s.x().length != s.y().length || s.x().length < 2) {
                throw fail("E_INPUT", "x and y need equal lengths of at least 2", "regimes." + e.getKey());
            }
        }
        Map<String, Estimate> out = new LinkedHashMap<>();
        for (Map.Entry<String, Sample> e : sorted.entrySet()) {
            out.put(e.getKey(), olsOrigin(e.getValue().x(), e.getValue().y(), "regimes." + e.getKey()));
        }
        double calm = out.get("calm").value();
        if (calm == 0) {
            throw fail("E_DOMAIN", "calm lambda_as is 0; the ratio is undefined", "regimes");
        }
        return new RegimeImpact(out, out.get("stressed").value() / calm);
    }

    private static double[] meanVar(double[] v) {
        int n = v.length;
        double m = fsum(v) / n;
        double[] d = new double[n];
        for (int i = 0; i < n; i++) {
            d[i] = (v[i] - m) * (v[i] - m);
        }
        return new double[] {m, fsum(d) / (n - 1)};
    }

    /** {@code micro.est.passive_vs_aggressive}: delta = mean(aggressive) - mean(passive), Welch SE. */
    public static Estimate passiveVsAggressive(double[] passive, double[] aggressive) {
        finite("passive", passive);
        finite("aggressive", aggressive);
        if (passive.length < 2) {
            throw fail("E_INPUT", "need at least 2 fills per class", "passive");
        }
        if (aggressive.length < 2) {
            throw fail("E_INPUT", "need at least 2 fills per class", "aggressive");
        }
        double[] p = meanVar(passive);
        double[] a = meanVar(aggressive);
        return new Estimate(a[0] - p[0], Math.sqrt(a[1] / aggressive.length + p[1] / passive.length));
    }
}
