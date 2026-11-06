package org.quantforge.core;

import java.util.function.DoubleUnaryOperator;

/** Bisection, Brent and safeguarded Newton (root-finders.md). */
public final class RootFinders {
    private RootFinders() {}

    public enum Termination { X_TOL, F_TOL, EXACT }

    public record Result(double root, int iterations, double residual, Termination termination) {}

    public record Tolerances(double xTol, double fTol, long maxIter) {
        void check() {
            if (xTol <= 0.0 || fTol < 0.0 || maxIter < 1) {
                throw new QfError("E_INPUT", "need x_tol > 0, f_tol >= 0 and max_iter >= 1");
            }
        }
    }

    private static final double EPS = 0x1p-52;

    private static double eval(DoubleUnaryOperator f, double x) {
        double v = f.applyAsDouble(x);
        if (!Double.isFinite(v)) {
            throw new QfError("E_NON_FINITE", "f is not finite at " + x);
        }
        return v;
    }

    private static QfError noConvergence() {
        return new QfError("E_NO_CONVERGENCE", "max_iter reached");
    }

    private static boolean sameSign(double p, double q) {
        return (p > 0.0) == (q > 0.0);
    }

    private static void checkBracket(double a, double b) {
        if (!(a < b)) {
            throw new QfError("E_INPUT", "need a < b");
        }
    }

    public static Result bisection(DoubleUnaryOperator f, double a, double b, Tolerances t) {
        t.check();
        checkBracket(a, b);
        double fa = eval(f, a);
        double fb = eval(f, b);
        if (fa == 0.0) {
            return new Result(a, 0, 0.0, Termination.EXACT);
        }
        if (fb == 0.0) {
            return new Result(b, 0, 0.0, Termination.EXACT);
        }
        if (sameSign(fa, fb)) {
            throw new QfError("E_NOT_BRACKETED", "no sign change on [a, b]");
        }
        for (int it = 1; it <= t.maxIter(); it++) {
            double m = a + (b - a) / 2.0;
            double fm = eval(f, m);
            if (fm == 0.0) {
                return new Result(m, it, 0.0, Termination.EXACT);
            }
            if (sameSign(fa, fm)) {
                a = m;
                fa = fm;
            } else {
                b = m;
            }
            if ((b - a) / 2.0 <= t.xTol()) {
                return new Result(m, it, fm, Termination.X_TOL);
            }
            if (Math.abs(fm) <= t.fTol()) {
                return new Result(m, it, fm, Termination.F_TOL);
            }
        }
        throw noConvergence();
    }

    public static Result brent(DoubleUnaryOperator f, double lo, double hi, Tolerances t) {
        t.check();
        checkBracket(lo, hi);
        double a = lo;
        double b = hi;
        double fa = eval(f, a);
        double fb = eval(f, b);
        if (fa == 0.0) {
            return new Result(a, 0, 0.0, Termination.EXACT);
        }
        if (fb == 0.0) {
            return new Result(b, 0, 0.0, Termination.EXACT);
        }
        if (sameSign(fa, fb)) {
            throw new QfError("E_NOT_BRACKETED", "no sign change on [a, b]");
        }
        double c = a;
        double fc = fa;
        double d = b - a;
        double e = d;
        for (int it = 1; it <= t.maxIter(); it++) {
            if (Math.abs(fc) < Math.abs(fb)) {
                a = b;
                b = c;
                c = a;
                fa = fb;
                fb = fc;
                fc = fa;
            }
            double tol1 = 2.0 * EPS * Math.abs(b) + t.xTol() / 2.0;
            double xm = (c - b) / 2.0;
            if (Math.abs(xm) <= tol1) {
                return new Result(b, it, fb, Termination.X_TOL);
            }
            if (fb == 0.0) {
                return new Result(b, it, fb, Termination.EXACT);
            }
            if (Math.abs(fb) <= t.fTol()) {
                return new Result(b, it, fb, Termination.F_TOL);
            }
            if (Math.abs(e) >= tol1 && Math.abs(fa) > Math.abs(fb)) {
                double s = fb / fa;
                double p;
                double q;
                if (a == c) {
                    p = 2.0 * xm * s;
                    q = 1.0 - s;
                } else {
                    double u = fa / fc;
                    double r = fb / fc;
                    p = s * (2.0 * xm * u * (u - r) - (b - a) * (r - 1.0));
                    q = (u - 1.0) * (r - 1.0) * (s - 1.0);
                }
                if (p > 0.0) {
                    q = -q;
                }
                p = Math.abs(p);
                if (2.0 * p < Math.min(3.0 * Math.abs(xm * q) - Math.abs(tol1 * q), Math.abs(e * q))) {
                    e = d;
                    d = p / q;
                } else {
                    d = xm;
                    e = d;
                }
            } else {
                d = xm;
                e = d;
            }
            a = b;
            fa = fb;
            b += Math.abs(d) > tol1 ? d : Math.copySign(tol1, xm);
            fb = eval(f, b);
            if (sameSign(fb, fc)) {
                c = a;
                fc = fa;
                d = b - a;
                e = d;
            }
        }
        throw noConvergence();
    }

    /** {@code a} and {@code b} are null together when there is no bracket. */
    public static Result newton(DoubleUnaryOperator f, DoubleUnaryOperator df, double x0, Double a, Double b,
                                Tolerances t) {
        t.check();
        boolean bracket = a != null;
        double lo = 0.0;
        double hi = 0.0;
        double flo = 0.0;
        if (bracket) {
            lo = a;
            hi = b;
            checkBracket(lo, hi);
            flo = eval(f, lo);
            double fhi = eval(f, hi);
            if (flo != 0.0 && fhi != 0.0 && sameSign(flo, fhi)) {
                throw new QfError("E_NOT_BRACKETED", "no sign change on [a, b]");
            }
            if (x0 < lo || x0 > hi) {
                throw new QfError("E_INPUT", "x0 outside [a, b]", "x0");
            }
        }
        double x = x0;
        for (int it = 1; it <= t.maxIter(); it++) {
            double fx = eval(f, x);
            if (fx == 0.0) {
                return new Result(x, it, 0.0, Termination.EXACT);
            }
            double dfx = eval(df, x);
            if (dfx == 0.0) {
                throw new QfError("E_ZERO_DERIVATIVE", "derivative is zero at " + x);
            }
            if (bracket) {
                if (flo != 0.0 && sameSign(fx, flo)) {
                    lo = x;
                    flo = fx;
                } else {
                    hi = x;
                }
            }
            double next = x - fx / dfx;
            if (bracket && !(next >= lo && next <= hi)) {
                next = lo + (hi - lo) / 2.0;
            }
            double fn = eval(f, next);
            if (Math.abs(next - x) <= t.xTol() * (1.0 + Math.abs(next))) {
                return new Result(next, it, fn, Termination.X_TOL);
            }
            if (Math.abs(fn) <= t.fTol()) {
                return new Result(next, it, fn, Termination.F_TOL);
            }
            x = next;
        }
        throw noConvergence();
    }
}
