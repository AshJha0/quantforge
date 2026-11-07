package org.quantforge.vol;

import org.quantforge.core.Normal;
import org.quantforge.core.QfError;

/** Analytic and bumped Greeks (vol-greeks.md). */
public final class Greeks {
    private Greeks() {}

    public record Analytic(double price, double delta, double gamma, double vega, double theta, double rho, double vanna,
                           double volga) {}

    public record Bumped(double delta, double gamma, double vega, double vanna, double volga) {}

    private static void check(Black.Option o, double v) {
        o.check(v);
        if (v <= 0.0 || o.t() <= 0.0) {
            throw new QfError("E_DOMAIN", "vol and expiry_years must be above 0");
        }
    }

    public static Analytic analytic(Black.Option o, double v) {
        check(o, v);
        double p = o.phi();
        double t = o.t();
        double r = Math.sqrt(t);
        double d = o.df();
        double price = Black.price(o, v);
        if (o.normal()) {
            double z = (o.forward() - o.strike()) / (v * r);
            double n = Normal.pdf(z);
            return new Analytic(price, d * p * Normal.cdf(p * z), d * n / (v * r), d * r * n, -d * v * n / (2.0 * r),
                    -t * price, -d * n * z / v, d * r * n * z * z / v);
        }
        double f = o.forward() + o.shift();
        double x = o.strike() + o.shift();
        double d1 = (Math.log(f / x) + v * v * t / 2.0) / (v * r);
        double d2 = d1 - v * r;
        double n = Normal.pdf(d1);
        if (o.model() == Black.Model.BLACK_SCHOLES) {
            double s = o.underlying();
            double q = Math.exp(-o.yield() * t);
            double vega = s * q * n * r;
            double theta = -s * q * n * v / (2.0 * r) - p * o.rate() * x * d * Normal.cdf(p * d2)
                    + p * o.yield() * s * q * Normal.cdf(p * d1);
            return new Analytic(price, q * p * Normal.cdf(p * d1), q * n / (s * v * r), vega, theta,
                    p * x * t * d * Normal.cdf(p * d2), -q * n * d2 / v, vega * d1 * d2 / v);
        }
        double vega = d * f * n * r;
        return new Analytic(price, d * p * Normal.cdf(p * d1), d * n / (f * v * r), vega, -d * f * n * v / (2.0 * r),
                -t * price, -d * n * d2 / v, vega * d1 * d2 / v);
    }

    public static Bumped bumped(Black.Option o, double v) {
        check(o, v);
        double u = o.underlying();
        double hu = o.normal() ? 1e-4 * Math.max(Math.abs(u), 1.0) : 1e-4 * (u + o.shift());
        double hv = 1e-3 * v;
        Black.Option up = o.withUnderlying(u + hu);
        Black.Option dn = o.withUnderlying(u - hu);
        double mid = Black.price(o, v);
        double vu = Black.price(up, v);
        double vd = Black.price(dn, v);
        double sp = Black.price(o, v + hv);
        double sm = Black.price(o, v - hv);
        return new Bumped((vu - vd) / (2.0 * hu), (vu - 2.0 * mid + vd) / (hu * hu), (sp - sm) / (2.0 * hv),
                (Black.price(up, v + hv) - Black.price(up, v - hv) - Black.price(dn, v + hv) + Black.price(dn, v - hv))
                        / (4.0 * hu * hv),
                (sp - 2.0 * mid + sm) / (hv * hv));
    }
}
