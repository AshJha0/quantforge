package org.quantforge.pricing;

import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/**
 * Stage G one-factor short-rate models: Vasicek, CIR and Hull-White bond prices and bond options, and the
 * Jamshidian swaption on Hull-White (short-rate-models.md, rulings G-1 to G-6, G-12, G-13).
 */
public final class ShortRate {
    private ShortRate() {}

    /** The one-factor short-rate models of short-rate-models.md. */
    public enum Model {
        /** Vasicek, Gaussian with a constant long-term mean. */
        VASICEK,
        /** Cox-Ingersoll-Ross, square-root diffusion. */
        CIR,
        /** Hull-White, Vasicek fitted to the initial curve. */
        HULL_WHITE
    }

    /** Log-linear discount curve with (0, 1) as the first node and a flat forward beyond the last pillar. */
    public static final class Curve {
        private final double[] t;
        private final double[] lnP;

        /**
         * A curve from its pillars.
         *
         * @param times pillar times in years, increasing
         * @param discountFactors discount factors at the pillars
         */
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

        /**
         * P(0, x).
         *
         * @param x time in years
         * @return the discount factor
         */
        public double df(double x) {
            int i = section(x);
            double slope = (lnP[i + 1] - lnP[i]) / (t[i + 1] - t[i]);
            return Math.exp(lnP[i] + slope * (x - t[i]));
        }

        /**
         * Instantaneous forward f(0, x), right-hand at a pillar (ruling G-3).
         *
         * @param x time in years
         * @return the forward rate
         */
        public double forward(double x) {
            int i = section(x);
            return -(lnP[i + 1] - lnP[i]) / (t[i + 1] - t[i]);
        }
    }

    /**
     * Parameters of one model; {@code b} is unused by Hull-White, {@code curve} only by Hull-White.
     *
     * @param model the model
     * @param a mean reversion
     * @param sigma volatility
     * @param b long-term mean (Vasicek and CIR)
     * @param curve initial discount curve (Hull-White)
     */
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

    /**
     * P(t, T) given the short rate r at t.
     *
     * @param p the model
     * @param r short rate at t
     * @param t valuation time in years
     * @param maturity bond maturity in years
     * @return the zero-coupon bond price
     */
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

    /**
     * Call on a bond (maturity s) struck at k at expiry t; the put follows by parity.
     *
     * @param p the model
     * @param r short rate today
     * @param call true for a call, false for a put
     * @param k strike per unit face
     * @param t option expiry in years
     * @param s bond maturity in years
     * @return the option price per unit face
     */
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

    /**
     * Vasicek and Hull-White bond call [J89].
     *
     * @param a mean reversion
     * @param sigma volatility
     * @param k strike per unit face
     * @param t option expiry in years
     * @param s bond maturity in years
     * @param pt P(0, t)
     * @param ps P(0, s)
     * @return the call price per unit face
     */
    public static double gaussianCall(double a, double sigma, double k, double t, double s, double pt, double ps) {
        double sp = sigma * bFactor(a, s - t) * Math.sqrt(-Math.expm1(-2.0 * a * t) / (2.0 * a));
        return gaussianCallSp(sp, k, pt, ps);
    }

    /**
     * The Gaussian bond call for a given total volatility sp.
     *
     * @param sp total volatility of the bond price ratio
     * @param k strike per unit face
     * @param pt P(0, t)
     * @param ps P(0, s)
     * @return the call price per unit face
     */
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

    /**
     * ln of the Poisson weight {@code e^-mu mu^j / j!}. For {@code j >= 10} by Stirling's series written without
     * the large cancelling terms, so the weight at the mode keeps full relative accuracy when mu is in the thousands.
     */
    static double logPoisson(int j, double mu) {
        if (j < 10) {
            double lf = 0.0;
            for (int i = 2; i <= j; i++) {
                lf += Math.log(i);
            }
            return -mu + j * Math.log(mu) - lf;
        }
        double n = j;
        double d = mu - n;
        double inv = 1.0 / n;
        double inv2 = inv * inv;
        double corr = inv * (1.0 / 12.0 - inv2 * (1.0 / 360.0 - inv2 * (1.0 / 1260.0 - inv2 / 1680.0)));
        return -d + n * Math.log1p(d / n) - 0.5 * Math.log(2.0 * Math.PI * n) - corr;
    }

    /**
     * Noncentral chi-square CDF with k degrees of freedom and noncentrality lambda: the Poisson series summed from
     * its mode with log weights, up then down, until terms fall below 1e-17 of the sum (ruling G-32). A
     * non-positive argument gives 0.
     */
    static double chi2Cdf(double x, double k, double lambda) {
        if (x <= 0.0) {
            return 0.0;
        }
        double mu = lambda / 2.0;
        double s0 = k / 2.0;
        if (mu == 0.0) {
            return gammaP(s0, x / 2.0);
        }
        double half = x / 2.0;
        if (!Double.isFinite(mu) || !Double.isFinite(half) || !Double.isFinite(s0)) {
            // R6-8: an overflowed parameter yields NaN for the caller's E_NON_FINITE guard, at once.
            return Double.NaN;
        }
        int j0 = (int) Math.floor(Math.min(mu, 1e9));
        double w0 = Math.exp(logPoisson(j0, mu));
        if (!Double.isFinite(w0)) {
            return Double.NaN;
        }
        double sum = 0.0;
        double w = w0;
        for (int j = j0; j < j0 + 1_000_000; j++) {
            double term = w * gammaP(s0 + j, half);
            sum += term;
            if (j > mu + 10.0 && term <= 1e-17 * sum) {
                break;
            }
            w *= mu / (j + 1);
        }
        w = w0;
        for (int j = j0 - 1; j >= 0; j--) {
            w *= (j + 1) / mu;
            double term = w * gammaP(s0 + j, half);
            sum += term;
            if (term <= 1e-17 * sum) {
                break;
            }
        }
        return Math.min(sum, 1.0);
    }

