package org.quantforge.vol;

import java.util.List;
import org.quantforge.core.QfError;

/** SLV leverage on the fixed reference PDE grid of heston-family.md (ruling E-A14). */
public final class Slv {
    private Slv() {}

    public record Grid(long nx, long nv, long nt, double xMin, double xMax, double vMax) {
        public void check(double spot) {
            if (nx < 5 || nv < 5 || nt < 2) {
                throw new QfError("E_INPUT", "need nx, nv at least 5 and nt at least 2", "grid");
            }
            double s = Math.log(spot);
            if (!(xMin < s && s < xMax)) {
                throw new QfError("E_INPUT", "x_min < ln(spot) < x_max is needed", "grid");
            }
            if (!(vMax > 0.0)) {
                throw new QfError("E_DOMAIN", "v_max must be above 0", "grid");
            }
            if (nx > 1000 || nv > 1000 || nt > 10_000) {
                throw new QfError("E_LIMIT", "grid is above its limit", "grid");
            }
        }
    }

    public record Result(double[] x, double[] leverage, double mass) {}

    public static Result leverage(double spot, double t, double r, double q, Heston.Params h,
                                  List<Surfaces.Slice> slices, Grid g) {
        int nx = (int) g.nx();
        int nv = (int) g.nv();
        int nt = (int) g.nt();
        double dx = (g.xMax() - g.xMin()) / (nx - 1);
        double dv = g.vMax() / (nv + 1);
        double dt = t / nt;
        double[] x = new double[nx];
        for (int i = 0; i < nx; i++) {
            x[i] = g.xMin() + i * dx;
        }
        double[] v = new double[nv];
        for (int j = 0; j < nv; j++) {
            v[j] = (j + 1) * dv;
        }
        // start at t_1 = dt
        double lv0 = Surfaces.dupire(slices, new double[] {dt}, new double[] {0.0}).localVol()[0];
        double l0 = lv0 * lv0 / h.v0();
        double mx = Math.log(spot) + (r - q - l0 * h.v0() / 2.0) * dt;
        double mv = h.v0() + h.kappa() * (h.theta() - h.v0()) * dt;
        double sx = Math.max(Math.sqrt(l0 * h.v0() * dt), 2 * dx);
        double sv = Math.max(h.xi() * Math.sqrt(h.v0() * dt), 2 * dv);
        double rho = h.rho();
        double[][] p = new double[nx][nv];
        double total = 0.0;
        for (int i = 0; i < nx; i++) {
            for (int j = 0; j < nv; j++) {
                double a = (x[i] - mx) / sx;
                double b = (v[j] - mv) / sv;
                double z = (a * a - 2 * rho * a * b + b * b) / (1 - rho * rho);
                p[i][j] = Math.exp(-z / 2.0) / (2 * Math.PI * sx * sv * Math.sqrt(1 - rho * rho));
                total += p[i][j];
            }
        }
        double scale = 1.0 / (total * dx * dv);
        for (double[] row : p) {
            for (int j = 0; j < nv; j++) {
                row[j] *= scale;
            }
        }
        for (int n = 1; n < nt; n++) {
            double[] lev2 = leverage2(p, x, v, n * dt, spot, r, q, slices);
            // 1. mixed term, explicit, interior nodes
            double[][] f = new double[nx][nv];
            for (int i = 0; i < nx; i++) {
                for (int j = 0; j < nv; j++) {
                    f[i][j] = rho * h.xi() * Math.sqrt(lev2[i]) * v[j] * p[i][j];
                }
            }
            double[][] ps = new double[nx][];
            for (int i = 0; i < nx; i++) {
                ps[i] = p[i].clone();
            }
            for (int i = 1; i < nx - 1; i++) {
                for (int j = 1; j < nv - 1; j++) {
                    ps[i][j] = p[i][j] + dt * (f[i + 1][j + 1] - f[i + 1][j - 1] - f[i - 1][j + 1] + f[i - 1][j - 1])
                            / (4 * dx * dv);
                }
            }
            // 2. x, implicit per j, Dirichlet ends
            double[] mu = new double[nx];
            double[] sd = new double[nx];
            double[] col = new double[nx];
            for (int j = 0; j < nv; j++) {
                for (int i = 0; i < nx; i++) {
                    mu[i] = r - q - lev2[i] * v[j] / 2.0;
                    sd[i] = lev2[i] * v[j];
                    col[i] = ps[i][j];
                }
                double[][] m = rows(mu, sd, dx, dt, false);
                m[0][1] = 1.0;
                m[0][2] = 0.0;
                m[nx - 1][0] = 0.0;
                m[nx - 1][1] = 1.0;
                col[0] = 0.0;
                col[nx - 1] = 0.0;
                double[] out = thomas(m, col);
                for (int i = 0; i < nx; i++) {
                    ps[i][j] = out[i];
                }
            }
            // 3. v, implicit per i, no-flux
            double[] muv = new double[nv];
            double[] sdv = new double[nv];
            for (int j = 0; j < nv; j++) {
                muv[j] = h.kappa() * (h.theta() - v[j]);
                sdv[j] = h.xi() * h.xi() * v[j];
            }
            double[][] mvRows = rows(muv, sdv, dv, dt, true);
            for (int i = 0; i < nx; i++) {
                p[i] = thomas(mvRows, ps[i]);
                // 4. floor
                for (int j = 0; j < nv; j++) {
                    p[i][j] = Math.max(p[i][j], 0.0);
                }
            }
        }
        double[] lev2 = leverage2(p, x, v, t, spot, r, q, slices);
        double[] lev = new double[nx];
        double mass = 0.0;
        for (int i = 0; i < nx; i++) {
            lev[i] = Math.sqrt(lev2[i]);
            for (int j = 0; j < nv; j++) {
                mass += p[i][j];
            }
        }
        return new Result(x, lev, mass * dx * dv);
    }

