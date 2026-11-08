package org.quantforge.pricing;

import java.util.function.DoubleUnaryOperator;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;
import org.quantforge.vol.Black;

/** Stage E5 exotics: digitals, barriers, geometric Asians, lookbacks, quanto, chooser, Kirk, basket, and American
 * options by CRR, BAW and a reference FD scheme (exotics.md, rulings E-A19 to E-A23). */
public final class Exotics {
    private Exotics() {}

    private static double n(double x) {
        return Normal.cdf(x);
    }

    /** Generalised Black-Scholes with cost of carry b. */
    public static double gbs(double phi, double s, double k, double t, double r, double b, double v) {
        return Black.lognormal(phi, s * Math.exp(b * t), k, t, Math.exp(-r * t), v);
    }

    public static double digital(double phi, boolean cash, double s, double k, double t, double r, double q, double v,
                                 double amount) {
        double sd = v * Math.sqrt(t);
        double d1 = (Math.log(s / k) + (r - q + v * v / 2) * t) / sd;
        return cash ? amount * Math.exp(-r * t) * n(phi * (d1 - sd)) : s * Math.exp(-q * t) * n(phi * d1);
    }

    public enum BarrierType { DOWN_IN, DOWN_OUT, UP_IN, UP_OUT }

    /** Reiner-Rubinstein, continuous monitoring [RR91]. */
    public static double barrier(double phi, BarrierType type, double s, double k, double t, double r, double q,
                                 double v, double h, double rebate) {
        boolean down = type == BarrierType.DOWN_IN || type == BarrierType.DOWN_OUT;
        if (down ? s <= h : s >= h) {
            throw new QfError("E_DOMAIN", "spot is on or beyond the barrier (ruling E-A19)", "barrier");
        }
        double b = r - q;
        double eta = down ? 1.0 : -1.0;
        double sd = v * Math.sqrt(t);
        double mu = (b - v * v / 2) / (v * v);
        double lambda = Math.sqrt(mu * mu + 2 * r / (v * v));
        double x1 = Math.log(s / k) / sd + (1 + mu) * sd;
        double x2 = Math.log(s / h) / sd + (1 + mu) * sd;
        double y1 = Math.log(h * h / (s * k)) / sd + (1 + mu) * sd;
        double y2 = Math.log(h / s) / sd + (1 + mu) * sd;
        double z = Math.log(h / s) / sd + lambda * sd;
        double carry = s * Math.exp((b - r) * t);
        double disc = k * Math.exp(-r * t);
        double hs = h / s;
        double a = phi * carry * n(phi * x1) - phi * disc * n(phi * x1 - phi * sd);
        double bb = phi * carry * n(phi * x2) - phi * disc * n(phi * x2 - phi * sd);
        double c = phi * carry * Math.pow(hs, 2 * (mu + 1)) * n(eta * y1) - phi * disc * Math.pow(hs, 2 * mu)
                * n(eta * y1 - eta * sd);
        double d = phi * carry * Math.pow(hs, 2 * (mu + 1)) * n(eta * y2) - phi * disc * Math.pow(hs, 2 * mu)
                * n(eta * y2 - eta * sd);
        double e = rebate * Math.exp(-r * t) * (n(eta * x2 - eta * sd) - Math.pow(hs, 2 * mu) * n(eta * y2 - eta * sd));
        double f = rebate * (Math.pow(hs, mu + lambda) * n(eta * z) + Math.pow(hs, mu - lambda)
                * n(eta * z - 2 * eta * lambda * sd));
        boolean call = phi > 0;
        boolean above = k > h;
        return switch (type) {
            case DOWN_IN -> call ? (above ? c + e : a - bb + d + e) : (above ? bb - c + d + e : a + e);
            case UP_IN -> call ? (above ? a + e : bb - c + d + e) : (above ? a - bb + d + e : c + e);
            case DOWN_OUT -> call ? (above ? a - c + f : bb - d + f) : (above ? a - bb + c - d + f : f);
            case UP_OUT -> call ? (above ? f : a - bb + c - d + f) : (above ? bb - d + f : a - c + f);
        };
    }

    public static double asianContinuous(double phi, double s, double k, double t, double r, double q, double v) {
        return gbs(phi, s, k, t, r, ((r - q) - v * v / 6) / 2, v / Math.sqrt(3));
    }

    public static double asianDiscrete(double phi, double s, double k, double t, double r, double q, double v,
                                       double[] fix) {
        int m = fix.length;
        double mean = 0.0;
        double sum = 0.0;
        for (int i = 0; i < m; i++) {
            mean += fix[i] / m;
            for (int j = 0; j < m; j++) {
                sum += Math.min(fix[i], fix[j]);
            }
        }
        double mm = Math.log(s) + (r - q - v * v / 2) * mean;
        double var = v * v * sum / ((double) m * m);
        double d1 = (mm - Math.log(k) + var) / Math.sqrt(var);
        double d2 = d1 - Math.sqrt(var);
        double fwd = Math.exp(mm + var / 2);
        return Math.exp(-r * t) * phi * (fwd * n(phi * d1) - k * n(phi * d2));
    }

