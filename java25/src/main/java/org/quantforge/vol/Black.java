package org.quantforge.vol;

import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/** Black-Scholes, Black-76, Bachelier (black-models.md). One option in forward terms. */
public final class Black {
    private Black() {}

    public enum Model { BLACK_SCHOLES, BLACK_76, BACHELIER }

    public enum OptionType { CALL, PUT }

    /** {@code underlying} is spot for BLACK_SCHOLES, else the unshifted forward. */
    public record Option(Model model, double phi, double strike, double t, double underlying, double rate, double yield,
                         double discount, double shift) {
        public boolean normal() {
            return model == Model.BACHELIER;
        }

        public double forward() {
            return model == Model.BLACK_SCHOLES ? underlying * Math.exp((rate - yield) * t) : underlying;
        }

        public double df() {
            return model == Model.BLACK_SCHOLES ? Math.exp(-rate * t) : discount;
        }

        public Option withUnderlying(double u) {
            return new Option(model, phi, strike, t, u, rate, yield, discount, shift);
        }

        /** Checks shared by price and implied vol. */
        public void check(double vol) {
            if (t < 0.0 || vol < 0.0) {
                throw new QfError("E_DOMAIN", "expiry_years or vol is negative");
            }
            if (model != Model.BLACK_SCHOLES && discount <= 0.0) {
                throw new QfError("E_DOMAIN", "discount_factor is not positive");
            }
            if (!normal() && (underlying + shift <= 0.0 || strike + shift <= 0.0)) {
                throw new QfError("E_DOMAIN", "underlying or strike is not positive");
            }
        }
    }

    public static double phi(OptionType type) {
        return type == OptionType.CALL ? 1.0 : -1.0;
    }

    public static double price(Option o, double vol) {
        double f = o.forward() + o.shift();
        double x = o.strike() + o.shift();
        return o.normal() ? normal(o.phi(), f, x, o.t(), o.df(), vol) : lognormal(o.phi(), f, x, o.t(), o.df(), vol);
    }

    public static double lognormal(double phi, double f, double x, double t, double d, double v) {
        if (t == 0.0 || v == 0.0) {
            return d * Math.max(phi * (f - x), 0.0);
        }
        double s = v * Math.sqrt(t);
        double d1 = (Math.log(f / x) + v * v * t / 2.0) / s;
        double d2 = d1 - s;
        return d * phi * (f * Normal.cdf(phi * d1) - x * Normal.cdf(phi * d2));
    }

    public static double normal(double phi, double f, double x, double t, double d, double v) {
        if (t == 0.0 || v == 0.0) {
            return d * Math.max(phi * (f - x), 0.0);
        }
        double s = v * Math.sqrt(t);
        double z = (f - x) / s;
        return d * (phi * (f - x) * Normal.cdf(phi * z) + s * Normal.pdf(z));
    }

    private static double vega(boolean normal, double f, double x, double t, double d, double v) {
        double r = Math.sqrt(t);
        if (normal) {
            return d * r * Normal.pdf((f - x) / (v * r));
        }
        return d * f * r * Normal.pdf((Math.log(f / x) + v * v * t / 2.0) / (v * r));
    }

    public static double implied(Option o, double price) {
        o.check(0.0);
        if (o.t() == 0.0) {
            throw new QfError("E_DOMAIN", "expiry_years is zero");
        }
        double f = o.forward() + o.shift();
        double x = o.strike() + o.shift();
        double d = o.df();
        double intrinsic = d * Math.max(o.phi() * (f - x), 0.0);
        if (price < intrinsic) {
            throw new QfError("E_DOMAIN", "price is below intrinsic");
        }
        if (!o.normal() && price >= (o.phi() > 0 ? d * f : d * x)) {
            throw new QfError("E_DOMAIN", "price is at or above its upper bound");
        }
        if (price == intrinsic) {
            return 0.0;
        }
        return solve(o.normal(), o.phi(), f, x, o.t(), d, price);
    }

    /** Newton inside a bracket. V is increasing in vol, so a bisection step is always safe. */
    public static double solve(boolean normal, double phi, double f, double x, double t, double d, double price) {
        double lo = 0.0;
        double hi = normal ? Math.max(Math.abs(f - x), 1.0) : 1.0;
        while (value(normal, phi, f, x, t, d, hi) < price) {
            lo = hi;
            hi *= 2.0;
            if (hi > 1e300) {
                throw new QfError("E_NO_CONVERGENCE", "no upper bracket for implied vol");
            }
        }
        double v = (lo + hi) / 2.0;
        for (int i = 0; i < 400; i++) {
            double diff = value(normal, phi, f, x, t, d, v) - price;
            if (diff == 0.0) {
                return v;
            }
            if (diff > 0.0) {
                hi = v;
            } else {
                lo = v;
            }
            double vega = vega(normal, f, x, t, d, v);
            double next = vega > 0.0 ? v - diff / vega : Double.NaN;
            if (!(next > lo && next < hi)) {
                next = (lo + hi) / 2.0;
            }
            boolean done = Math.abs(next - v) <= 4e-16 * v;
            v = next;
            if (done) {
                break;
            }
        }
        if (!(Math.abs(value(normal, phi, f, x, t, d, v) - price) <= 1e-13 * Math.max(1.0, price))) {
            throw new QfError("E_NO_CONVERGENCE", "implied vol did not converge");
        }
        return v;
    }

    private static double value(boolean normal, double phi, double f, double x, double t, double d, double v) {
        return normal ? normal(phi, f, x, t, d, v) : lognormal(phi, f, x, t, d, v);
    }
}
