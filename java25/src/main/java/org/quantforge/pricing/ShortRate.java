package org.quantforge.pricing;

import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/**
 * Stage G one-factor short-rate models: Vasicek, CIR and Hull-White bond prices and bond options, and the
 * Jamshidian swaption on Hull-White (short-rate-models.md, rulings G-1 to G-6, G-12, G-13).
 */
public final class ShortRate {
    private ShortRate() {}

    public enum Model { VASICEK, CIR, HULL_WHITE }

    /** Log-linear discount curve with (0, 1) as the first node and a flat forward beyond the last pillar. */
    public static final class Curve {
        private final double[] t;
        private final double[] lnP;

        public Curve(double[] times, double[] discountFactors) {
            if (times.length == 0 || times.length != discountFactors.length) {
                throw new QfError("E_INPUT", "curve needs matching, non-empty times and discount_factors", "curve");
            }
            this.t = new double[times.length + 1];
            this.lnP = new double[times.length + 1];
            for (int i = 0; i < times.length; i++) {
                if (!(times[i] > t[i])) {
                    throw new QfError("E_INPUT", "pillar times must be positive and strictly increasing", "curve");
                }
                t[i + 1] = times[i];
            }
            for (int i = 0; i < times.length; i++) {
                if (!(discountFactors[i] > 0.0)) {
                    throw new QfError("E_DOMAIN", "discount factors must be positive", "curve");
                }
                lnP[i + 1] = Math.log(discountFactors[i]);
            }
        }

        private int section(double x) {
            int i = 0;
            while (i < t.length - 2 && x >= t[i + 1]) {
                i++;
            }
            return i;
        }

        /** P(0, x). */
        public double df(double x) {
            int i = section(x);
            double slope = (lnP[i + 1] - lnP[i]) / (t[i + 1] - t[i]);
            return Math.exp(lnP[i] + slope * (x - t[i]));
        }

        /** Instantaneous forward f(0, x), right-hand at a pillar (ruling G-3). */
        public double forward(double x) {
            int i = section(x);
            return -(lnP[i + 1] - lnP[i]) / (t[i + 1] - t[i]);
        }
    }

    /** Parameters of one model; {@code b} is unused by Hull-White, {@code curve} only by Hull-White. */
    public record Params(Model model, double a, double sigma, double b, Curve curve) {}

    // ---- factors ----

    private static final int SERIES_TERMS = 24;

    /** Coefficients h_n of (2 (f1 - 1) + x f1^2) / x^2 = sum h_n x^(n-2), f1 = (1 - e^-x) / x. */
    private static final double[] H = seriesH();

    private static double[] seriesH() {
        double[] c = new double[SERIES_TERMS + 2];
        double fact = 1.0;
        for (int k = 0; k < c.length; k++) {
            fact *= k + 1;
            c[k] = (k % 2 == 0 ? 1.0 : -1.0) / fact;
        }
        double[] h = new double[SERIES_TERMS];
        for (int n = 2; n < SERIES_TERMS; n++) {
            double sq = 0.0; // coefficient of x^(n-1) in f1^2
            for (int i = 0; i <= n - 1; i++) {
                sq += c[i] * c[n - 1 - i];
            }
            h[n] = 2.0 * c[n] + sq;
        }
        return h;
    }

    /** B = (1 - e^(-a tau)) / a without cancellation. */
    static double bFactor(double a, double tau) {
        return -Math.expm1(-a * tau) / a;
    }

    /** (B - tau) without cancellation (series for a tau below 1, ruling G-2). */
    private static double bMinusTau(double a, double tau) {
        double x = a * tau;
        if (x >= 1.0) {
            return bFactor(a, tau) - tau;
        }
        double sum = 0.0;
        double fact = 1.0;
        double pow = 1.0;
        for (int k = 1; k < SERIES_TERMS; k++) {
            fact *= k + 1;
            pow *= -x;
            sum += pow / fact;
        }
        return tau * sum;
    }

    /** (2 (B - tau) + a B^2) / a^2, finite as a goes to 0. */
    private static double gOverA2(double a, double tau) {
        double x = a * tau;
        if (x >= 1.0) {
            double b = bFactor(a, tau);
            return (2.0 * (b - tau) + a * b * b) / (a * a);
        }
        double sum = 0.0;
        double pow = 1.0;
        for (int n = 2; n < SERIES_TERMS; n++) {
            sum += H[n] * pow;
            pow *= x;
        }
        return tau * tau * tau * sum;
    }

    private static double vasicekLnA(Params p, double tau) {
        return p.b() * bMinusTau(p.a(), tau) - p.sigma() * p.sigma() / 4.0 * gOverA2(p.a(), tau);
    }

