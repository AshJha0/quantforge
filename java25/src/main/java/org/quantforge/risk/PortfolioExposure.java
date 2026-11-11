package org.quantforge.risk;

import java.util.ArrayList;
import java.util.List;
import org.quantforge.core.Normal;
import org.quantforge.pricing.ShortRate;

/**
 * Exposure profile of a netting set of swaps under Hull-White in its LGM form, by exact one-factor integration
 * (xva-exposure-portfolio.md, ruling G-42).
 */
public final class PortfolioExposure {
    private PortfolioExposure() {}

    /**
     * A fixed-float swap (G-12 conventions).
     *
     * @param notional notional
     * @param fixedRate fixed rate
     * @param payer true when paying fixed
     * @param start start time
     * @param pay payment times
     */
    public record Swap(double notional, double fixedRate, boolean payer, double start, double[] pay) {}

    /**
     * One exposure date.
     *
     * @param ee discounted expected exposure
     * @param ene discounted expected negative exposure
     * @param pfe potential future exposure, one per quantile
     */
    public record Point(double ee, double ene, double[] pfe) {}

    private static final int GRID = 600;
    private static final double SPAN = 12.0;
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

    /** The deflated netting-set value {@code f(x)} at one reset date, with its legs precomputed. */
    private static final class Deflated {
        final double ht;
        final double zt;
        final double pt;
        final List<double[]> coef = new ArrayList<>(); // per leg term: {weight, H(T) - Ht, (H(T)^2 - Ht^2) zt / 2}
        double constant;

        Deflated(ShortRate.Curve curve, double a, double sigma, List<Swap> trades, double t) {
            ht = h(a, t);
            zt = sigma * sigma * Math.expm1(2.0 * a * t) / (2.0 * a);
            pt = curve.df(t);
            for (Swap s : trades) {
                double sgn = s.payer() ? 1.0 : -1.0;
                double prev = t;
                int last = -1;
                for (int i = 0; i < s.pay().length; i++) {
                    if (s.pay()[i] > t) {
                        last = i;
                    }
                }
                if (last < 0) {
                    continue;
                }
                constant += sgn * s.notional();
                for (int i = 0; i < s.pay().length; i++) {
                    double ti = s.pay()[i];
                    if (!(ti > t)) {
                        continue;
                    }
                    double w = -sgn * s.notional() * s.fixedRate() * (ti - prev);
                    if (i == last) {
                        w -= sgn * s.notional();
                    }
                    prev = ti;
                    double hT = h(a, ti);
                    coef.add(new double[] {w * curve.df(ti) / pt, hT - ht, (hT * hT - ht * ht) * zt / 2.0});
                }
            }
        }

        double value(double x) {
            double v = constant;
            for (double[] c : coef) {
                v += c[0] * Math.exp(-c[1] * x - c[2]);
            }
            return v * pt * Math.exp(-ht * x - ht * ht * zt / 2.0);
        }
    }

    private static double h(double a, double t) {
        return -Math.expm1(-a * t) / a;
    }

    private static double root(Deflated f, double y, double x0, double x1) {
        double f0 = f.value(x0) - y;
        for (int it = 0; it < 200; it++) {
            double m = 0.5 * (x0 + x1);
            if (m == x0 || m == x1) {
                break;
            }
            double fm = f.value(m) - y;
            if (fm == 0.0) {
                return m;
            }
            if ((fm < 0.0) == (f0 < 0.0)) {
                x0 = m;
                f0 = fm;
            } else {
                x1 = m;
            }
        }
        return 0.5 * (x0 + x1);
    }

    /** Roots of {@code f - y} on the scan grid, as the specification's reference does. */
    private static List<Double> crossings(Deflated f, double[] xs, double[] vs, double y, boolean exactZero) {
        List<Double> z = new ArrayList<>();
        for (int i = 0; i < GRID; i++) {
            double v0 = vs[i] - y;
            double v1 = vs[i + 1] - y;
            if (exactZero && v0 == 0.0) {
                z.add(xs[i]);
            } else if (v0 * v1 < 0.0) {
                z.add(root(f, y, xs[i], xs[i + 1]));
            }
        }
        return z;
    }

