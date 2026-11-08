package org.quantforge.pricing;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import org.quantforge.core.Integration;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;
import org.quantforge.core.Rng;
import org.quantforge.vol.Black;

/** Stage E8: CDS options on a stylised forward CDS, default copulas, the large homogeneous pool
 * (credit-options-and-copulas.md, rulings E-B22 to E-B26). */
public final class CreditOptions {
    private CreditOptions() {}

    private static final double[][] GL = Integration.legendre(64);

    /** Composite 64-node Gauss-Legendre over equal panels. */
    static double integrate(java.util.function.DoubleUnaryOperator f, double a, double b, int panels) {
        double w = (b - a) / panels;
        double sum = 0.0;
        for (int p = 0; p < panels; p++) {
            double lo = a + p * w;
            for (int i = 0; i < GL[0].length; i++) {
                sum += GL[1][i] * f.applyAsDouble(lo + w / 2 * (1 + GL[0][i]));
            }
        }
        return sum * w / 2;
    }

    // ---- CDS options ----

    public record Legs(double protection, double annuity) {
        public double forward() {
            return protection / annuity;
        }
    }

    private static double years(LocalDate asOf, LocalDate d) {
        return ChronoUnit.DAYS.between(asOf, d) / 365.0;
    }

    /** The forward CDS of ruling E-B22, per unit notional. */
    public static Legs legs(LocalDate asOf, LocalDate expiry, LocalDate maturity, double r, double h, double rec) {
        double prot = 0.0;
        double ann = 0.0;
        LocalDate a = expiry;
        for (int k = 1; a.isBefore(maturity); k++) {
            LocalDate next = expiry.plusMonths(3L * k);
            LocalDate b = next.isAfter(maturity) ? maturity : next;
            long days = ChronoUnit.DAYS.between(a, b);
            LocalDate m = a.plusDays(days / 2);
            double sa = Math.exp(-h * years(asOf, a));
            double sb = Math.exp(-h * years(asOf, b));
            double pm = Math.exp(-r * years(asOf, m));
            prot += (1 - rec) * pm * (sa - sb);
            ann += days / 360.0 * Math.exp(-r * years(asOf, b)) * sb
                    + ChronoUnit.DAYS.between(a, m) / 360.0 * pm * (sa - sb);
            a = b;
        }
        return new Legs(prot, ann);
    }

    public static void checkOption(LocalDate asOf, LocalDate expiry, LocalDate maturity, double h, double rec,
                                   double k) {
        if (!expiry.isAfter(asOf) || !maturity.isAfter(expiry)) {
            throw new QfError("E_INPUT", "need as_of < expiry < maturity", "expiry");
        }
        if (!(rec >= 0.0 && rec < 1.0) || !(h >= 0.0) || !(k > 0.0)) {
            throw new QfError("E_DOMAIN", "recovery, hazard_rate or strike out of range");
        }
    }

    public record OptionPrice(double price, double forward, double annuity, double frontEnd) {}

    public static OptionPrice price(LocalDate asOf, LocalDate expiry, LocalDate maturity, double r, double h,
                                    double rec, boolean payer, double k, double n, double vol, boolean knockOut) {
        Legs l = legs(asOf, expiry, maturity, r, h, rec);
        double t = years(asOf, expiry);
        double fep = n * (1 - rec) * (1 - Math.exp(-h * t)) * Math.exp(-r * t);
        double opt = n * l.annuity() * Black.lognormal(payer ? 1.0 : -1.0, l.forward(), k, t, 1.0, vol);
        return new OptionPrice(opt + (payer && !knockOut ? fep : 0.0), l.forward(), l.annuity(), fep);
    }

    /** Knock-out options only (ruling E-B23); bisection on vol to the last midpoint. */
    public static double impliedVol(LocalDate asOf, LocalDate expiry, LocalDate maturity, double r, double h,
                                    double rec, boolean payer, double k, double n, double premium) {
        Legs l = legs(asOf, expiry, maturity, r, h, rec);
        double t = years(asOf, expiry);
        double f = l.forward();
        double scale = n * l.annuity();
        double lower = scale * Math.max(payer ? f - k : k - f, 0.0);
        double upper = scale * (payer ? f : k);
        if (!(premium > lower) || !(premium < upper)) {
            throw new QfError("E_DOMAIN", "premium is outside the no-arbitrage range", "premium");
        }
        java.util.function.DoubleUnaryOperator g = v -> scale * Black.lognormal(payer ? 1.0 : -1.0, f, k, t, 1.0, v)
                - premium;
        double hi = 1.0;
        for (int i = 0; i < 200 && g.applyAsDouble(hi) < 0.0; i++) {
            hi *= 2.0;
        }
        return RatesVol.bisect(g, 0.0, hi);
    }

