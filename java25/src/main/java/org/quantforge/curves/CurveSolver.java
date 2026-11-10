package org.quantforge.curves;

import org.quantforge.core.Finite;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.List;
import java.util.function.DoubleUnaryOperator;
import java.util.function.ToDoubleFunction;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.QfError;

/**
 * Solves pillar log discount factors so that each model rate equals its quote. Model j reads no date beyond
 * pillar j, so the system is triangular and either method lands on the same curve.
 */
public final class CurveSolver {
    private CurveSolver() {}

    public enum Method { SEQUENTIAL, GLOBAL }

    public record Solved(Curve curve, double maxRepricingError) {}

    private record Setup(LocalDate asOf, Curve.Interpolation interp, LocalDate[] dates, double[] quotes,
                         List<ToDoubleFunction<Curve>> models, Jumps jumps, Curve.Shape shape) {
        double years(int j) {
            return j < 0 ? 0.0 : ChronoUnit.DAYS.between(asOf, dates[j]) / 365.0;
        }

        double[] residuals(double[] x) {
            Curve c = Curve.fromLogs(asOf, interp, dates, x, jumps, shape);
            double[] r = new double[x.length];
            for (int j = 0; j < r.length; j++) {
                r[j] = models.get(j).applyAsDouble(c) - quotes[j];
            }
            return r;
        }
    }

    private static final double TARGET = 1e-15;
    private static final double ACCEPT = 1e-13;
    private static final int MAX_STEPS = 60;

    public static Solved solve(LocalDate asOf, Curve.Interpolation interp, LocalDate[] dates, double[] quotes,
                               List<ToDoubleFunction<Curve>> models, Method method) {
        Finite.check("quotes", quotes);
        return solve(asOf, interp, dates, quotes, models, method, Jumps.NONE);
    }

    public static Solved solve(LocalDate asOf, Curve.Interpolation interp, LocalDate[] dates, double[] quotes,
                               List<ToDoubleFunction<Curve>> models, Method method, Jumps jumps) {
        return solve(asOf, interp, dates, quotes, models, method, jumps, Curve.Shape.NONE);
    }

    /**
     * As above with the stage F parameters. The stage F methods are not local, so SEQUENTIAL and GLOBAL both return
     * the global solution (ruling F-21).
     */
    public static Solved solve(LocalDate asOf, Curve.Interpolation interp, LocalDate[] dates, double[] quotes,
                               List<ToDoubleFunction<Curve>> models, Method method, Jumps jumps, Curve.Shape shape) {
        Finite.check("quotes", quotes);
        shape.check(interp, dates);
        Setup s = new Setup(asOf, interp, dates, quotes, models, jumps, shape);
        double[] x = method == Method.SEQUENTIAL && !interp.smooth() ? sequential(s) : global(s);
        double worst = norm(s.residuals(x));
        if (!(worst < ACCEPT)) {
            throw new QfError("E_NO_CONVERGENCE", "curve solve stopped at repricing error " + worst);
        }
        return new Solved(Curve.fromLogs(asOf, interp, dates, x, jumps, shape), worst);
    }

    /** The largest absolute entry; NaN if any entry is NaN. */
    private static double norm(double[] r) {
        double m = 0.0;
        for (double v : r) {
            if (Double.isNaN(v)) {
                return Double.NaN;
            }
            m = Math.max(m, Math.abs(v));
        }
        return m;
    }

    private static double[] sequential(Setup s) {
        double[] x = new double[s.dates().length];
        for (int j = 0; j < x.length; j++) {
            LocalDate[] prefix = Arrays.copyOf(s.dates(), j + 1);
            double[] logs = Arrays.copyOf(x, j + 1);
            int index = j;
            DoubleUnaryOperator error = v -> {
                logs[index] = v;
                return s.models().get(index).applyAsDouble(Curve.fromLogs(s.asOf(), s.interp(), prefix, logs, s.jumps()))
                        - s.quotes()[index];
            };
            double guess = (j == 0 ? 0.0 : x[j - 1]) - s.quotes()[j] * (s.years(j) - s.years(j - 1));
            x[j] = secant(error, guess, guess - 1e-4);
        }
        return x;
    }

    private static double secant(DoubleUnaryOperator g, double a, double b) {
        double ga = g.applyAsDouble(a);
        double gb = g.applyAsDouble(b);
        double best = Math.abs(ga) < Math.abs(gb) ? a : b;
        double bestError = Math.min(Math.abs(ga), Math.abs(gb));
        int stalled = 0;
        for (int i = 0; i < MAX_STEPS && bestError > TARGET && stalled < 3 && gb != ga; i++) {
            double next = b - gb * (b - a) / (gb - ga);
            a = b;
            ga = gb;
            b = next;
            gb = g.applyAsDouble(b);
            if (Math.abs(gb) < bestError) {
                bestError = Math.abs(gb);
                best = b;
                stalled = 0;
            } else {
                stalled++;
            }
        }
        return best;
    }

    /** Newton on all pillars together, from a flat guess, with a bumped Jacobian. */
    private static double[] global(Setup s) {
        int n = s.dates().length;
        double[] x = new double[n];
        for (int j = 0; j < n; j++) {
            x[j] = -s.quotes()[j] * s.years(j);
        }
        double[] best = x.clone();
        double[] r = s.residuals(x);
        double bestError = norm(r);
        int stalled = 0;
        double h = 1e-6;
        for (int it = 0; it < MAX_STEPS && bestError > TARGET && stalled < 3; it++) {
            double[][] jac = new double[n][n];
            for (int c = 0; c < n; c++) {
                double[] up = x.clone();
                double[] down = x.clone();
                up[c] += h;
                down[c] -= h;
                double[] ru = s.residuals(up);
                double[] rd = s.residuals(down);
                for (int i = 0; i < n; i++) {
                    jac[i][c] = (ru[i] - rd[i]) / (2.0 * h);
                }
            }
            double[] step;
            try {
                step = LinearAlgebra.solve(jac, r);
            } catch (QfError e) {
                throw new QfError("E_NO_CONVERGENCE", "curve Jacobian is singular");
            }
            for (int i = 0; i < n; i++) {
                x[i] -= step[i];
            }
            r = s.residuals(x);
            double e = norm(r);
            if (e < bestError) {
                bestError = e;
                best = x.clone();
                stalled = 0;
            } else {
                stalled++;
            }
        }
        return best;
    }
}
