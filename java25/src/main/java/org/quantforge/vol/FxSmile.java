package org.quantforge.vol;

import org.quantforge.core.Finite;

import java.util.function.DoubleUnaryOperator;
import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/** Garman-Kohlhagen vanillas, FX delta and ATM conventions, smile from quotes (fx-smile.md, E-A9 to E-A11). */
public final class FxSmile {
    private FxSmile() {}

    public enum DeltaType { SPOT, FORWARD, SPOT_PA, FORWARD_PA }

    public enum AtmType { SPOT, FORWARD, DNS }

    /** Market data for one expiry; {@code phi} is +1 call, -1 put. */
    public record Market(double spot, double t, double rd, double rf) {
        public double forward() {
            return spot * Math.exp((rd - rf) * t);
        }

        double df() {
            return Math.exp(-rf * t);
        }

        double dd() {
            return Math.exp(-rd * t);
        }
    }

    public static void checkMarket(Market m, double vol) {
        Finite.check("vol", vol);
        if (!(m.spot() > 0.0) || !(m.t() > 0.0) || !(vol > 0.0)) {
            throw new QfError("E_DOMAIN", "spot, expiry_years and vol must be above 0");
        }
    }

    private static double d1(double f, double k, double v, double t) {
        double s = v * Math.sqrt(t);
        return Math.log(f / k) / s + s / 2.0;
    }

    public record Price(double price, double premiumPctForeign, double forward, double delta, double gamma,
                        double vega) {}

    public static Price price(Market m, double k, double v, double phi, double notional) {
        Finite.check("k", k);
        Finite.check("v", v);
        Finite.check("phi", phi);
        Finite.check("notional", notional);
        double f = m.forward();
        double t = m.t();
        double d1 = d1(f, k, v, t);
        double d2 = d1 - v * Math.sqrt(t);
        double p = phi * m.dd() * (f * Normal.cdf(phi * d1) - k * Normal.cdf(phi * d2));
        double n = Normal.pdf(d1);
        return new Price(notional * p, p / m.spot(), f, notional * phi * m.df() * Normal.cdf(phi * d1),
                notional * m.df() * n / (m.spot() * v * Math.sqrt(t)), notional * m.spot() * m.df() * n * Math.sqrt(t));
    }

    public static double delta(Market m, double k, double v, double phi, DeltaType type) {
        Finite.check("k", k);
        Finite.check("v", v);
        Finite.check("phi", phi);
        double f = m.forward();
        double d1 = d1(f, k, v, m.t());
        double d2 = d1 - v * Math.sqrt(m.t());
        return switch (type) {
            case SPOT -> phi * m.df() * Normal.cdf(phi * d1);
            case FORWARD -> phi * Normal.cdf(phi * d1);
            case SPOT_PA -> phi * m.df() * (k / f) * Normal.cdf(phi * d2);
            case FORWARD_PA -> phi * (k / f) * Normal.cdf(phi * d2);
        };
    }

    private static boolean premiumAdjusted(DeltaType type) {
        return type == DeltaType.SPOT_PA || type == DeltaType.FORWARD_PA;
    }

    /** The strike of maximum PA call delta: {@code v sqrt T N(d2) = n(d2)} (ruling E-A10). */
    static double maxDeltaStrike(Market m, double v) {
        double s = v * Math.sqrt(m.t());
        double d2 = bisect(x -> s * Normal.cdf(x) - Normal.pdf(x), -s, 40.0);
        return m.forward() * Math.exp(-s * d2 - s * s / 2.0);
    }

    /** The strike with the given delta; PA calls take the root above the maximum-delta strike. */
    public static double strike(Market m, double delta, double v, double phi, DeltaType type) {
        Finite.check("delta", delta);
        Finite.check("v", v);
        Finite.check("phi", phi);
        if (!(phi * delta > 0.0)) {
            throw new QfError("E_DOMAIN", "a call delta must be above 0 and a put delta below 0", "delta");
        }
        double lnF = Math.log(m.forward());
        DoubleUnaryOperator g = x -> delta(m, Math.exp(x), v, phi, type) - delta;
        if (!premiumAdjusted(type)) {
            double cap = type == DeltaType.SPOT ? m.df() : 1.0;
            if (!(Math.abs(delta) < cap)) {
                throw new QfError("E_DOMAIN", "delta is beyond its range", "delta");
            }
            return Math.exp(bracketed(g, lnF));
        }
        if (phi < 0.0) {
            return Math.exp(bracketed(g, lnF));
        }
        double kStar = maxDeltaStrike(m, v);
        double lo = Math.log(kStar);
        if (!(g.applyAsDouble(lo) > 0.0)) {
            throw new QfError("E_DOMAIN", "delta is at or above the maximum premium-adjusted call delta", "delta");
        }
        double hi = lo + 1.0;
        for (int i = 0; i < 200 && g.applyAsDouble(hi) > 0.0; i++) {
            hi = lo + 2.0 * (hi - lo);
        }
        return Math.exp(bisect(g, lo, hi));
    }

    /** Root of a monotone g in x = ln K, bracket grown from ln F. */
    private static double bracketed(DoubleUnaryOperator g, double centre) {
        double w = 1.0;
        for (int i = 0; i < 200 && Math.signum(g.applyAsDouble(centre - w)) == Math.signum(g.applyAsDouble(centre + w));
             i++) {
            w *= 2.0;
        }
        return bisect(g, centre - w, centre + w);
    }

    /** Bisection to the last representable midpoint; g(a) and g(b) differ in sign. */
    static double bisect(DoubleUnaryOperator g, double a, double b) {
        double ga = g.applyAsDouble(a);
        for (int i = 0; i < 2000; i++) {
            double mid = 0.5 * (a + b);
            if (mid <= Math.min(a, b) || mid >= Math.max(a, b)) {
                break;
            }
            double gm = g.applyAsDouble(mid);
            if (gm == 0.0) {
                return mid;
            }
            if ((gm > 0.0) == (ga > 0.0)) {
                a = mid;
                ga = gm;
            } else {
                b = mid;
            }
        }
        return 0.5 * (a + b);
    }

    public static double atmStrike(Market m, double v, AtmType atm, DeltaType type) {
        Finite.check("v", v);
        double f = m.forward();
        return switch (atm) {
            case SPOT -> m.spot();
            case FORWARD -> f;
            case DNS -> f * Math.exp((premiumAdjusted(type) ? -0.5 : 0.5) * v * v * m.t());
        };
    }
}