    // ---- Jamshidian swaption ----

    /**
     * A Jamshidian swaption result.
     *
     * @param price swaption price
     * @param forwardSwapRate forward par rate of the underlying swap
     * @param annuity annuity of the underlying swap
     */
    public record Swaption(double price, double forwardSwapRate, double annuity) {}

    /**
     * European swaption on Hull-White; coupons are fixed-rate times accruals, plus 1 on the last.
     *
     * @param p the Hull-White model
     * @param t0 expiry and swap start in years
     * @param pay payment times in years, increasing, after t0
     * @param rate fixed rate
     * @param payer true for a payer swaption, false for a receiver
     * @param notional notional
     * @return price, forward swap rate and annuity
     */
    public static Swaption swaption(Params p, double t0, double[] pay, double rate, boolean payer, double notional) {
        return swaption(p, 0.0, t0, pay, rate, payer, notional);
    }

    /**
     * European swaption by Jamshidian under any of the three models (ruling G-20). For Vasicek and CIR the
     * curve is the model's own bonds at {@code r0}; Hull-White ignores {@code r0}.
     *
     * @param p the model
     * @param r0 short rate today (Vasicek and CIR)
     * @param t0 expiry and swap start in years
     * @param pay payment times in years, increasing, after t0
     * @param rate fixed rate
     * @param payer true for a payer swaption, false for a receiver
     * @param notional notional
     * @return price, forward swap rate and annuity
     */
    public static Swaption swaption(Params p, double r0, double t0, double[] pay, double rate, boolean payer,
                                    double notional) {
        int n = pay.length;
        double[] tau = new double[n];
        double[] c = new double[n];
        double annuity = 0.0;
        for (int i = 0; i < n; i++) {
            tau[i] = pay[i] - (i == 0 ? t0 : pay[i - 1]);
            c[i] = rate * tau[i] + (i == n - 1 ? 1.0 : 0.0);
            annuity += tau[i] * df0(p, r0, pay[i]);
        }
        double fwd = (df0(p, r0, t0) - df0(p, r0, pay[n - 1])) / annuity;
        double rStar = criticalRate(p, t0, pay, c);
        double total = 0.0;
        for (int i = 0; i < n; i++) {
            double x = zcb(p, rStar, t0, pay[i]);
            total += c[i] * bondOption(p, r0, !payer, x, t0, pay[i]);
        }
        return new Swaption(notional * total, fwd, notional * annuity);
    }

    /** P(0, t): the curve for Hull-White, the model bond at r0 otherwise. */
    static double df0(Params p, double r0, double t) {
        return p.model() == Model.HULL_WHITE ? p.curve().df(t) : zcb(p, r0, 0.0, t);
    }

    /** The coupon-bond equation {@code sum c_i P(t0, Ti; r) - 1} and its r-derivative. */
    private static double[] couponBond(Params p, double t0, double[] pay, double[] c, double r) {
        double f = -1.0;
        double d = 0.0;
        for (int i = 0; i < pay.length; i++) {
            double pi = zcb(p, r, t0, pay[i]);
            double tau = pay[i] - t0;
            f += c[i] * pi;
            d -= c[i] * pi * (p.model() == Model.CIR ? cirB(p, tau) : bFactor(p.a(), tau));
        }
        return new double[] {f, d};
    }

    /**
     * Jamshidian critical rate: Newton from 0 kept inside the bracket {@code [-1, 1]} ({@code [0, 1]} for CIR),
     * bisecting when a step leaves it (ruling G-29). No sign change on the bracket, or a last coupon
     * {@code c_n <= 0}, is E_DOMAIN.
     */
    static double criticalRate(Params p, double t0, double[] pay, double[] c) {
        if (!(c[c.length - 1] > 0.0)) {
            throw new QfError("E_DOMAIN", "1 + K tau_n <= 0 (ruling G-29)", "fixed_rate");
        }
        double lo = p.model() == Model.CIR ? 0.0 : -1.0;
        double hi = 1.0;
        double flo = couponBond(p, t0, pay, c, lo)[0];
        double fhi = couponBond(p, t0, pay, c, hi)[0];
        if (flo == 0.0) {
            return lo;
        }
        if (flo < 0.0 || fhi > 0.0) {
            String why = p.model() == Model.CIR ? "no non-negative critical rate (ruling G-20)"
                    : "no critical rate on [-1, 1] (ruling G-29)";
            throw new QfError("E_DOMAIN", why, "fixed_rate");
        }
        double r = 0.0;
        for (int it = 0; it < 400; it++) {
            double[] fd = couponBond(p, t0, pay, c, r);
            double f = fd[0];
            if (Math.abs(f) <= 1e-15) {
                return r;
            }
            if (f > 0.0) {
                lo = r;
            } else {
                hi = r;
            }
            double next = r - f / fd[1];
            if (!(next > lo && next < hi)) {
                next = 0.5 * (lo + hi);
            }
            if (Math.abs(next - r) <= 1e-17 * Math.max(1.0, Math.abs(r))) {
                return next;
            }
            r = next;
        }
        throw new QfError("E_NO_CONVERGENCE", "critical rate did not converge");
    }
}