    private static double cirGamma(Params p) {
        return Math.sqrt(p.a() * p.a() + 2.0 * p.sigma() * p.sigma());
    }

    private static double cirB(Params p, double tau) {
        double g = cirGamma(p);
        double den = (g + p.a()) * Math.expm1(g * tau) + 2.0 * g;
        return 2.0 * Math.expm1(g * tau) / den;
    }

    private static double cirLnA(Params p, double tau) {
        double g = cirGamma(p);
        double den = (g + p.a()) * Math.expm1(g * tau) + 2.0 * g;
        double ln = Math.log(2.0 * g) + (p.a() + g) * tau / 2.0 - Math.log(den);
        return 2.0 * p.a() * p.b() / (p.sigma() * p.sigma()) * ln;
    }

    /** P(t, T) given the short rate r at t. */
    public static double zcb(Params p, double r, double t, double maturity) {
        double tau = maturity - t;
        return switch (p.model()) {
            case VASICEK -> Math.exp(vasicekLnA(p, tau) - bFactor(p.a(), tau) * r);
            case CIR -> Math.exp(cirLnA(p, tau) - cirB(p, tau) * r);
            case HULL_WHITE -> {
                double b = bFactor(p.a(), tau);
                double v = p.sigma() * p.sigma() / (4.0 * p.a()) * -Math.expm1(-2.0 * p.a() * t) * b * b;
                double lnA = Math.log(p.curve().df(maturity) / p.curve().df(t)) + b * p.curve().forward(t) - v;
                yield Math.exp(lnA - b * r);
            }
        };
    }

    // ---- bond options ----

    /** Call on a bond (maturity s) struck at k at expiry t; the put follows by parity. */
    public static double bondOption(Params p, double r, boolean call, double k, double t, double s) {
        double pt;
        double ps;
        double callValue;
        switch (p.model()) {
            case CIR -> {
                pt = zcb(p, r, 0.0, t);
                ps = zcb(p, r, 0.0, s);
                callValue = cirCall(p, r, k, t, s, pt, ps);
            }
            default -> {
                if (p.model() == Model.VASICEK) {
                    pt = zcb(p, r, 0.0, t);
                    ps = zcb(p, r, 0.0, s);
                } else {
                    pt = p.curve().df(t);
                    ps = p.curve().df(s);
                }
                callValue = gaussianCall(p.a(), p.sigma(), k, t, s, pt, ps);
            }
        }
        return call ? callValue : callValue - ps + k * pt;
    }

    /** Vasicek and Hull-White bond call [J89]. */
    public static double gaussianCall(double a, double sigma, double k, double t, double s, double pt, double ps) {
        double sp = sigma * bFactor(a, s - t) * Math.sqrt(-Math.expm1(-2.0 * a * t) / (2.0 * a));
        return gaussianCallSp(sp, k, pt, ps);
    }

    /** The Gaussian bond call for a given total volatility sp. */
    public static double gaussianCallSp(double sp, double k, double pt, double ps) {
        double h = Math.log(ps / (k * pt)) / sp + sp / 2.0;
        return ps * Normal.cdf(h) - k * pt * Normal.cdf(h - sp);
    }

    private static double cirCall(Params p, double r, double k, double t, double s, double pt, double ps) {
        double g = cirGamma(p);
        double sig2 = p.sigma() * p.sigma();
        double rho = 2.0 * g / (sig2 * Math.expm1(g * t));
        double psi = (p.a() + g) / sig2;
        double tau = s - t;
        double bb = cirB(p, tau);
        double rbar = (cirLnA(p, tau) - Math.log(k)) / bb;
        double kk = 4.0 * p.a() * p.b() / sig2;
        double e = r * 2.0 * rho * rho * Math.exp(g * t);
        double d1 = rho + psi + bb;
        double d2 = rho + psi;
        return ps * chi2Cdf(2.0 * rbar * d1, kk, e / d1) - k * pt * chi2Cdf(2.0 * rbar * d2, kk, e / d2);
    }

    // ---- noncentral chi-square ----

    private static final double[] LANCZOS = {0.99999999999980993, 676.5203681218851, -1259.1392167224028,
        771.32342877765313, -176.61502916214059, 12.507343278686905, -0.13857109526572012,
        9.9843695780195716e-6, 1.5056327351493116e-7};

