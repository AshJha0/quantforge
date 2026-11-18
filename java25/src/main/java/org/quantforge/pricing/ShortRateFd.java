package org.quantforge.pricing;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/**
 * The pinned Hull-White finite-difference reference scheme of ruling G-18: Bermudan swaptions and callable bonds
 * (short-rate-models.md, waves 2d and 2g). Fully implicit, coefficients at the earlier time, linear-extrapolation
 * boundaries substituted into the tridiagonal rows.
 */
public final class ShortRateFd {
    private ShortRateFd() {}

    /*
     * G-9 work counter (aad-core.md, G-9), the one definition shared by the four ports: W = number of per-grid-node
     * evaluations in every time-stepping, exercise and adjoint loop (each inner per-node iteration counts 1; a
     * tridiagonal solve over nx nodes counts nx), plus the number of tape operations recorded and the number replayed
     * in the reverse sweep. An exercise evaluation at a node counts 1 with its max or active-branch test folded in,
     * and one stage split over several passes still counts 1 per node. Each call adds its count once, at the end, to a per-thread total; it never touches a
     * priced value.
     */
    private static final ThreadLocal<long[]> WORK = ThreadLocal.withInitial(() -> new long[1]);

    static void addWork(long w) {
        WORK.get()[0] += w;
    }

    /** Resets this thread's G-9 work counter (test entry point). */
    public static void workReset() {
        WORK.get()[0] = 0L;
    }

    /**
     * This thread's G-9 work count since the last {@link #workReset} (test entry point).
     *
     * @return W
     */
    public static long work() {
        return WORK.get()[0];
    }

    /**
     * The space and time grid inputs.
     *
     * @param nx number of space nodes, odd and at least 5
     * @param stepsPerYear time steps per year
     * @param width half-width of the space grid in standard deviations
     */
    public record Grid(int nx, long stepsPerYear, double width) {}

    /** What happens on arrival at a knot: the value vector may be changed in place. */
    private interface Knot {
        void apply(int k, double t, double[] x, double[] v);
    }

    private static double alpha(ShortRate.Params p, double t) {
        double a = p.a();
        double e = -Math.expm1(-a * t);
        return p.curve().forward(t) + p.sigma() * p.sigma() / (2.0 * a * a) * e * e;
    }

    /**
     * Rolls back from the last knot to 0. {@code v} holds the values at the last knot on entry; {@code at} is
     * called on arrival at every knot {@code k} with {@code 0 < k < m}. Returns the centre value at 0.
     */
    private static double roll(ShortRate.Params p, Grid g, double[] knots, double[] x, double[] v, Knot at) {
        int nx = g.nx();
        double a = p.a();
        double s2 = p.sigma() * p.sigma() / 2.0;
        double dx = x[1] - x[0];
        double diff = s2 / (dx * dx);
        double[] lo = new double[nx];
        double[] di = new double[nx];
        double[] up = new double[nx];
        double[] rhs = new double[nx];
        int m = knots.length - 1;
        long w = 0L;
        for (int k = m; k >= 1; k--) {
            double t1 = knots[k - 1];
            double span = knots[k] - t1;
            long n = Math.max(1L, (long) Math.ceil(g.stepsPerYear() * span));
            double dt = span / n;
            for (long j = n - 1; j >= 0; j--) {
                double t = t1 + j * dt;
                double al = alpha(p, t);
                for (int i = 1; i < nx - 1; i++) {
                    double drift = a * x[i] / (2.0 * dx);
                    lo[i] = -dt * (diff + drift);
                    di[i] = 1.0 - dt * (-2.0 * diff - (x[i] + al));
                    up[i] = -dt * (diff - drift);
                    rhs[i] = v[i];
                }
                di[1] += 2.0 * lo[1];
                up[1] -= lo[1];
                di[nx - 2] += 2.0 * up[nx - 2];
                lo[nx - 2] -= up[nx - 2];
                solve(lo, di, up, rhs, v, 1, nx - 2);
                v[0] = 2.0 * v[1] - v[2];
                v[nx - 1] = 2.0 * v[nx - 2] - v[nx - 3];
                w += 2L * (nx - 2); // coefficient rows + Thomas solve
            }
            if (k - 1 > 0) {
                at.apply(k - 1, t1, x, v);
                w += nx; // knot update
            }
        }
        addWork(w);
        return v[(nx - 1) / 2];
    }

