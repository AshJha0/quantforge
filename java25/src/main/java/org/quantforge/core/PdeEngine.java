package org.quantforge.core;

/** Theta-scheme Black-Scholes solver in log price, with Rannacher start-up (pde.md). */
public final class PdeEngine {
    private PdeEngine() {}

    public record Inputs(boolean call, double spot, double strike, double r, double q, double sigma, double t,
                         long spaceSteps, long timeSteps, double width, long rannacherSteps) {}

    public record Result(double price, double delta, double gamma, double gridH) {}

    public static Result solve(Inputs in) {
        if (in.spot() <= 0 || in.strike() <= 0 || in.sigma() <= 0 || in.t() <= 0 || in.width() <= 0) {
            throw new QfError("E_DOMAIN", "spot, strike, sigma, t and width must be positive");
        }
        long jj = in.spaceSteps();
        long mm = in.timeSteps();
        long rr = in.rannacherSteps();
        if (jj % 2 != 0 || jj < 20 || mm < 2 || rr < 0 || rr >= mm) {
            throw new QfError("E_INPUT", "bad grid sizes");
        }
        int nJ = Math.toIntExact(jj);
        double a = in.sigma() * in.sigma() / 2.0;
        double b = in.r() - in.q() - a;
        double h = 2.0 * in.width() * in.sigma() * Math.sqrt(in.t()) / nJ;
        double dt = in.t() / mm;
        double x0 = Math.log(in.spot());
        double[] x = new double[nJ + 1];
        for (int j = 0; j <= nJ; j++) {
            x[j] = x0 + (j - nJ / 2) * h;
        }
        double[] v = new double[nJ + 1];
        for (int j = 0; j <= nJ; j++) {
            v[j] = cellAverage(in.call(), x[j], h, in.strike());
        }
        double l = a / (h * h) - b / (2.0 * h);
        double c = -2.0 * a / (h * h) - in.r();
        double u = a / (h * h) + b / (2.0 * h);
        double sLow = Math.exp(x[0]);
        double sHigh = Math.exp(x[nJ]);
        Stepper st = new Stepper(in, l, c, u, sLow, sHigh, v);
        for (long n = 0; n < rr; n++) {
            double start = n * dt;
            st.step(1.0, dt / 2.0, start, start + dt / 2.0);
            st.step(1.0, dt / 2.0, start + dt / 2.0, (n + 1) * dt);
        }
        for (long n = rr; n < mm; n++) {
            st.step(0.5, dt, n * dt, (n + 1) * dt);
        }
        double[] w = st.v;
        int m = nJ / 2;
        double vx = (w[m + 1] - w[m - 1]) / (2.0 * h);
        double vxx = (w[m + 1] - 2.0 * w[m] + w[m - 1]) / (h * h);
        return new Result(w[m], vx / in.spot(), (vxx - vx) / (in.spot() * in.spot()), h);
    }

    private static double cellAverage(boolean call, double xj, double h, double strike) {
        double k = Math.log(strike);
        double lo = xj - h / 2.0;
        double hi = xj + h / 2.0;
        if (call) {
            if (hi <= k) {
                return 0.0;
            }
            double from = Math.max(lo, k);
            return (Math.exp(hi) - Math.exp(from) - strike * (hi - from)) / h;
        }
        if (lo >= k) {
            return 0.0;
        }
        double to = Math.min(hi, k);
        return (strike * (to - lo) - Math.exp(to) + Math.exp(lo)) / h;
    }

    private static final class Stepper {
        private final Inputs in;
        private final double l;
        private final double c;
        private final double u;
        private final double sLow;
        private final double sHigh;
        private final double[] rhs;
        private final double[] work;
        double[] v;
        private double[] next;

        Stepper(Inputs in, double l, double c, double u, double sLow, double sHigh, double[] v) {
            this.in = in;
            this.l = l;
            this.c = c;
            this.u = u;
            this.sLow = sLow;
            this.sHigh = sHigh;
            this.v = v;
            next = new double[v.length];
            rhs = new double[v.length];
            work = new double[v.length];
        }

        private double lower(double tau) {
            return in.call() ? 0.0 : in.strike() * Math.exp(-in.r() * tau) - sLow * Math.exp(-in.q() * tau);
        }

        private double upper(double tau) {
            return in.call() ? sHigh * Math.exp(-in.q() * tau) - in.strike() * Math.exp(-in.r() * tau) : 0.0;
        }

        /** One theta step of size s from tauOld to tauNew. */
        void step(double theta, double s, double tauOld, double tauNew) {
            int nJ = v.length - 1;
            double lowOld = lower(tauOld);
            double highOld = upper(tauOld);
            double lowNew = lower(tauNew);
            double highNew = upper(tauNew);
            double e = (1.0 - theta) * s;
            for (int j = 1; j < nJ; j++) {
                double left = j == 1 ? lowOld : v[j - 1];
                double right = j == nJ - 1 ? highOld : v[j + 1];
                rhs[j] = v[j] + e * (l * left + c * v[j] + u * right);
            }
            double sub = -theta * s * l;
            double diag = 1.0 - theta * s * c;
            double sup = -theta * s * u;
            rhs[1] -= sub * lowNew;
            rhs[nJ - 1] -= sup * highNew;
            // Thomas algorithm on the interior.
            work[1] = sup / diag;
            rhs[1] /= diag;
            for (int j = 2; j < nJ; j++) {
                double den = diag - sub * work[j - 1];
                work[j] = sup / den;
                rhs[j] = (rhs[j] - sub * rhs[j - 1]) / den;
            }
            next[nJ - 1] = rhs[nJ - 1];
            for (int j = nJ - 2; j >= 1; j--) {
                next[j] = rhs[j] - work[j] * next[j + 1];
            }
            next[0] = lowNew;
            next[nJ] = highNew;
            double[] t = v;
            v = next;
            next = t;
        }
    }
}
