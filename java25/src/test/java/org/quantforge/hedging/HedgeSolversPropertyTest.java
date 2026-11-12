package org.quantforge.hedging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import org.quantforge.core.LinearAlgebra;

/**
 * The property tests named by {@code hedge-solvers.md}, on this build's own random problems: KKT conditions of the
 * QP, {@code MIN_NORM} on regular problems, integer optimality against one-lot neighbours, the minimum-variance
 * effectiveness as an OLS {@code R^2}, the Euler sum of the residual report and exact Greek neutralisation.
 */
class HedgeSolversPropertyTest {

    private static double[][] gaussian(Random rnd, int rows, int cols) {
        double[][] m = new double[rows][cols];
        for (double[] row : m) {
            for (int j = 0; j < cols; j++) {
                row[j] = rnd.nextGaussian();
            }
        }
        return m;
    }

    private static double[] gaussian(Random rnd, int n) {
        return gaussian(rnd, 1, n)[0];
    }

    private static double[] positive(Random rnd, int n) {
        double[] w = new double[n];
        for (int i = 0; i < n; i++) {
            w[i] = 0.1 + 3.0 * rnd.nextDouble();
        }
        return w;
    }

    /** A feasible problem: bounds and equalities built around a random interior point. */
    private record Problem(double[][] a, double[] b, double[] w, double ridge, double[][] eq, double[] e,
            double[] lo, double[] hi) {}

    private static Problem problem(long seed, boolean bounds, int maxEq) {
        Random rnd = new Random(seed);
        int n = 1 + rnd.nextInt(5);
        int m = n + rnd.nextInt(4);
        double[] x0 = gaussian(rnd, n);
        double[] lo = null;
        double[] hi = null;
        if (bounds) {
            lo = new double[n];
            hi = new double[n];
            for (int j = 0; j < n; j++) {
                lo[j] = rnd.nextInt(4) == 0 ? Double.NEGATIVE_INFINITY : x0[j] - 0.5 * rnd.nextDouble();
                hi[j] = rnd.nextInt(4) == 0 ? Double.POSITIVE_INFINITY : x0[j] + 0.5 * rnd.nextDouble();
            }
        }
        int k = Math.min(maxEq, rnd.nextInt(n));
        double[][] eq = k == 0 ? null : gaussian(rnd, k, n);
        double[] e = k == 0 ? null : Dense.mul(eq, x0);
        double ridge = rnd.nextBoolean() ? 0.0 : rnd.nextDouble();
        return new Problem(gaussian(rnd, m, n), gaussian(rnd, m), positive(rnd, m), ridge, eq, e, lo, hi);
    }

    @Property(tries = 300)
    void qpSatisfiesKkt(@ForAll long seed) {
        Problem p = problem(seed, true, 2);
        LeastSquaresHedge.Solution s = LeastSquaresHedge.solve(p.a(), p.b(), p.w(), p.ridge(), p.eq(), p.e(), p.lo(),
                p.hi(), false);
        int n = s.x().length;
        int k = p.eq() == null ? 0 : p.eq().length;
        double[] x = s.x();
        // Gradient g = 2 (H x + c) = 2 (A'W r + ridge x).
        double[] wr = new double[p.b().length];
        for (int i = 0; i < wr.length; i++) {
            wr[i] = p.w()[i] * s.residual()[i];
        }
        double[] g = Dense.mulT(p.a(), wr, n);
        double scale = 1.0;
        for (int j = 0; j < n; j++) {
            g[j] = 2.0 * (g[j] + p.ridge() * x[j]);
            scale = Math.max(scale, Math.abs(g[j]));
        }
        List<Integer> free = new ArrayList<>();
        for (int j = 0; j < n; j++) {
            double tol = 1e-9 * Math.max(1.0, Math.abs(x[j]));
            assertTrue(x[j] >= p.lo()[j] - tol && x[j] <= p.hi()[j] + tol, "bound " + j);
            if (!(Math.abs(x[j] - p.lo()[j]) <= tol || Math.abs(x[j] - p.hi()[j]) <= tol)) {
                free.add(j);
            }
        }
        double[] lambda = new double[k];
        if (k > 0) {
            for (int i = 0; i < k; i++) {
                assertEquals(p.e()[i], Dense.dot(p.eq()[i], x), 1e-9 * Math.max(1.0, Math.abs(p.e()[i])));
            }
            double[][] m = new double[k][k];
            double[] rhs = new double[k];
            for (int i = 0; i < k; i++) {
                for (int j : free) {
                    rhs[i] -= p.eq()[i][j] * g[j];
                    for (int t = 0; t < k; t++) {
                        m[i][t] += p.eq()[i][j] * p.eq()[t][j];
                    }
                }
            }
            if (free.size() < k || LinearAlgebra.singularValues(m)[k - 1] < 1e-8 * LinearAlgebra.singularValues(m)[0]) {
                return; // the multipliers are not determined by the free set; the bound checks above still ran
            }
            lambda = LinearAlgebra.solve(m, rhs);
        }
        for (int j = 0; j < n; j++) {
            double stat = g[j];
            for (int i = 0; i < k; i++) {
                stat += p.eq()[i][j] * lambda[i];
            }
            if (free.contains(j)) {
                assertEquals(0.0, stat, 1e-8 * scale, "stationarity " + j);
            } else if (Math.abs(x[j] - p.lo()[j]) <= 1e-9 * Math.max(1.0, Math.abs(x[j]))) {
                assertTrue(stat >= -1e-8 * scale, "lower multiplier sign " + j); // mu_L = stat >= 0
            } else {
                assertTrue(stat <= 1e-8 * scale, "upper multiplier sign " + j); // mu_U = -stat >= 0
            }
        }
    }

