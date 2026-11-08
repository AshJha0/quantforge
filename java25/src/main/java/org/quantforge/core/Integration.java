package org.quantforge.core;

import java.util.ArrayList;
import java.util.List;
import java.util.function.DoubleUnaryOperator;

/** Fixed and adaptive quadrature (integration.md). */
public final class Integration {
    private Integration() {}

    public record Adaptive(double value, double errorEstimate) {}

    private static final long MAX_CALLS = 10_000_000L;

    private static void checkRange(double a, double b) {
        if (!(a < b)) {
            throw new QfError("E_INPUT", "need a < b");
        }
    }

    public static double trapezoid(DoubleUnaryOperator f, double a, double b, long n) {
        checkRange(a, b);
        if (n < 1) {
            throw new QfError("E_INPUT", "need n >= 1", "n");
        }
        double h = (b - a) / n;
        double sum = f.applyAsDouble(a) / 2.0;
        for (long i = 1; i < n; i++) {
            sum += f.applyAsDouble(a + i * h);
        }
        sum += f.applyAsDouble(a + n * h) / 2.0;
        return h * sum;
    }

    public static double simpson(DoubleUnaryOperator f, double a, double b, long n) {
        checkRange(a, b);
        if (n < 2 || n % 2 != 0) {
            throw new QfError("E_INPUT", "need even n >= 2", "n");
        }
        double h = (b - a) / n;
        double sum = f.applyAsDouble(a);
        for (long i = 1; i < n; i++) {
            sum += (i % 2 == 1 ? 4.0 : 2.0) * f.applyAsDouble(a + i * h);
        }
        sum += f.applyAsDouble(a + n * h);
        return h / 3.0 * sum;
    }

    /** P_n(x) and P_{n-1}(x). */
    private static double[] legendreAt(int n, double x) {
        double p0 = 1.0;
        double p1 = x;
        for (int k = 2; k <= n; k++) {
            double p2 = ((2 * k - 1) * x * p1 - (k - 1) * p0) / k;
            p0 = p1;
            p1 = p2;
        }
        return new double[] {p1, p0};
    }

    /** Returns nodes then weights on [-1, 1], ascending in node. */
    public static double[][] legendre(int n) {
        double[] t = new double[n];
        double[] w = new double[n];
        for (int i = 1; i <= n; i++) {
            double x = Math.cos(Math.PI * (i - 0.25) / (n + 0.5));
            for (int it = 0; it < 100; it++) {
                double[] p = legendreAt(n, x);
                double dx = p[0] / (n * (x * p[0] - p[1]) / (x * x - 1.0));
                x -= dx;
                if (Math.abs(dx) < 1e-16) {
                    break;
                }
            }
            double[] p = legendreAt(n, x);
            double dp = n * (x * p[0] - p[1]) / (x * x - 1.0);
            t[n - i] = x;
            w[n - i] = 2.0 / ((1.0 - x * x) * dp * dp);
        }
        return new double[][] {t, w};
    }

    public static double gaussLegendre(DoubleUnaryOperator f, double a, double b, long n) {
        checkRange(a, b);
        if (n < 1 || n > 64) {
            throw new QfError("E_INPUT", "need n from 1 to 64", "n");
        }
        double[][] tw = legendre((int) n);
        double sum = 0.0;
        for (int i = 0; i < n; i++) {
            sum += tw[1][i] * f.applyAsDouble((a + b) / 2.0 + (b - a) / 2.0 * tw[0][i]);
        }
        return (b - a) / 2.0 * sum;
    }

    /** Stops a run at the fixed call limit of limits.md. */
    private static DoubleUnaryOperator counted(DoubleUnaryOperator f) {
        long[] calls = new long[1];
        return x -> {
            if (++calls[0] >= MAX_CALLS) {
                throw new QfError("E_NO_CONVERGENCE", "function call limit reached");
            }
            return f.applyAsDouble(x);
        };
    }

    private static double finite(DoubleUnaryOperator f, double x) {
        double v = f.applyAsDouble(x);
        if (!Double.isFinite(v)) {
            throw new QfError("E_NON_FINITE", "f is not finite at " + x);
        }
        return v;
    }

