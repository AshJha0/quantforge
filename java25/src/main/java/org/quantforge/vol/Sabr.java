package org.quantforge.vol;

import org.quantforge.core.Finite;

import java.util.ArrayList;
import java.util.List;
import org.quantforge.core.QfError;

/** Hagan SABR, its density check and fit, and the arbitrage-free recipe (sabr.md). */
public final class Sabr {
    private Sabr() {}

    public record Params(double alpha, double beta, double rho, double nu) {}

    public static void check(double t, Params p, double f, double[] x) {
        Finite.check("t", t);
        Finite.check("f", f);
        Finite.check("x", x);
        if (t <= 0.0 || p.alpha() <= 0.0 || p.beta() < 0.0 || p.beta() > 1.0 || Math.abs(p.rho()) >= 1.0 || p.nu() < 0.0
                || f <= 0.0) {
            throw new QfError("E_DOMAIN", "sabr inputs");
        }
        for (double v : x) {
            if (v <= 0.0) {
                throw new QfError("E_DOMAIN", "shifted strike is not positive");
            }
        }
    }

    /** {@code f}, {@code x} are shifted. */
    public static double hagan(double f, double x, double t, Params p) {
        Finite.check("f", f);
        Finite.check("x", x);
        Finite.check("t", t);
        double a = p.alpha();
        double b = p.beta();
        double rho = p.rho();
        double nu = p.nu();
        double ob = 1.0 - b;
        double bigA = Math.pow(f * x, ob);
        double root = Math.sqrt(bigA);
        double l = Math.log(f / x);
        double c = ob * ob * l * l;
        double z = nu / a * root * l;
        double m;
        if (Math.abs(z) < 1e-7) {
            m = 1.0 - rho * z / 2.0 - (3.0 * rho * rho - 2.0) * z * z / 12.0;
        } else {
            m = z / Math.log((Math.sqrt(1.0 - 2.0 * rho * z + z * z) + z - rho) / (1.0 - rho));
        }
        double den = root * (1.0 + c / 24.0 + c * c / 1920.0);
        double h = 1.0 + t * (ob * ob * a * a / (24.0 * bigA) + rho * b * nu * a / (4.0 * root)
                + (2.0 - 3.0 * rho * rho) * nu * nu / 24.0);
        return a * m * h / den;
    }

    public static double[] density(double f, double[] x, double t, Params p, double h) {
        Finite.check("f", f);
        Finite.check("x", x);
        Finite.check("t", t);
        Finite.check("h", h);
        double[] out = new double[x.length];
        for (int i = 0; i < x.length; i++) {
            out[i] = (call(f, x[i] + h, t, p) - 2.0 * call(f, x[i], t, p) + call(f, x[i] - h, t, p)) / (h * h);
        }
        return out;
    }

    private static double call(double f, double x, double t, Params p) {
        return Black.lognormal(1.0, f, x, t, 1.0, hagan(f, x, t, p));
    }

    public record SabrFit(double alpha, double rho, double nu, double rmse) {}

    public static SabrFit calibrate(double f, double t, double beta, double[] x, double[] vols, double[] wt) {
        Finite.check("f", f);
        Finite.check("t", t);
        Finite.check("beta", beta);
        Finite.check("x", x);
        Finite.check("vols", vols);
        Finite.check("wt", wt);
        int n = x.length;
        double atm = vols[0];
        double near = Double.POSITIVE_INFINITY;
        for (int i = 0; i < n; i++) {
            if (Math.abs(x[i] - f) < near) {
                near = Math.abs(x[i] - f);
                atm = vols[i];
            }
        }
        double a0 = atm * Math.pow(f, 1.0 - beta);
        List<double[]> starts = new ArrayList<>();
        for (double af : new double[] {0.7, 1.0, 1.4}) {
            for (double rho : new double[] {-0.7, -0.3, 0.0, 0.3, 0.7}) {
                for (double nu : new double[] {0.05, 0.3, 0.8, 1.5}) {
                    starts.add(new double[] {Math.log(af * a0), Fit.atanh(rho), Math.log(nu)});
                }
            }
        }
        double[] p = Fit.best(q -> {
            Params s = new Params(Math.exp(q[0]), beta, Math.tanh(q[1]), Math.exp(q[2]));
            double[] r = new double[n];
            for (int i = 0; i < n; i++) {
                r[i] = Math.sqrt(wt == null ? 1.0 : wt[i]) * (hagan(f, x[i], t, s) - vols[i]);
            }
            return r;
        }, starts);
        Params s = new Params(Math.exp(p[0]), beta, Math.tanh(p[1]), Math.exp(p[2]));
        double sum = 0.0;
        double sw = 0.0;
        for (int i = 0; i < n; i++) {
            double w = wt == null ? 1.0 : wt[i];
            double e = hagan(f, x[i], t, s) - vols[i];
            sum += w * e * e;
            sw += w;
        }
        return new SabrFit(s.alpha(), s.rho(), s.nu(), Math.sqrt(sum / sw));
    }