    /** L_i^2 = sigma_LV(t, x_i)^2 / E_i with the smooth conditional-variance estimate. */
    static double[] leverage2(double[][] p, double[] x, double[] v, double t, double spot, double r, double q,
                              List<Surfaces.Slice> slices) {
        int nx = x.length;
        double[] m = new double[nx];
        double[] e = new double[nx];
        double max = 0.0;
        double sm = 0.0;
        double se = 0.0;
        for (int i = 0; i < nx; i++) {
            for (int j = 0; j < v.length; j++) {
                m[i] += p[i][j];
                e[i] += v[j] * p[i][j];
            }
            max = Math.max(max, m[i]);
            sm += m[i];
            se += e[i];
        }
        double eps = 1e-10 * max;
        double ebar = se / sm;
        double lnF = Math.log(spot) + (r - q) * t;
        double[] ts = new double[nx];
        double[] ks = new double[nx];
        for (int i = 0; i < nx; i++) {
            ts[i] = t;
            ks[i] = x[i] - lnF;
        }
        double[] lv = Surfaces.dupire(slices, ts, ks).localVol();
        double[] out = new double[nx];
        for (int i = 0; i < nx; i++) {
            out[i] = lv[i] * lv[i] / ((e[i] + eps * ebar) / (m[i] + eps));
        }
        return out;
    }

    /** Rows {lower, diag, upper} of (I - dt A), A p = -D[mu p] + (1/2) D2[s p]. */
    static double[][] rows(double[] mu, double[] s, double h, double dt, boolean noFlux) {
        int n = mu.length;
        double[] face = new double[n + 1];
        for (int k = 1; k < n; k++) {
            face[k] = (mu[k - 1] + mu[k]) / 2.0;
        }
        face[0] = noFlux ? 0.0 : mu[0];
        face[n] = noFlux ? 0.0 : mu[n - 1];
        double h2 = h * h;
        double[][] m = new double[n][3];
        for (int k = 0; k < n; k++) {
            boolean end = k == 0 || k == n - 1;
            m[k][1] = 1.0 + dt * s[k] / ((noFlux && end) ? 2.0 * h2 : h2);
            if (k > 0) {
                m[k][0] = -dt * s[k - 1] / (2.0 * h2) - dt * Math.max(face[k], 0.0) / h;
            }
            if (k < n - 1) {
                m[k][2] = -dt * s[k + 1] / (2.0 * h2) + dt * Math.min(face[k + 1], 0.0) / h;
            }
            m[k][1] += dt * (Math.max(face[k + 1], 0.0) - Math.min(face[k], 0.0)) / h;
        }
        return m;
    }

    /** Thomas algorithm, no pivoting. */
    static double[] thomas(double[][] m, double[] d) {
        int n = d.length;
        double[] c = new double[n];
        double[] y = new double[n];
        double beta = m[0][1];
        c[0] = m[0][2] / beta;
        y[0] = d[0] / beta;
        for (int k = 1; k < n; k++) {
            beta = m[k][1] - m[k][0] * c[k - 1];
            c[k] = k < n - 1 ? m[k][2] / beta : 0.0;
            y[k] = (d[k] - m[k][0] * y[k - 1]) / beta;
        }
        for (int k = n - 2; k >= 0; k--) {
            y[k] -= c[k] * y[k + 1];
        }
        return y;
    }
}