    /** ln Gamma(x) for x > 0 (Lanczos, g = 7). */
    static double lgamma(double x) {
        if (x < 0.5) {
            return Math.log(Math.PI / Math.abs(Math.sin(Math.PI * x))) - lgamma(1.0 - x);
        }
        double xm = x - 1.0;
        double sum = LANCZOS[0];
        for (int i = 1; i < 9; i++) {
            sum += LANCZOS[i] / (xm + i);
        }
        double tt = xm + 7.5;
        return 0.5 * Math.log(2.0 * Math.PI) + (xm + 0.5) * Math.log(tt) - tt + Math.log(sum);
    }

    /** Regularised lower incomplete gamma P(s, x): series below s + 1, continued fraction above. */
    static double gammaP(double s, double x) {
        if (x <= 0.0) {
            return 0.0;
        }
        double lead = s * Math.log(x) - x - lgamma(s);
        if (x < s + 1.0) {
            double term = 1.0 / s;
            double sum = term;
            for (int n = 1; n < 100000; n++) {
                term *= x / (s + n);
                sum += term;
                if (term < sum * 1e-17) {
                    break;
                }
            }
            return sum * Math.exp(lead);
        }
        double tiny = 1e-300;
        double b = x + 1.0 - s;
        double c = 1.0 / tiny;
        double d = 1.0 / b;
        double h = d;
        for (int i = 1; i < 100000; i++) {
            double an = -i * (i - s);
            b += 2.0;
            d = an * d + b;
            if (Math.abs(d) < tiny) {
                d = tiny;
            }
            c = b + an / c;
            if (Math.abs(c) < tiny) {
                c = tiny;
            }
            d = 1.0 / d;
            double del = d * c;
            h *= del;
            if (Math.abs(del - 1.0) < 1e-16) {
                break;
            }
        }
        return 1.0 - Math.exp(lead) * h;
    }

    /** Noncentral chi-square CDF with k degrees of freedom and noncentrality lambda, by the Poisson series. */
    static double chi2Cdf(double x, double k, double lambda) {
        if (x <= 0.0) {
            return 0.0;
        }
        double mu = lambda / 2.0;
        double s0 = k / 2.0;
        double sum = 0.0;
        if (mu == 0.0) {
            return gammaP(s0, x / 2.0);
        }
        double logMu = Math.log(mu);
        double lnFact = 0.0;
        for (int j = 0; j < 100000; j++) {
            if (j > 0) {
                lnFact += Math.log(j);
            }
            double w = Math.exp(-mu + j * logMu - lnFact);
            double term = w * gammaP(s0 + j, x / 2.0);
            sum += term;
            if (j > mu + 10.0 && term < 1e-17 * sum) {
                break;
            }
        }
        return Math.min(sum, 1.0);
    }

    // ---- Jamshidian swaption ----

    public record Swaption(double price, double forwardSwapRate, double annuity) {}

    /** European swaption on Hull-White; coupons are fixed-rate times accruals, plus 1 on the last. */
    public static Swaption swaption(Params p, double t0, double[] pay, double rate, boolean payer, double notional) {
        int n = pay.length;
        double[] tau = new double[n];
        double[] c = new double[n];
        double annuity = 0.0;
        for (int i = 0; i < n; i++) {
            tau[i] = pay[i] - (i == 0 ? t0 : pay[i - 1]);
            c[i] = rate * tau[i] + (i == n - 1 ? 1.0 : 0.0);
            annuity += tau[i] * p.curve().df(pay[i]);
        }
        double fwd = (p.curve().df(t0) - p.curve().df(pay[n - 1])) / annuity;
        double rStar = criticalRate(p, t0, pay, c);
        double total = 0.0;
        for (int i = 0; i < n; i++) {
            double x = zcb(p, rStar, t0, pay[i]);
            double call = gaussianCall(p.a(), p.sigma(), x, t0, pay[i], p.curve().df(t0), p.curve().df(pay[i]));
            double v = payer ? call - p.curve().df(pay[i]) + x * p.curve().df(t0) : call;
            total += c[i] * v;
        }
        return new Swaption(notional * total, fwd, notional * annuity);
    }

    private static double criticalRate(Params p, double t0, double[] pay, double[] c) {
        double r = 0.0;
        for (int it = 0; it < 200; it++) {
            double f = -1.0;
            double d = 0.0;
            for (int i = 0; i < pay.length; i++) {
                double pi = zcb(p, r, t0, pay[i]);
                f += c[i] * pi;
                d -= c[i] * pi * bFactor(p.a(), pay[i] - t0);
            }
            if (Math.abs(f) <= 1e-15) {
                return r;
            }
            r -= f / d;
        }
        throw new QfError("E_NO_CONVERGENCE", "critical rate did not converge");
    }
}