    /** Goldman-Sosin-Gatto floating-strike lookback; {@code e} is the running minimum (call) or maximum (put). */
    public static double lookback(double phi, double s, double e, double t, double r, double q, double v) {
        double b = r - q;
        double sq = Math.sqrt(t);
        double a1 = (Math.log(s / e) + (b + v * v / 2) * t) / (v * sq);
        double a2 = a1 - v * sq;
        double reflect = Math.pow(s / e, -2 * b / (v * v));
        double k = s * Math.exp(-r * t) * v * v / (2 * b);
        if (phi > 0) {
            return s * Math.exp((b - r) * t) * n(a1) - e * Math.exp(-r * t) * n(a2)
                    + k * (reflect * n(-a1 + 2 * b * sq / v) - Math.exp(b * t) * n(-a1));
        }
        return -s * Math.exp((b - r) * t) * n(-a1) + e * Math.exp(-r * t) * n(-a2)
                + k * (-reflect * n(a1 - 2 * b * sq / v) + Math.exp(b * t) * n(a1));
    }

    public static double quanto(double phi, double s, double k, double t, double rd, double rf, double q, double v,
                                double fxVol, double rho) {
        return gbs(phi, s, k, t, rd, rf - q - rho * v * fxVol, v);
    }

    public static double chooser(double s, double k, double t, double r, double q, double v, double tc) {
        double b = r - q;
        double d = (Math.log(s / k) + (b + v * v / 2) * t) / (v * Math.sqrt(t));
        double y = (Math.log(s / k) + b * t + v * v * tc / 2) / (v * Math.sqrt(tc));
        double carry = s * Math.exp((b - r) * t);
        double disc = k * Math.exp(-r * t);
        return carry * n(d) - disc * n(d - v * Math.sqrt(t)) - carry * n(-y) + disc * n(-y + v * Math.sqrt(tc));
    }

    public static double kirk(double f1, double f2, double k, double t, double r, double v1, double v2, double rho) {
        double f = f2 / (f2 + k);
        double s = Math.sqrt(v1 * v1 - 2 * rho * v1 * v2 * f + v2 * v2 * f * f);
        double d1 = (Math.log(f1 / (f2 + k)) + s * s * t / 2) / (s * Math.sqrt(t));
        return Math.exp(-r * t) * (f1 * n(d1) - (f2 + k) * n(d1 - s * Math.sqrt(t)));
    }

    /** {price, M1, v_B} by lognormal moment matching [Levy92]. */
    public static double[] basket(double phi, double[] f, double[] w, double[] v, double[][] rho, double k, double t,
                                  double r) {
        double m1 = 0.0;
        double m2 = 0.0;
        for (int i = 0; i < f.length; i++) {
            m1 += w[i] * f[i];
            for (int j = 0; j < f.length; j++) {
                m2 += w[i] * w[j] * f[i] * f[j] * Math.exp(rho[i][j] * v[i] * v[j] * t);
            }
        }
        double vb = Math.sqrt(Math.log(m2 / (m1 * m1)) / t);
        return new double[] {gbs(phi, m1, k, t, r, 0.0, vb), m1, vb};
    }

    /** {american, european} on a CRR tree with Hull's probability (ruling E-A23). */
    public static double[] crr(double phi, double s, double k, double t, double r, double q, double v, int steps) {
        double dt = t / steps;
        double u = Math.exp(v * Math.sqrt(dt));
        double d = 1 / u;
        double p = (Math.exp((r - q) * dt) - d) / (u - d);
        if (!(p > 0.0 && p < 1.0)) {
            throw new QfError("E_DOMAIN", "tree probability is outside (0, 1)", "steps");
        }
        double disc = Math.exp(-r * dt);
        double[] am = new double[steps + 1];
        double[] eu = new double[steps + 1];
        for (int j = 0; j <= steps; j++) {
            am[j] = Math.max(phi * (s * Math.pow(u, steps - 2.0 * j) - k), 0.0);
            eu[j] = am[j];
        }
        for (int i = steps - 1; i >= 0; i--) {
            for (int j = 0; j <= i; j++) {
                eu[j] = disc * (p * eu[j] + (1 - p) * eu[j + 1]);
                double cont = disc * (p * am[j] + (1 - p) * am[j + 1]);
                am[j] = Math.max(cont, phi * (s * Math.pow(u, i - 2.0 * j) - k));
            }
        }
        return new double[] {am[0], eu[0]};
    }

