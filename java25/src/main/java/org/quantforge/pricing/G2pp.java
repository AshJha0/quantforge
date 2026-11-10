package org.quantforge.pricing;

/** Two-factor Gaussian G2++ bond prices and bond options (short-rate-models.md, ruling G-14). */
public final class G2pp {
    private G2pp() {}

    public record Params(ShortRate.Curve curve, double a, double sigma, double b, double eta, double rho) {}

    private static final int TERMS = 30;

    /** c_k = (-1)^k / (k + 1)!, the coefficients of (1 - e^-x) / x. */
    private static final double[] C = coefficients();

    private static double[] coefficients() {
        double[] c = new double[TERMS + 1];
        double fact = 1.0;
        for (int k = 0; k <= TERMS; k++) {
            fact *= k + 1;
            c[k] = (k % 2 == 0 ? 1.0 : -1.0) / fact;
        }
        return c;
    }

    private static double bf(double a, double tau) {
        return -Math.expm1(-a * tau) / a;
    }

    /** (tau - 2 B + B2) / a^2 for one factor, by series when a tau is below 1. */
    private static double single(double a, double tau) {
        double x = a * tau;
        if (x >= 1.0) {
            return (tau - 2.0 * bf(a, tau) + bf(2.0 * a, tau)) / (a * a);
        }
        double sum = 0.0;
        double pow = 1.0;
        for (int k = 2; k <= TERMS; k++) {
            sum += C[k] * (Math.pow(2.0, k) - 2.0) * pow;
            pow *= x;
        }
        return tau * tau * tau * sum;
    }

    /** (tau - B_a - B_b + B_(a+b)) / (a b). */
    private static double cross(double a, double b, double tau) {
        double xa = a * tau;
        double xb = b * tau;
        if (xa + xb >= 1.0) {
            return (tau - bf(a, tau) - bf(b, tau) + bf(a + b, tau)) / (a * b);
        }
        double sum = 0.0;
        for (int k = 2; k <= TERMS; k++) {
            double inner = 0.0;
            double binom = 1.0; // C(k, j)
            for (int j = 1; j <= k - 1; j++) {
                binom = binom * (k - j + 1) / j;
                inner += binom * Math.pow(xa, j - 1) * Math.pow(xb, k - j - 1);
            }
            sum += C[k] * inner;
        }
        return tau * tau * tau * sum;
    }

    private static double v(Params p, double tau) {
        if (tau == 0.0) {
            return 0.0;
        }
        return p.sigma() * p.sigma() * single(p.a(), tau) + p.eta() * p.eta() * single(p.b(), tau)
                + 2.0 * p.rho() * p.sigma() * p.eta() * cross(p.a(), p.b(), tau);
    }

    /** P(t, T) with factor states x and y at t. */
    public static double zcb(Params p, double x, double y, double t, double maturity) {
        double tau = maturity - t;
        double ln = 0.5 * (v(p, tau) - v(p, maturity) + v(p, t)) - bf(p.a(), tau) * x - bf(p.b(), tau) * y;
        return p.curve().df(maturity) / p.curve().df(t) * Math.exp(ln);
    }

    /** Bond call at expiry t on the bond to s, states starting at zero; the put by parity. */
    public static double bondOption(Params p, boolean call, double k, double t, double s) {
        double u = s - t;
        double ba = bf(p.a(), u);
        double bb = bf(p.b(), u);
        double var = p.sigma() * p.sigma() * ba * ba * -Math.expm1(-2.0 * p.a() * t) / (2.0 * p.a())
                + p.eta() * p.eta() * bb * bb * -Math.expm1(-2.0 * p.b() * t) / (2.0 * p.b())
                + 2.0 * p.rho() * p.sigma() * p.eta() * ba * bb * -Math.expm1(-(p.a() + p.b()) * t)
                / (p.a() + p.b());
        double pt = p.curve().df(t);
        double ps = p.curve().df(s);
        double c = ShortRate.gaussianCallSp(Math.sqrt(var), k, pt, ps);
        return call ? c : c - ps + k * pt;
    }
}