    public static double adaptiveSimpson(DoubleUnaryOperator f, double a, double b, double tol, long maxDepth) {
        checkRange(a, b);
        if (!(tol > 0.0) || maxDepth < 1) {
            throw new QfError("E_INPUT", "need tol > 0 and max_depth >= 1");
        }
        DoubleUnaryOperator g = counted(f);
        double fa = finite(g, a);
        double fb = finite(g, b);
        double fm = finite(g, (a + b) / 2.0);
        return simpsonStep(g, a, b, fa, fm, fb, (b - a) / 6.0 * (fa + 4.0 * fm + fb), tol, 0, maxDepth);
    }

    private static double simpsonStep(DoubleUnaryOperator f, double l, double r, double fl, double fm, double fr,
                                      double whole, double tol, long depth, long maxDepth) {
        double m = (l + r) / 2.0;
        double flm = finite(f, (l + m) / 2.0);
        double frm = finite(f, (m + r) / 2.0);
        double s1 = (m - l) / 6.0 * (fl + 4.0 * flm + fm);
        double s2 = (r - m) / 6.0 * (fm + 4.0 * frm + fr);
        double delta = s1 + s2 - whole;
        if (Math.abs(delta) <= 15.0 * tol) {
            return s1 + s2 + delta / 15.0;
        }
        if (depth >= maxDepth) {
            throw new QfError("E_NO_CONVERGENCE", "max_depth exceeded");
        }
        return simpsonStep(f, l, m, fl, flm, fm, s1, tol / 2.0, depth + 1, maxDepth)
                + simpsonStep(f, m, r, fm, frm, fr, s2, tol / 2.0, depth + 1, maxDepth);
    }

    private static final double[] XK = {0.991455371120812639206854697526329, 0.949107912342758524526189684047851,
        0.864864423359769072789712788640926, 0.741531185599394439863864773280788, 0.586087235467691130294144838258730,
        0.405845151377397166906606412076961, 0.207784955007898467600689403773244, 0.0};
    private static final double[] WK = {0.022935322010529224963732008058970, 0.063092092629978553290700663189204,
        0.104790010322250183839876322541518, 0.140653259715525918998541745705333, 0.169004726639267902826583426140209,
        0.190350578064785409913256402421014, 0.204432940075298892414161999234649, 0.209482141084727828012999174351914};
    private static final double[] WG = {0.129484966168869693270611432679082, 0.279705391489276667901467771423780,
        0.381830050505118944950369775488975, 0.417959183673469387755102040816327};

    private record Piece(double a, double b, double value, double error) {}

    private static Piece kronrod(DoubleUnaryOperator f, double a, double b) {
        double c = (a + b) / 2.0;
        double h = (b - a) / 2.0;
        double fc = finite(f, c);
        double k = WK[7] * fc;
        double g = WG[3] * fc;
        for (int i = 0; i < 7; i++) {
            double s = finite(f, c - h * XK[i]) + finite(f, c + h * XK[i]);
            k += WK[i] * s;
            if (i % 2 == 1) {
                g += WG[i / 2] * s;
            }
        }
        return new Piece(a, b, k * h, Math.abs(k - g) * h);
    }

    public static Adaptive gaussKronrod(DoubleUnaryOperator raw, double a, double b, double tol, long maxIntervals) {
        DoubleUnaryOperator f = counted(raw);
        checkRange(a, b);
        if (!(tol > 0.0) || maxIntervals < 1) {
            throw new QfError("E_INPUT", "need tol > 0 and max_intervals >= 1");
        }
        List<Piece> pieces = new ArrayList<>();
        pieces.add(kronrod(f, a, b));
        while (true) {
            double value = 0.0;
            double error = 0.0;
            int worst = 0;
            for (int i = 0; i < pieces.size(); i++) {
                Piece p = pieces.get(i);
                value += p.value();
                error += p.error();
                if (p.error() > pieces.get(worst).error()) {
                    worst = i;
                }
            }
            if (error <= Math.max(tol, 1e-14 * Math.abs(value))) {
                return new Adaptive(value, error);
            }
            if (pieces.size() + 1 > maxIntervals) {
                throw new QfError("E_NO_CONVERGENCE", "max_intervals exceeded");
            }
            Piece p = pieces.get(worst);
            double m = (p.a() + p.b()) / 2.0;
            pieces.set(worst, kronrod(f, p.a(), m));
            pieces.add(worst + 1, kronrod(f, m, p.b()));
        }
    }
}
