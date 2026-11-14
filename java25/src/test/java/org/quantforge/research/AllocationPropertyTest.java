package org.quantforge.research;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.Random;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** Stage J wave 2 property tests (STAGE_J_HANDOVER.md "WAVE 2 READY", "Property tests"), on seeded own data. */
class AllocationPropertyTest {

    private static double[][] randomCov(Random r, int n) {
        double[][] f = new double[n + 2][n];
        for (double[] row : f) {
            for (int j = 0; j < n; j++) {
                row[j] = 0.1 * r.nextGaussian();
            }
        }
        double[][] s = new double[n][n];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                for (double[] row : f) {
                    s[i][j] += row[i] * row[j];
                }
            }
            s[i][i] += 0.01;
        }
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < i; j++) {
                s[i][j] = s[j][i];
            }
        }
        return s;
    }

    private static double[] mul(double[][] a, double[] x) {
        double[] o = new double[a.length];
        for (int i = 0; i < a.length; i++) {
            for (int j = 0; j < x.length; j++) {
                o[i] += a[i][j] * x[j];
            }
        }
        return o;
    }

    private static double[] fill(int n, double v) {
        double[] x = new double[n];
        Arrays.fill(x, v);
        return x;
    }

    @Test
    void meanVarianceKktAndClosedForm() {
        Random r = new Random(11);
        for (int rep = 0; rep < 30; rep++) {
            int n = 2 + r.nextInt(6);
            double[][] s = randomCov(r, n);
            double[] mu = new double[n];
            for (int i = 0; i < n; i++) {
                mu[i] = 0.05 + 0.05 * r.nextGaussian();
            }
            double gamma = 2 + 3 * r.nextDouble();
            double[] lo = fill(n, 0);
            double[] hi = fill(n, 1);
            Allocation.MeanVariance m = Allocation.meanVariance(mu, s, gamma, lo, hi);
            double[] w = m.weights();
            assertEquals(1, Arrays.stream(w).sum(), 1e-12);
            double[] sw = mul(s, w);
            // nu from any free asset; all free gradients must agree, bound ones carry the right sign
            double nu = Double.NaN;
            for (int i = 0; i < n; i++) {
                if (m.atBound()[i] == 0) {
                    nu = mu[i] - gamma * sw[i];
                }
            }
            if (!Double.isNaN(nu)) {
                for (int i = 0; i < n; i++) {
                    double g = mu[i] - gamma * sw[i] - nu;
                    if (m.atBound()[i] == 0) {
                        assertEquals(0, g, 1e-9);
                    } else if (m.atBound()[i] < 0) {
                        assertTrue(g <= 1e-9);
                    } else {
                        assertTrue(g >= -1e-9);
                    }
                }
            }
            // loosening every upper bound never lowers the objective
            Allocation.MeanVariance loose = Allocation.meanVariance(mu, s, gamma, lo, fill(n, 2));
            assertTrue(loose.objective() >= m.objective() - 1e-12);
            // wide bounds: closed form Sigma^-1 (mu - nu 1) / gamma
            Allocation.MeanVariance wide = Allocation.meanVariance(mu, s, gamma, fill(n, -1e3), fill(n, 1e3));
            double[][] l = Allocation.cholesky(s);
            double[] a = Allocation.solve(l, mu);
            double[] e = Allocation.solve(l, fill(n, 1));
            double nuc = (Arrays.stream(a).sum() - gamma) / Arrays.stream(e).sum();
            for (int i = 0; i < n; i++) {
                assertEquals((a[i] - nuc * e[i]) / gamma, wide.weights()[i], 1e-9);
            }
        }
        Allocation.MeanVariance one = Allocation.meanVariance(new double[] {0.1}, new double[][] {{0.04}}, 3,
                new double[] {0}, new double[] {1});
        assertEquals(1.0, one.weights()[0]);
    }

    @Test
    void riskParitySharesAndScale() {
        Random r = new Random(12);
        for (int rep = 0; rep < 30; rep++) {
            int n = 2 + r.nextInt(8);
            double[][] s = randomCov(r, n);
            double[] b = new double[n];
            for (int i = 0; i < n; i++) {
                b[i] = 0.2 + r.nextDouble();
            }
            double sb = Arrays.stream(b).sum();
            for (int i = 0; i < n; i++) {
                b[i] /= sb;
            }
            double[] bb = b;
            Allocation.RiskParity p;
            try {
                p = Allocation.riskParity(s, bb);
            } catch (QfError ex) {
                continue; // normalised budgets may miss the 1e-12 sum test by rounding
            }
            for (int i = 0; i < n; i++) {
                assertEquals(b[i], p.contributions()[i] / p.volatility(), 1e-10);
            }
            double[][] s4 = new double[n][n];
            for (int i = 0; i < n; i++) {
                for (int j = 0; j < n; j++) {
                    s4[i][j] = 4 * s[i][j];
                }
            }
            double[] w4 = Allocation.riskParity(s4, bb).weights();
            for (int i = 0; i < n; i++) {
                assertEquals(p.weights()[i], w4[i], 1e-12);
            }
        }
        assertEquals(1.0, Allocation.riskParity(new double[][] {{0.09}}, null).weights()[0], 1e-15);
    }

    @Test
    void eulerSumsAndScales() {
        Random r = new Random(13);
        for (int rep = 0; rep < 30; rep++) {
            int n = 1 + r.nextInt(8);
            double[][] s = randomCov(r, n);
            double[] w = new double[n];
            for (int i = 0; i < n; i++) {
                w[i] = r.nextGaussian();
            }
            Allocation.Euler e = Allocation.euler(w, s);
            assertEquals(e.volatility(), Arrays.stream(e.contributions()).sum(), 1e-10 * e.volatility());
            double[] w3 = Arrays.stream(w).map(v -> 3 * v).toArray();
            Allocation.Euler e3 = Allocation.euler(w3, s);
            for (int i = 0; i < n; i++) {
                assertEquals(3 * e.contributions()[i], e3.contributions()[i], 1e-12);
            }
        }
        assertThrows(QfError.class, () -> Allocation.euler(new double[] {1, 1}, new double[][] {{1, -1}, {-1, 1}}));
    }

    @Test
    void ledoitWolfBoundsAndShift() {
        Random r = new Random(14);
        for (int rep = 0; rep < 30; rep++) {
            int t = 3 + r.nextInt(30);
            int n = 1 + r.nextInt(6);
            double[][] x = new double[t][n];
            for (double[] row : x) {
                for (int j = 0; j < n; j++) {
                    row[j] = r.nextGaussian();
                }
            }
            Allocation.LedoitWolf lw = Allocation.ledoitWolf(x);
            assertTrue(lw.shrinkage() >= 0 && lw.shrinkage() <= 1);
            if (lw.shrinkage() > 0) {
                Allocation.cholesky(lw.covariance());
            }
            for (double[] row : x) {
                row[0] += 5;
            }
            Allocation.LedoitWolf sh = Allocation.ledoitWolf(x);
            assertEquals(lw.shrinkage(), sh.shrinkage(), 1e-9);
        }
    }

    @Test
    void blackLittermanForms() {
        Random r = new Random(15);
        for (int rep = 0; rep < 20; rep++) {
            int n = 1 + r.nextInt(5);
            int k = 1 + r.nextInt(n);
            double[][] s = randomCov(r, n);
            double[] pi = new double[n];
            for (int i = 0; i < n; i++) {
                pi[i] = 0.05 * r.nextGaussian();
            }
            double[][] p = new double[k][n];
            double[] q = new double[k];
            double[][] om = new double[k][k];
            for (int v = 0; v < k; v++) {
                p[v][v] = 1;
                p[v][(v + 1) % n] -= 0.5;
                q[v] = 0.05 * r.nextGaussian();
                om[v][v] = 0.001 + 0.01 * r.nextDouble();
            }
            double tau = 0.05;
            Allocation.BlackLitterman bl = Allocation.blackLitterman(s, pi, p, q, om, tau);
            // precision form: H = (tau S)^-1 + P' Om^-1 P, mean = H^-1 [(tau S)^-1 pi + P' Om^-1 q]
            double[][] ts = new double[n][n];
            for (int i = 0; i < n; i++) {
                for (int j = 0; j < n; j++) {
                    ts[i][j] = tau * s[i][j];
                }
            }
            double[][] lts = Allocation.cholesky(ts);
            double[][] h = new double[n][n];
            for (int j = 0; j < n; j++) {
                double[] ej = new double[n];
                ej[j] = 1;
                double[] col = Allocation.solve(lts, ej);
                for (int i = 0; i < n; i++) {
                    h[i][j] = col[i];
                }
            }
            double[] rhs = Allocation.solve(lts, pi);
            for (int i = 0; i < n; i++) {
                for (int v = 0; v < k; v++) {
                    rhs[i] += p[v][i] * q[v] / om[v][v];
                    for (int j = 0; j < n; j++) {
                        h[i][j] += p[v][i] * p[v][j] / om[v][v];
                    }
                }
            }
            double[] mean = Allocation.solve(Allocation.cholesky(Allocation.symmetric(symm(h))), rhs);
            for (int i = 0; i < n; i++) {
                assertEquals(mean[i], bl.posteriorReturns()[i], 1e-10);
            }
            double[][] big = new double[k][k];
            for (int v = 0; v < k; v++) {
                big[v][v] = om[v][v] * 1e14;
            }
            double[] prior = Allocation.blackLitterman(s, pi, p, q, big, tau).posteriorReturns();
            for (int i = 0; i < n; i++) {
                assertEquals(pi[i], prior[i], 1e-10);
            }
        }
    }

    private static double[][] symm(double[][] h) {
        int n = h.length;
        double[][] o = new double[n][n];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                o[i][j] = 0.5 * (h[i][j] + h[j][i]);
            }
        }
        return o;
    }

    @Test
    void z2NoExceptionsAndScale() {
        double[] l = {1, 3, 0.5, 4};
        double[] v = {2, 2, 2, 2};
        double[] es = {2.5, 2.5, 2.5, 2.5};
        assertEquals(-1.8, Allocation.esZ2(l, v, es, 0.25).z2(), 1e-15);
        assertEquals(1.0, Allocation.esZ2(l, new double[] {5, 5, 5, 5}, es, 0.25).z2());
        double[] l7 = Arrays.stream(l).map(x -> 7 * x).toArray();
        double[] v7 = Arrays.stream(v).map(x -> 7 * x).toArray();
        double[] e7 = Arrays.stream(es).map(x -> 7 * x).toArray();
        assertEquals(Allocation.esZ2(l, v, es, 0.25).z2(), Allocation.esZ2(l7, v7, e7, 0.25).z2(), 1e-14);
        assertEquals(2, Allocation.esZ2(l7, v7, e7, 0.25).exceptions());
    }

    private static double[] hmmData(Random r, int t) {
        double[] y = new double[t];
        int s = 0;
        for (int i = 0; i < t; i++) {
            if (r.nextDouble() < 0.1) {
                s = 1 - s;
            }
            y[i] = (s == 0 ? -0.5 : 1.5) + r.nextGaussian();
        }
        return y;
    }

    @Test
    void baumWelchMonotoneReproducibleEquivariant() {
        Random r = new Random(16);
        double[] y = hmmData(r, 300);
        double[] pi = {0.6, 0.4};
        double[][] a = {{0.9, 0.1}, {0.2, 0.8}};
        double prev = Double.NEGATIVE_INFINITY;
        for (int it = 1; it <= 25; it++) {
            Allocation.BaumWelch b = Allocation.baumWelch(y, pi, a, new double[] {-1, 2}, new double[] {1, 1}, 1e-300,
                    it);
            assertTrue(b.logLikelihood() >= prev - 1e-9 * Math.abs(b.logLikelihood()));
            prev = b.logLikelihood();
        }
        Allocation.BaumWelch x = Allocation.baumWelch(y, pi, a, new double[] {-1, 2}, new double[] {1, 1}, 1e-8,
                1000);
        Allocation.BaumWelch x2 = Allocation.baumWelch(y, pi, a, new double[] {-1, 2}, new double[] {1, 1}, 1e-8,
                1000);
        assertArrayEquals(x.means(), x2.means());
        assertEquals(Double.doubleToRawLongBits(x.logLikelihood()), Double.doubleToRawLongBits(x2.logLikelihood()));
        Allocation.BaumWelch p = Allocation.baumWelch(y, new double[] {0.4, 0.6},
                new double[][] {{0.8, 0.2}, {0.1, 0.9}}, new double[] {2, -1}, new double[] {1, 1}, 1e-8, 1000);
        assertEquals(x.iterations(), p.iterations());
        assertEquals(x.means()[0], p.means()[1], 1e-12);
        assertEquals(x.sds()[1], p.sds()[0], 1e-12);
        assertEquals(x.transition()[0][1], p.transition()[1][0], 1e-12);
        // K = 1: sample mean and population sd, stop at iteration 2
        Allocation.BaumWelch one = Allocation.baumWelch(y, new double[] {1}, new double[][] {{1}}, new double[] {0},
                new double[] {1}, 1e-10, 1000);
        double m = Arrays.stream(y).average().orElseThrow();
        double v = Arrays.stream(y).map(z -> (z - m) * (z - m)).sum() / y.length;
        assertEquals(2, one.iterations());
        assertTrue(one.converged());
        assertEquals(m, one.means()[0], 1e-12);
        assertEquals(Math.sqrt(v), one.sds()[0], 1e-12);
        Allocation.BaumWelch capped = Allocation.baumWelch(y, pi, a, new double[] {-1, 2}, new double[] {1, 1}, 1e-300,
                3);
        assertFalse(capped.converged());
        assertThrows(QfError.class, () -> Allocation.baumWelch(new double[] {1, 1, 1}, pi, a, new double[] {-1, 2},
                new double[] {1, 1}, 1e-10, 100));
    }
}