    // ---- normal and t distributions ----

    /** Inverse normal: AS 241 refined by one Newton step. */
    public static double inverseNormal(double p) {
        double x = Rng.ppnd16(p);
        return x - (Normal.cdf(x) - p) / Normal.pdf(x);
    }

    /** Bivariate normal CDF, Drezner-Wesolowsky in the arcsine variable. */
    public static double bivariateNormal(double h, double k, double rho) {
        if (rho == 0.0) {
            return Normal.cdf(h) * Normal.cdf(k);
        }
        double top = Math.asin(rho);
        double integral = integrate(th -> {
            double c = Math.cos(th);
            return Math.exp(-(h * h - 2 * h * k * Math.sin(th) + k * k) / (2 * c * c));
        }, 0.0, top, 8);
        return Normal.cdf(h) * Normal.cdf(k) + integral / (2 * Math.PI);
    }

    /** E_W[f(sqrt(W/nu))] for W chi-square(nu), by log-space quadrature normalised on its own grid. */
    private static double mixture(double nu, java.util.function.DoubleUnaryOperator f) {
        double a = nu / 2.0;
        // density of u = W/nu is proportional to u^(a-1) e^(-a u); in z = ln u, to e^(a z - a e^z)
        // below lo the mass is negligible: the e^(a z) tail for small a, the Gaussian-like bump (width 1/sqrt a) for large a
        double lo = -(40.0 / a + 12.0 / Math.sqrt(a));
        double hi = Math.log(1.0 + 40.0 / Math.sqrt(a) + 40.0 / a);
        double den = integrate(z -> Math.exp(a * z - a * Math.exp(z) + a), lo, hi, 64);
        double num = integrate(z -> Math.exp(a * z - a * Math.exp(z) + a) * f.applyAsDouble(Math.exp(z / 2)), lo, hi,
                64);
        return num / den;
    }

    public static double studentCdf(double x, double nu) {
        return mixture(nu, s -> Normal.cdf(x * s));
    }

    public static double studentInverse(double p, double nu) {
        double lo = -1.0;
        double hi = 1.0;
        while (studentCdf(lo, nu) > p) {
            lo *= 2;
        }
        while (studentCdf(hi, nu) < p) {
            hi *= 2;
        }
        double l = lo;
        double h = hi;
        return RatesVol.bisect(x -> studentCdf(x, nu) - p, l, h);
    }

    public static double bivariateStudent(double x, double y, double rho, double nu) {
        return mixture(nu, s -> bivariateNormal(x * s, y * s, rho));
    }

    // ---- copula and LHP ----

    public enum Copula { GAUSSIAN, STUDENT_T }

    /** {joint default probability, default correlation}. */
    public static double[] jointDefault(Copula c, double p1, double p2, double rho, double nu) {
        double joint = c == Copula.GAUSSIAN
                ? bivariateNormal(inverseNormal(p1), inverseNormal(p2), rho)
                : bivariateStudent(studentInverse(p1, nu), studentInverse(p2, nu), rho, nu);
        return new double[] {joint, (joint - p1 * p2) / Math.sqrt(p1 * (1 - p1) * p2 * (1 - p2))};
    }

    public static void checkPool(double p, double rho, double rec) {
        if (!(p > 0.0 && p < 1.0) || !(rho > 0.0 && rho < 1.0) || !(rec >= 0.0 && rec < 1.0)) {
            throw new QfError("E_DOMAIN", "default_probability, correlation or recovery out of range");
        }
    }

    /** E[min(P(M), k)] in closed form (ruling E-B25). */
    static double expectedMin(double p, double rho, double k) {
        if (k >= 1.0) {
            return p;
        }
        if (k <= 0.0) {
            return 0.0;
        }
        double c = inverseNormal(p);
        double m = (c - Math.sqrt(1 - rho) * inverseNormal(k)) / Math.sqrt(rho);
        return p - (bivariateNormal(c, m, Math.sqrt(rho)) - k * Normal.cdf(m));
    }

    public static double trancheLoss(double p, double rho, double rec, double a, double d) {
        double ea = a == 0.0 ? 0.0 : expectedMin(p, rho, Math.min(a / (1 - rec), 1.0));
        double ed = expectedMin(p, rho, Math.min(d / (1 - rec), 1.0));
        return (1 - rec) * (ed - ea) / (d - a);
    }

    public static double lossCdf(double p, double rho, double rec, double x) {
        return Normal.cdf((Math.sqrt(1 - rho) * inverseNormal(x / (1 - rec)) - inverseNormal(p)) / Math.sqrt(rho));
    }
}