    /** Thomas algorithm on rows {@code first..last}; the boundary coupling is already folded in. */
    private static void solve(double[] lo, double[] di, double[] up, double[] rhs, double[] out, int first,
                              int last) {
        int len = last - first + 1;
        double[] c = new double[len];
        double[] d = new double[len];
        c[0] = up[first] / di[first];
        d[0] = rhs[first] / di[first];
        for (int r = 1; r < len; r++) {
            int i = first + r;
            double den = di[i] - lo[i] * c[r - 1];
            c[r] = up[i] / den;
            d[r] = (rhs[i] - lo[i] * d[r - 1]) / den;
        }
        out[last] = d[len - 1];
        for (int r = len - 2; r >= 0; r--) {
            out[first + r] = d[r] - c[r] * out[first + r + 1];
        }
    }

    private static double[] space(ShortRate.Params p, Grid g, double tm) {
        double a = p.a();
        double sx = p.sigma() * Math.sqrt(-Math.expm1(-2.0 * a * tm) / (2.0 * a));
        double h = g.width() * sx;
        double dx = 2.0 * h / (g.nx() - 1);
        double[] x = new double[g.nx()];
        for (int i = 0; i < x.length; i++) {
            x[i] = -h + i * dx;
        }
        return x;
    }

    private static double exercise(ShortRate.Params p, double t, double r, double[] pay, double rate, double phi) {
        double sum = 0.0;
        double prev = t;
        double last = 0.0;
        for (double tj : pay) {
            if (tj > t) {
                last = ShortRate.zcb(p, r, t, tj);
                sum += (tj - prev) * last;
                prev = tj;
            }
        }
        return phi * (1.0 - last - rate * sum);
    }

    /**
     * Bermudan swaption on the reference scheme.
     *
     * @param p the Hull-White model
     * @param pay payment times of the underlying swap
     * @param rate fixed rate
     * @param payer true for a payer, false for a receiver
     * @param notional notional
     * @param ex exercise times, increasing reset dates
     * @param g the grid
     * @return the price
     */
    public static double bermudan(ShortRate.Params p, double[] pay, double rate, boolean payer, double notional,
                                  double[] ex, Grid g) {
        double phi = payer ? 1.0 : -1.0;
        double[] knots = new double[ex.length + 1];
        System.arraycopy(ex, 0, knots, 1, ex.length);
        double tm = ex[ex.length - 1];
        double[] x = space(p, g, tm);
        double[] v = new double[x.length];
        double al = alpha(p, tm);
        for (int i = 0; i < x.length; i++) {
            v[i] = Math.max(exercise(p, tm, x[i] + al, pay, rate, phi), 0.0);
        }
        addWork(x.length); // terminal payoff
        return notional * roll(p, g, knots, x, v, (k, t, xs, vs) -> {
            double alk = alpha(p, t);
            for (int i = 0; i < xs.length; i++) {
                vs[i] = Math.max(vs[i], exercise(p, t, xs[i] + alk, pay, rate, phi));
            }
        });
    }

    /**
     * Issuer-callable fixed-rate bond on the reference scheme (ruling G-21).
     *
     * @param p the Hull-White model
     * @param pay payment times
     * @param coupon coupon rate, accruals from 0
     * @param notional face
     * @param calls call times, a subset of the payment times before the last
     * @param callPrice call price as a fraction of face
     * @param g the grid
     * @return the price
     */
    public static double callable(ShortRate.Params p, double[] pay, double coupon, double notional, double[] calls,
                                  double callPrice, Grid g) {
        int n = pay.length;
        double[] knots = new double[n + 1];
        System.arraycopy(pay, 0, knots, 1, n);
        double[] x = space(p, g, pay[n - 1]);
        double[] v = new double[x.length];
        Arrays.fill(v, 1.0 + coupon * (knots[n] - knots[n - 1]));
        Set<Double> callSet = new HashSet<>();
        for (double c : calls) {
            callSet.add(c);
        }
        return notional * roll(p, g, knots, x, v, (k, t, xs, vs) -> {
            boolean call = callSet.contains(t);
            double cpn = coupon * (knots[k] - knots[k - 1]);
            for (int i = 0; i < vs.length; i++) {
                vs[i] = (call ? Math.min(vs[i], callPrice) : vs[i]) + cpn;
            }
        });
    }
}
