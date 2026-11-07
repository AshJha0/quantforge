package org.quantforge.vol;

import java.util.function.Function;
import org.quantforge.core.QfError;

/** Levenberg-Marquardt on unconstrained parameters, from many starts. Domains are kept by the caller's transform. */
final class Fit {
    private Fit() {}

    private static double cost(double[] r) {
        double s = 0.0;
        for (double e : r) {
            s += e * e;
        }
        return Double.isFinite(s) ? s : Double.POSITIVE_INFINITY;
    }

    static double atanh(double x) {
        return 0.5 * Math.log((1.0 + x) / (1.0 - x));
    }

    private static double[] solve(double[][] a, double[] b) {
        int n = b.length;
        for (int c = 0; c < n; c++) {
            int p = c;
            for (int i = c + 1; i < n; i++) {
                if (Math.abs(a[i][c]) > Math.abs(a[p][c])) {
                    p = i;
                }
            }
            double[] row = a[c];
            a[c] = a[p];
            a[p] = row;
            double tmp = b[c];
            b[c] = b[p];
            b[p] = tmp;
            if (a[c][c] == 0.0) {
                return null;
            }
            for (int i = c + 1; i < n; i++) {
                double m = a[i][c] / a[c][c];
                for (int j = c; j < n; j++) {
                    a[i][j] -= m * a[c][j];
                }
                b[i] -= m * b[c];
            }
        }
        double[] x = new double[n];
        for (int i = n - 1; i >= 0; i--) {
            double s = b[i];
            for (int j = i + 1; j < n; j++) {
                s -= a[i][j] * x[j];
            }
            x[i] = s / a[i][i];
        }
        return x;
    }

    private static double[] descend(Function<double[], double[]> res, double[] start) {
        int n = start.length;
        double[] p = start.clone();
        double[] r = res.apply(p);
        double c = cost(r);
        double mu = 1e-3;
        for (int it = 0; it < 500 && c > 1e-30; it++) {
            double[][] jac = new double[n][];
            for (int k = 0; k < n; k++) {
                double h = 1e-6 * Math.max(1.0, Math.abs(p[k]));
                double[] u = p.clone();
                double[] d = p.clone();
                u[k] += h;
                d[k] -= h;
                double[] ru = res.apply(u);
                double[] rd = res.apply(d);
                jac[k] = new double[r.length];
                for (int i = 0; i < r.length; i++) {
                    jac[k][i] = (ru[i] - rd[i]) / (2.0 * h);
                }
            }
            double[][] jtj = new double[n][n];
            double[] g = new double[n];
            for (int a = 0; a < n; a++) {
                for (int b = 0; b < n; b++) {
                    for (int i = 0; i < r.length; i++) {
                        jtj[a][b] += jac[a][i] * jac[b][i];
                    }
                }
                for (int i = 0; i < r.length; i++) {
                    g[a] -= jac[a][i] * r[i];
                }
            }
            boolean moved = false;
            while (mu < 1e14 && !moved) {
                double[][] m = new double[n][];
                for (int a = 0; a < n; a++) {
                    m[a] = jtj[a].clone();
                    m[a][a] += mu * Math.max(jtj[a][a], 1e-12);
                }
                double[] step = solve(m, g.clone());
                if (step != null) {
                    double[] q = p.clone();
                    for (int a = 0; a < n; a++) {
                        q[a] += step[a];
                    }
                    double[] rq = res.apply(q);
                    double cq = cost(rq);
                    if (cq < c) {
                        p = q;
                        r = rq;
                        c = cq;
                        mu = Math.max(mu / 5.0, 1e-14);
                        moved = true;
                    }
                }
                if (!moved) {
                    mu *= 4.0;
                }
            }
            if (!moved) {
                break;
            }
        }
        return p;
    }

    /** The best end point over all starts. */
    static double[] best(Function<double[], double[]> res, Iterable<double[]> starts) {
        double[] best = null;
        double bestCost = Double.POSITIVE_INFINITY;
        for (double[] s : starts) {
            double[] p = descend(res, s);
            double c = cost(res.apply(p));
            if (c < bestCost) {
                bestCost = c;
                best = p;
            }
        }
        if (best == null) {
            throw new QfError("E_NON_FINITE", "the fit's cost is not finite from any start");
        }
        return best;
    }
}