    @Property(tries = 200)
    void minNormEqualsUniqueSolutionOnRegularProblems(@ForAll long seed) {
        Problem p = problem(seed, false, 2);
        LeastSquaresHedge.Solution unique = LeastSquaresHedge.solve(p.a(), p.b(), p.w(), p.ridge(), p.eq(), p.e(),
                null, null, false);
        LeastSquaresHedge.Solution mn = LeastSquaresHedge.solve(p.a(), p.b(), p.w(), p.ridge(), p.eq(), p.e(), null,
                null, true);
        int k = p.eq() == null ? 0 : p.eq().length;
        assertEquals(unique.x().length - k, mn.rank());
        for (int j = 0; j < unique.x().length; j++) {
            assertEquals(unique.x()[j], mn.x()[j], 1e-9 * Math.max(1.0, Math.abs(unique.x()[j])));
        }
    }

    @Property(tries = 150)
    void integerLotsBeatEveryNeighbourAndTheRelaxation(@ForAll long seed) {
        Random rnd = new Random(seed);
        int n = 1 + rnd.nextInt(3);
        int m = n + rnd.nextInt(3);
        double[] sizes = new double[n];
        double[] lo = new double[n];
        double[] hi = new double[n];
        for (int j = 0; j < n; j++) {
            sizes[j] = new double[] {1.0, 0.5, 2.5, 10.0}[rnd.nextInt(4)];
            lo[j] = rnd.nextInt(3) == 0 ? -1 - rnd.nextInt(3) : Double.NEGATIVE_INFINITY;
            hi[j] = rnd.nextInt(3) == 0 ? 1 + rnd.nextInt(3) : Double.POSITIVE_INFINITY;
        }
        double[][] a = gaussian(rnd, m, n);
        double[] b = gaussian(rnd, m);
        for (int i = 0; i < m; i++) {
            b[i] *= 20.0;
        }
        double[] w = positive(rnd, m);
        LeastSquaresHedge.IntegerSolution s = LeastSquaresHedge.solveLots(a, b, w, 0.0, sizes, lo, hi);
        assertTrue(s.objective() >= s.continuousObjective() * (1 - 1e-12) - 1e-12);
        for (int j = 0; j < n; j++) {
            assertTrue(s.lots()[j] >= lo[j] && s.lots()[j] <= hi[j]);
            for (int step = -1; step <= 1; step += 2) {
                long[] nb = s.lots().clone();
                nb[j] += step;
                if (nb[j] < lo[j] || nb[j] > hi[j]) {
                    continue;
                }
                double[] x = new double[n];
                for (int t = 0; t < n; t++) {
                    x[t] = sizes[t] * nb[t];
                }
                double f = LeastSquaresHedge.objective(LeastSquaresHedge.residual(a, b, x), w, 0.0, x);
                assertTrue(f >= s.objective() * (1 - 1e-12), "neighbour " + j + " " + step);
            }
        }
    }