    private static double integral(Deflated f, double a, double b, double sd) {
        int pieces = Math.max(1, (int) Math.ceil((b - a) / (0.25 * sd)));
        double w = (b - a) / pieces;
        double norm = 1.0 / (sd * Math.sqrt(2.0 * Math.PI));
        double sum = 0.0;
        for (int k = 0; k < pieces; k++) {
            double mid = a + (k + 0.5) * w;
            double part = 0.0;
            for (int i = 0; i < GL_N; i++) {
                double x = mid + 0.5 * w * GL_X[i];
                part += GL_W[i] * f.value(x) * Math.exp(-x * x / (2.0 * sd * sd));
            }
            sum += 0.5 * w * part;
        }
        return sum * norm;
    }

    private static double cdf(Deflated f, double[] xs, double[] vs, double y, double sd) {
        List<Double> pts = new ArrayList<>();
        pts.add(xs[0]);
        pts.addAll(crossings(f, xs, vs, y, false));
        pts.add(xs[GRID]);
        double p = 0.0;
        for (int i = 0; i + 1 < pts.size(); i++) {
            double a = pts.get(i);
            double b = pts.get(i + 1);
            if (f.value(0.5 * (a + b)) - y <= 0.0) {
                p += Normal.cdf(b / sd) - Normal.cdf(a / sd);
            }
        }
        return p;
    }

    /**
     * EE, ENE and PFE at one reset date.
     *
     * @param curve the curve
     * @param a mean reversion
     * @param sigma volatility
     * @param trades the netting set
     * @param t the reset date
     * @param q PFE quantiles in (0, 1)
     * @return the profile point
     */
    public static Point point(ShortRate.Curve curve, double a, double sigma, List<Swap> trades, double t, double[] q) {
        Deflated f = new Deflated(curve, a, sigma, trades, t);
        double sd = Math.sqrt(f.zt);
        double[] xs = new double[GRID + 1];
        double[] vs = new double[GRID + 1];
        double vmax = Double.NEGATIVE_INFINITY;
        for (int i = 0; i <= GRID; i++) {
            xs[i] = sd * (-SPAN + 2.0 * SPAN * i / GRID);
            vs[i] = f.value(xs[i]);
            vmax = Math.max(vmax, vs[i]);
        }
        List<Double> pts = new ArrayList<>();
        pts.add(xs[0]);
        pts.addAll(crossings(f, xs, vs, 0.0, true));
        pts.add(xs[GRID]);
        double ee = 0.0;
        double ene = 0.0;
        for (int i = 0; i + 1 < pts.size(); i++) {
            double lo = pts.get(i);
            double hi = pts.get(i + 1);
            if (!(hi > lo)) {
                continue;
            }
            double val = integral(f, lo, hi, sd);
            if (f.value(0.5 * (lo + hi)) > 0.0) {
                ee += val;
            } else {
                ene += val;
            }
        }
        double[] pfe = new double[q.length];
        double c0 = cdf(f, xs, vs, 0.0, sd);
        for (int j = 0; j < q.length; j++) {
            if (c0 >= q[j]) {
                continue;
            }
            double lo = 0.0;
            double hi = vmax;
            for (int it = 0; it < 200; it++) {
                double mid = 0.5 * (lo + hi);
                if (cdf(f, xs, vs, mid, sd) >= q[j]) {
                    hi = mid;
                } else {
                    lo = mid;
                }
                if (hi - lo <= 1e-11 * Math.max(1.0, hi)) {
                    break;
                }
            }
            pfe[j] = hi;
        }
        return new Point(ee, ene, pfe);
    }
}