    public record ArbFree(double[] calls, Double[] vols, double mass, double mean, double absorbed, double minDensity) {}

    /** {@code f0}, {@code x} are shifted. */
    public static ArbFree arbFree(double f0, double t, Params p, int cells, int below, int steps, double[] x) {
        Finite.check("f0", f0);
        Finite.check("t", t);
        Finite.check("x", x);
        double alpha = p.alpha();
        double beta = p.beta();
        double rho = p.rho();
        double nu = p.nu();
        int n = cells;
        double h = f0 / (below - 0.5);
        double uMax = n * h;
        for (double v : x) {
            if (v >= uMax) {
                throw new QfError("E_INPUT", "strike is at or beyond the top of the grid");
            }
        }
        double ob = 1.0 - beta;
        double[] u = new double[n];
        double[] dsq = new double[n];
        double[] g = new double[n];
        double f1 = Math.pow(f0, ob);
        double fb = Math.pow(f0, beta);
        for (int j = 0; j < n; j++) {
            u[j] = (j + 0.5) * h;
            double z = (Math.pow(u[j], ob) - f1) / ob;
            dsq[j] = (alpha * alpha + 2.0 * rho * alpha * nu * z + nu * nu * z * z) * Math.pow(u[j], 2.0 * beta);
            if (beta == 0.0) {
                g[j] = 0.0;
            } else if (j == below - 1) {
                g[j] = beta * Math.pow(f0, beta - 1.0);
            } else {
                g[j] = (Math.pow(u[j], beta) - fb) / (u[j] - f0);
            }
        }
        double dt = t / steps;
        double lambda = dt / (h * h);
        double[] q = new double[n];
        q[below - 1] = 1.0 / h;
        double[] m = new double[n];
        double[] cp = new double[n];
        double pl = 0.0;
        double pr = 0.0;
        double coef = rho * nu * alpha;
        for (int s = 1; s <= steps; s++) {
            double time = s * dt;
            for (int j = 0; j < n; j++) {
                m[j] = dsq[j] * Math.exp(coef * g[j] * time) / 2.0;
            }
            // Row j: -l m[j-1] q[j-1] + (1 + 2 l m[j]) q[j] - l m[j+1] q[j+1] = old, with 3 l m at both ends.
            double diag = 1.0 + 3.0 * lambda * m[0];
            cp[0] = -lambda * m[1] / diag;
            q[0] = q[0] / diag;
            for (int j = 1; j < n; j++) {
                double lower = -lambda * m[j - 1];
                double d = (j == n - 1 ? 1.0 + 3.0 * lambda * m[j] : 1.0 + 2.0 * lambda * m[j]) - lower * cp[j - 1];
                cp[j] = j == n - 1 ? 0.0 : -lambda * m[j + 1] / d;
                q[j] = (q[j] - lower * q[j - 1]) / d;
            }
            for (int j = n - 2; j >= 0; j--) {
                q[j] -= cp[j] * q[j + 1];
            }
            pl += 2.0 * dt * m[0] * q[0] / h;
            pr += 2.0 * dt * m[n - 1] * q[n - 1] / h;
        }
        double[] calls = new double[x.length];
        Double[] vols = new Double[x.length];
        for (int i = 0; i < x.length; i++) {
            int c = Math.min((int) Math.floor(x[i] / h), n - 1); // 0-based holding cell.
            double e = (c + 1) * h;
            double sum = q[c] * (e - x[i]) * (e - x[i]) / 2.0;
            for (int j = c + 1; j < n; j++) {
                sum += (u[j] - x[i]) * q[j] * h;
            }
            sum += (uMax - x[i]) * pr;
            calls[i] = sum;
            vols[i] = sum > Math.max(f0 - x[i], 0.0) && sum < f0 ? Double.valueOf(Black.solve(false, 1.0, f0, x[i], t, 1.0, sum)) : null;
        }
        double mass = 0.0;
        double mean = 0.0;
        double min = Double.POSITIVE_INFINITY;
        for (int j = 0; j < n; j++) {
            mass += q[j] * h;
            mean += u[j] * q[j] * h;
            min = Math.min(min, q[j]);
        }
        return new ArbFree(calls, vols, mass + pl + pr, mean + uMax * pr, pl, min);
    }
}