    @Property(tries = 200)
    void minVarianceEffectivenessIsTheOlsRSquared(@ForAll long seed) {
        Random rnd = new Random(seed);
        int k = 1 + rnd.nextInt(3);
        int t = k + 2 + rnd.nextInt(40);
        double[][] h = gaussian(rnd, k, t);
        double[] e = new double[t];
        for (int p = 0; p < t; p++) {
            e[p] = rnd.nextGaussian();
            for (int i = 0; i < k; i++) {
                e[p] += (i + 0.5) * h[i][p];
            }
        }
        HedgeRatios.MinVariance mv = HedgeRatios.minimumVariance(HedgeRatios.sampleCovariance(e, h));
        // OLS of e on [1, h_1..h_k] by the normal equations.
        double[][] xtx = new double[k + 1][k + 1];
        double[] xty = new double[k + 1];
        for (int p = 0; p < t; p++) {
            double[] row = new double[k + 1];
            row[0] = 1.0;
            for (int i = 0; i < k; i++) {
                row[i + 1] = h[i][p];
            }
            for (int i = 0; i <= k; i++) {
                xty[i] += row[i] * e[p];
                for (int j = 0; j <= k; j++) {
                    xtx[i][j] += row[i] * row[j];
                }
            }
        }
        double[] beta = LinearAlgebra.solve(xtx, xty);
        double mean = 0.0;
        for (double v : e) {
            mean += v / t;
        }
        double ssr = 0.0;
        double sst = 0.0;
        for (int p = 0; p < t; p++) {
            double fit = beta[0];
            for (int i = 0; i < k; i++) {
                fit += beta[i + 1] * h[i][p];
            }
            ssr += (e[p] - fit) * (e[p] - fit);
            sst += (e[p] - mean) * (e[p] - mean);
        }
        assertEquals(1.0 - ssr / sst, mv.effectiveness(), 1e-9);
        for (int i = 0; i < k; i++) {
            assertEquals(-beta[i + 1], mv.hedge()[i], 1e-9 * Math.max(1.0, Math.abs(beta[i + 1])));
        }
    }

    @Property(tries = 200)
    void residualContributionsSumToTheVariance(@ForAll long seed) {
        Random rnd = new Random(seed);
        int m = 1 + rnd.nextInt(5);
        int n = 1 + rnd.nextInt(4);
        double[][] f = gaussian(rnd, m, m + 1);
        double[][] s = new double[m][m];
        for (int i = 0; i < m; i++) {
            for (int j = 0; j < m; j++) {
                s[i][j] = Dense.dot(f[i], f[j]);
            }
        }
        HedgeRatios.Residual r = HedgeRatios.residualReport(gaussian(rnd, m, n), gaussian(rnd, m),
                gaussian(rnd, n), s);
        double sum = 0.0;
        for (double c : r.contributions()) {
            sum += c;
        }
        assertEquals(r.varianceAfter(), sum, 1e-12 * Math.max(1.0, Math.abs(r.varianceAfter())));
        assertEquals(1.0 - r.varianceAfter() / r.varianceBefore(), r.effectiveness(), 1e-15);
    }

    @Property(tries = 200)
    void greekHedgeZeroesEveryTarget(@ForAll long seed) {
        Random rnd = new Random(seed);
        HedgeRatios.Market mk = new HedgeRatios.Market(50 + 100 * rnd.nextDouble(), 0.1 * rnd.nextGaussian(),
                0.05 * rnd.nextDouble(), 0.1 + 0.4 * rnd.nextDouble());
        List<HedgeRatios.Position> book = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            book.add(new HedgeRatios.Position(rnd.nextBoolean() ? HedgeRatios.Instrument.CALL
                    : HedgeRatios.Instrument.PUT, mk.spot() * (0.8 + 0.4 * rnd.nextDouble()),
                    0.2 + 2 * rnd.nextDouble(), 100 * rnd.nextGaussian()));
        }
        List<HedgeRatios.Position> hedges = List.of(
                new HedgeRatios.Position(HedgeRatios.Instrument.UNDERLYING, null, null, 0),
                new HedgeRatios.Position(HedgeRatios.Instrument.CALL, mk.spot(), 0.5, 0),
                new HedgeRatios.Position(HedgeRatios.Instrument.PUT, mk.spot() * 0.9, 2.0, 0));
        List<HedgeRatios.Greek> targets = List.of(HedgeRatios.Greek.VEGA, HedgeRatios.Greek.DELTA,
                HedgeRatios.Greek.GAMMA);
        HedgeRatios.GreekHedge g = HedgeRatios.neutralise(mk, book, hedges, targets);
        for (int i = 0; i < 3; i++) {
            double scale = Math.max(1.0, Math.abs(g.before()[i]));
            assertEquals(0.0, g.after()[i], 1e-9 * scale);
        }
    }
}