    /** Barone-Adesi-Whaley [BAW87]; r = 0 is E_DOMAIN (ruling E-A22). */
    public static double baw(double phi, double s, double k, double t, double r, double q, double v) {
        if (!(r > 0.0)) {
            throw new QfError("E_DOMAIN", "BAW needs a positive rate (rulings E-A22, E-A30)", "rate");
        }
        double b = r - q;
        if (phi > 0 && b >= r) {
            return gbs(1.0, s, k, t, r, b, v);
        }
        double m = 2 * r / (v * v);
        double nn = 2 * b / (v * v);
        double kt = 1 - Math.exp(-r * t);
        double root = Math.sqrt((nn - 1) * (nn - 1) + 4 * m / kt);
        double qq = phi > 0 ? (-(nn - 1) + root) / 2 : (-(nn - 1) - root) / 2;
        DoubleUnaryOperator d1 = x -> (Math.log(x / k) + (b + v * v / 2) * t) / (v * Math.sqrt(t));
        DoubleUnaryOperator g = x -> phi * (x - k) - gbs(phi, x, k, t, r, b, v)
                - phi * (1 - Math.exp((b - r) * t) * n(phi * d1.applyAsDouble(x))) * x / qq;
        double lo;
        double hi;
        if (phi > 0) {
            lo = Math.log(k);
            hi = lo + 1;
            for (int i = 0; i < 200 && g.applyAsDouble(Math.exp(hi)) < 0; i++) {
                hi = lo + 2 * (hi - lo);
            }
        } else {
            hi = Math.log(k);
            lo = hi - 1;
            for (int i = 0; i < 200 && g.applyAsDouble(Math.exp(lo)) < 0; i++) {
                lo = hi - 2 * (hi - lo);
            }
        }
        double a = lo;
        double c = hi;
        boolean callSide = phi > 0;
        for (int i = 0; i < 2000; i++) {
            double mid = 0.5 * (a + c);
            if (mid <= a || mid >= c) {
                break;
            }
            boolean positive = g.applyAsDouble(Math.exp(mid)) >= 0;
            if (positive == callSide) {
                c = mid;
            } else {
                a = mid;
            }
        }
        double star = Math.exp(0.5 * (a + c));
        double coef = phi * (star / qq) * (1 - Math.exp((b - r) * t) * n(phi * d1.applyAsDouble(star)));
        if (phi > 0 ? s < star : s > star) {
            return gbs(phi, s, k, t, r, b, v) + coef * Math.pow(s / star, qq);
        }
        return phi * (s - k);
    }

    /** {price, delta, gamma} at the centre node of the reference backward-Euler scheme (ruling E-A23). */
    public static double[] fd(double phi, boolean american, double s, double k, double t, double r, double q, double v,
                              int nx, int nt, double width) {
        double h = width * v * Math.sqrt(t);
        double dx = 2 * h / (nx - 1);
        double dt = t / nt;
        double mu = r - q - v * v / 2;
        double[] x = new double[nx];
        double[] pay = new double[nx];
        double[] val = new double[nx];
        for (int i = 0; i < nx; i++) {
            x[i] = Math.log(s) - h + i * dx;
            pay[i] = Math.max(phi * (Math.exp(x[i]) - k), 0.0);
            val[i] = pay[i];
        }
        double lo = -dt * (v * v / (2 * dx * dx) - mu / (2 * dx));
        double di = 1 + dt * (v * v / (dx * dx) + r);
        double up = -dt * (v * v / (2 * dx * dx) + mu / (2 * dx));
        double[] cp = new double[nx];
        double[] dp = new double[nx];
        for (int step = 0; step < nt; step++) {
            double tau = (step + 1) * dt;
            double[] rhs = val.clone();
            for (int end : new int[] {0, nx - 1}) {
                rhs[end] = american ? pay[end]
                        : Math.max(phi * (Math.exp(x[end]) * Math.exp(-q * tau) - k * Math.exp(-r * tau)), 0.0);
            }
            // Thomas with identity end rows
            cp[0] = 0.0;
            dp[0] = rhs[0];
            for (int i = 1; i < nx - 1; i++) {
                double beta = di - lo * cp[i - 1];
                cp[i] = up / beta;
                dp[i] = (rhs[i] - lo * dp[i - 1]) / beta;
            }
            val[nx - 1] = rhs[nx - 1];
            for (int i = nx - 2; i >= 1; i--) {
                val[i] = dp[i] - cp[i] * val[i + 1];
            }
            val[0] = rhs[0];
            if (american) {
                for (int i = 0; i < nx; i++) {
                    val[i] = Math.max(val[i], pay[i]);
                }
            }
        }
        int c = (nx - 1) / 2;
        double first = (val[c + 1] - val[c - 1]) / (2 * dx);
        double second = (val[c + 1] - 2 * val[c] + val[c - 1]) / (dx * dx);
        return new double[] {val[c], first / s, (second - first) / (s * s)};
    }
}
