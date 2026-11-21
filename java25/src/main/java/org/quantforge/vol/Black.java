package org.quantforge.vol;

import org.quantforge.core.Finite;

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
        Finite.check("vol", vol);
        double f = o.forward() + o.shift();
        double x = o.strike() + o.shift();
        return o.normal() ? normal(o.phi(), f, x, o.t(), o.df(), vol) : lognormal(o.phi(), f, x, o.t(), o.df(), vol);
    }

    public static double lognormal(double phi, double f, double x, double t, double d, double v) {
        Finite.check("phi", phi);
        Finite.check("f", f);
        Finite.check("x", x);
        Finite.check("t", t);
        Finite.check("d", d);
        Finite.check("v", v);
        if (t == 0.0 || v == 0.0) {
            return d * Math.max(phi * (f - x), 0.0);
        }
        double s = v * Math.sqrt(t);
        double d1 = (Math.log(f / x) + v * v * t / 2.0) / s;
        double d2 = d1 - s;
        return d * phi * (f * Normal.cdf(phi * d1) - x * Normal.cdf(phi * d2));
    }

    public static double normal(double phi, double f, double x, double t, double d, double v) {
        Finite.check("phi", phi);
        Finite.check("f", f);
        Finite.check("x", x);
        Finite.check("t", t);
        Finite.check("d", d);
        Finite.check("v", v);
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
        Finite.check("price", price);
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
        Finite.check("phi", phi);
        Finite.check("f", f);
        Finite.check("x", x);
        Finite.check("t", t);
        Finite.check("d", d);
        Finite.check("price", price);
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
        if (!normal && t > 0.0) {
            return solveLognormal(phi, f, x, t, d, price, lo, hi, v);
        }
        for (int i = 0; i < 400; i++) {
            double val = value(normal, phi, f, x, t, d, v);
            double diff = val - price;
            if (diff == 0.0) {
                return identified(normal, phi, f, x, t, d, v, price);
            }
            if (diff > 0.0) {
                hi = v;
            } else {
                lo = v;
            }
            double vega = vega(normal, f, x, t, d, v);
            // Newton on ln V - ln price (ruling KR-341): the same step near the root, and it keeps its size far
            // out of the money, where V spans hundreds of decades over the bracket.
            double next = vega > 0.0 && val > 0.0 ? v - Math.log(val / price) * val / vega : Double.NaN;
            if (!(next > lo && next < hi)) {
                next = (lo + hi) / 2.0;
            }
            boolean done = Math.abs(next - v) <= 4e-16 * v;
            v = next;
            if (done) {
                break;
            }
        }
        // Accept a tiny price error, or a vol bracket collapsed to a few ulps: there the price formula's own
        // rounding (cancellation in f N(d1) - x N(d2) far from the money) is larger than 1e-13 of the price.
        boolean priced = Math.abs(value(normal, phi, f, x, t, d, v) - price) <= 1e-13 * Math.max(1.0, price);
        boolean collapsed = hi - lo <= 1e-14 * hi && Math.abs(value(normal, phi, f, x, t, d, v) - price) <= 1e-10 * Math.max(1.0, price);
        if (!priced && !collapsed) {
            throw new QfError("E_NO_CONVERGENCE", "implied vol did not converge: f=" + f + " x=" + x + " t=" + t + " d=" + d + " price=" + price + " v=" + v + " value=" + value(normal, phi, f, x, t, d, v));
        }
        return identified(normal, phi, f, x, t, d, v, price);
    }

    /**
     * Returns v if the price identifies the vol in binary64, else E_NO_CONVERGENCE (ruling KR-341). Estimated vol
     * error: (|V(v) - price| + 2^-52 M + 2^-1070 (1 + D (|F| + |K| + v sqrt T)))/(v vega), M the sum of the
     * magnitudes of the two terms of V (they cancel far from the money); above 1e-10 the vol is refused.
     */
    static double identified(boolean normal, double phi, double f, double x, double t, double d, double v, double price) {
        double root = v * Math.sqrt(t);
        double mag;
        if (normal) {
            double z = (f - x) / root;
            mag = d * (Math.abs(f - x) * Normal.cdf(phi * z) + root * Normal.pdf(z));
        } else {
            double d1 = (Math.log(f / x) + v * v * t / 2.0) / root;
            mag = d * (f * Normal.cdf(phi * d1) + x * Normal.cdf(phi * (d1 - root)));
        }
        double scale = v * vega(normal, f, x, t, d, v);
        double error = Math.abs(value(normal, phi, f, x, t, d, v) - price) + 0x1p-52 * mag
                + 0x1p-1070 * (1.0 + d * (Math.abs(f) + Math.abs(x) + root));
        if (!(scale > 0.0) || error > 1e-10 * scale) {
            throw new QfError("E_NO_CONVERGENCE", "the price does not identify the vol in binary64");
        }
        return v;
    }

    /**
     * The lognormal branch of {@link #solve} with t &gt; 0, computing the same floating-point expressions in the
     * same order (so the same iterates, result and errors), but evaluating each one once: ln(F/K) and sqrt(T) are
     * hoisted out of the loop, vega reuses d1 from the price, and the closing checks plus {@link #identified} share
     * one price evaluation and its two N() terms. In the loop v stays inside (lo, hi) with lo &gt;= 0, so v &gt; 0
     * and finite, which is when {@link #lognormal} takes its general branch.
     */
    private static double solveLognormal(double phi, double f, double x, double t, double d, double price,
                                         double lo, double hi, double v) {
        double lf = Math.log(f / x);
        double r = Math.sqrt(t);
        for (int i = 0; i < 400; i++) {
            double s = v * r;
            double d1 = (lf + v * v * t / 2.0) / s;
            double c1 = Normal.cdf(phi * d1);
            double c2 = Normal.cdf(phi * (d1 - s));
            double val = d * phi * (f * c1 - x * c2);
            double diff = val - price;
            if (diff == 0.0) {
                return identifiedLognormal(f, x, d, v, price, s, d1, c1, c2, val, r);
            }
            if (diff > 0.0) {
                hi = v;
            } else {
                lo = v;
            }
            double vega = d * f * r * Normal.pdf(d1);
            // Newton on ln V - ln price (ruling KR-341): the same step near the root, and it keeps its size far
            // out of the money, where V spans hundreds of decades over the bracket.
            double next = vega > 0.0 && val > 0.0 ? v - Math.log(val / price) * val / vega : Double.NaN;
            if (!(next > lo && next < hi)) {
                next = (lo + hi) / 2.0;
            }
            boolean done = Math.abs(next - v) <= 4e-16 * v;
            v = next;
            if (done) {
                break;
            }
        }
        double s = v * r;
        double d1 = (lf + v * v * t / 2.0) / s;
        double c1 = Normal.cdf(phi * d1);
        double c2 = Normal.cdf(phi * (d1 - s));
        double val = d * phi * (f * c1 - x * c2);
        // Accept a tiny price error, or a vol bracket collapsed to a few ulps: there the price formula's own
        // rounding (cancellation in f N(d1) - x N(d2) far from the money) is larger than 1e-13 of the price.
        boolean priced = Math.abs(val - price) <= 1e-13 * Math.max(1.0, price);
        boolean collapsed = hi - lo <= 1e-14 * hi && Math.abs(val - price) <= 1e-10 * Math.max(1.0, price);
        if (!priced && !collapsed) {
            throw new QfError("E_NO_CONVERGENCE", "implied vol did not converge: f=" + f + " x=" + x + " t=" + t + " d=" + d + " price=" + price + " v=" + v + " value=" + val);
        }
        return identifiedLognormal(f, x, d, v, price, s, d1, c1, c2, val, r);
    }

    /** {@link #identified} for the lognormal model, given the terms of V(v) already evaluated at v. */
    private static double identifiedLognormal(double f, double x, double d, double v, double price, double root,
                                              double d1, double c1, double c2, double val, double r) {
        double mag = d * (f * c1 + x * c2);
        double scale = v * (d * f * r * Normal.pdf(d1));
        double error = Math.abs(val - price) + 0x1p-52 * mag
                + 0x1p-1070 * (1.0 + d * (Math.abs(f) + Math.abs(x) + root));
        if (!(scale > 0.0) || error > 1e-10 * scale) {
            throw new QfError("E_NO_CONVERGENCE", "the price does not identify the vol in binary64");
        }
        return v;
    }

    private static double value(boolean normal, double phi, double f, double x, double t, double d, double v) {
        return normal ? normal(phi, f, x, t, d, v) : lognormal(phi, f, x, t, d, v);
    }
}
