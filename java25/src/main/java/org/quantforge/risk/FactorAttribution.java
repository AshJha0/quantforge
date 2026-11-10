package org.quantforge.risk;

import org.quantforge.core.Finite;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.QfError;

/** Use case 4: return attribution by OLS with an intercept (use-cases.md). */
public final class FactorAttribution {
    private FactorAttribution() {}

    public record Result(double alpha, double[] betas, double[] contributions, double meanReturn, double rSquared,
                         double residualVol, double[] betaSe) {}

    public static Result attribute(double[] y, double[][] f, int names) {
        Finite.check("portfolio_returns", y);
        int t = y.length;
        if (f.length != t) {
            throw new QfError("E_INPUT", "factor_returns must have one row per return", "factor_returns");
        }
        int k = names;
        for (double[] row : f) {
            Finite.check("factor_returns", row);
            if (row.length != k) {
                throw new QfError("E_INPUT", "factor_returns rows must match factor_names", "factor_returns");
            }
        }
        if (t < k + 2) {
            throw new QfError("E_INPUT", "need T >= K + 2", "portfolio_returns");
        }
        int p = k + 1;
        double[][] x = new double[t][p];
        for (int i = 0; i < t; i++) {
            x[i][0] = 1.0;
            System.arraycopy(f[i], 0, x[i], 1, k);
        }
        double[] sv = LinearAlgebra.singularValues(x);
        double max = 0.0;
        double min = Double.POSITIVE_INFINITY;
        for (double s : sv) {
            max = Math.max(max, s);
            min = Math.min(min, s);
        }
        if (sv.length < p || min < 1e-12 * max) {
            throw new QfError("E_DOMAIN", "factors are collinear", "factor_returns");
        }
        // Householder QR: R (p x p) and Q'y.
        double[][] a = new double[t][];
        for (int i = 0; i < t; i++) {
            a[i] = x[i].clone();
        }
        double[] qty = y.clone();
        for (int j = 0; j < p; j++) {
            double norm = 0.0;
            for (int i = j; i < t; i++) {
                norm = Math.hypot(norm, a[i][j]);
            }
            double alpha = a[j][j] > 0 ? -norm : norm;
            double[] v = new double[t];
            for (int i = j; i < t; i++) {
                v[i] = a[i][j];
            }
            v[j] -= alpha;
            double vv = 0.0;
            for (int i = j; i < t; i++) {
                vv += v[i] * v[i];
            }
            if (vv == 0.0) {
                continue;
            }
            for (int c = j; c < p; c++) {
                double s = 0.0;
                for (int i = j; i < t; i++) {
                    s += v[i] * a[i][c];
                }
                s = 2.0 * s / vv;
                for (int i = j; i < t; i++) {
                    a[i][c] -= s * v[i];
                }
            }
            double s = 0.0;
            for (int i = j; i < t; i++) {
                s += v[i] * qty[i];
            }
            s = 2.0 * s / vv;
            for (int i = j; i < t; i++) {
                qty[i] -= s * v[i];
            }
        }
        double[] b = new double[p];
        for (int j = p - 1; j >= 0; j--) {
            double s = qty[j];
            for (int c = j + 1; c < p; c++) {
                s -= a[j][c] * b[c];
            }
            b[j] = s / a[j][j];
        }
        // R^-1, then (X'X)^-1 = R^-1 R^-T.
        double[][] rinv = new double[p][p];
        for (int col = 0; col < p; col++) {
            for (int j = p - 1; j >= 0; j--) {
                double s = j == col ? 1.0 : 0.0;
                for (int c = j + 1; c < p; c++) {
                    s -= a[j][c] * rinv[c][col];
                }
                rinv[j][col] = s / a[j][j];
            }
        }
        double mean = 0.0;
        for (double v : y) {
            mean += v;
        }
        mean /= t;
        double ssr = 0.0;
        double sst = 0.0;
        for (int i = 0; i < t; i++) {
            double fit = 0.0;
            for (int j = 0; j < p; j++) {
                fit += x[i][j] * b[j];
            }
            ssr += (y[i] - fit) * (y[i] - fit);
            sst += (y[i] - mean) * (y[i] - mean);
        }
        double resVol = Math.sqrt(ssr / (t - k - 1));
        double[] betas = new double[k];
        double[] contrib = new double[k];
        double[] se = new double[k];
        for (int j = 0; j < k; j++) {
            betas[j] = b[j + 1];
            double fm = 0.0;
            for (int i = 0; i < t; i++) {
                fm += f[i][j];
            }
            contrib[j] = betas[j] * fm / t;
            double d = 0.0;
            for (int c = 0; c < p; c++) {
                d += rinv[j + 1][c] * rinv[j + 1][c];
            }
            se[j] = Math.sqrt(resVol * resVol * d);
        }
        return new Result(b[0], betas, contrib, mean, 1.0 - ssr / sst, resVol, se);
    }
}
