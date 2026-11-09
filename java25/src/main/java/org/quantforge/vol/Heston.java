package org.quantforge.vol;

import org.quantforge.core.Finite;

import java.util.function.Function;
import org.quantforge.core.Integration;
import org.quantforge.core.QfError;

/** Heston, Bates and Merton prices by Lewis's integral, and Merton's series (heston-family.md, E-A12, E-A13). */
public final class Heston {
    private Heston() {}

    /** Recipe of ruling E-A26: 1024 nodes on [0, 200/sqrt(min(T, 1))]. */
    public static final int NODES = 1024;
    public static final double U_MAX = 200.0;
    private static final double[][] GL = Integration.legendre(NODES);

    public record Params(double v0, double kappa, double theta, double xi, double rho) {
        public void check() {
            if (!(v0 > 0.0) || !(kappa > 0.0) || !(theta > 0.0) || !(xi > 0.0) || !(Math.abs(rho) < 1.0)) {
                throw new QfError("E_DOMAIN", "heston parameters", "heston");
            }
        }
    }

    public record Jumps(double intensity, double mean, double vol) {
        public void check() {
            if (!(intensity >= 0.0) || !Double.isFinite(mean) || !(vol >= 0.0)) {
                throw new QfError("E_DOMAIN", "jump parameters", "jumps");
            }
        }

        double kbar() {
            return Math.exp(mean + vol * vol / 2.0) - 1.0;
        }
    }

    /** Minimal complex arithmetic. */
    public record C(double re, double im) {
        static C of(double re) {
            return new C(re, 0.0);
        }

        C plus(C o) {
            return new C(re + o.re, im + o.im);
        }

        C minus(C o) {
            return new C(re - o.re, im - o.im);
        }

        C times(C o) {
            return new C(re * o.re - im * o.im, re * o.im + im * o.re);
        }

        C times(double s) {
            return new C(re * s, im * s);
        }

        C div(C o) {
            double n = o.re * o.re + o.im * o.im;
            return new C((re * o.re + im * o.im) / n, (im * o.re - re * o.im) / n);
        }

        C exp() {
            double e = Math.exp(re);
            return new C(e * Math.cos(im), e * Math.sin(im));
        }

        C log() {
            return new C(Math.log(Math.hypot(re, im)), Math.atan2(im, re));
        }

        /** Principal square root. */
        C sqrt() {
            double m = Math.hypot(re, im);
            double a = Math.sqrt((m + re) / 2.0);
            double b = Math.sqrt((m - re) / 2.0);
            return new C(a, im < 0.0 ? -b : b);
        }
    }

    private static final C I = new C(0.0, 1.0);
    private static final C ONE = C.of(1.0);

    /** phi(u) of X = ln(S_T/F), little-trap form [Alb07]. */
    public static C cf(C u, double t, Params p) {
        Finite.check("t", t);
        double xi2 = p.xi() * p.xi();
        C iu = I.times(u);
        C b = C.of(p.kappa()).minus(iu.times(p.rho() * p.xi()));
        C w = iu.plus(u.times(u)).times(xi2);
        C d = b.times(b).plus(w).sqrt();
        C bmd = w.times(-1.0).div(b.plus(d)); // b - d without cancellation when xi is small
        C g = bmd.div(b.plus(d));
        C e = d.times(-t).exp();
        C one = ONE.minus(g.times(e));
        C z = g.times(ONE.minus(e)).div(ONE.minus(g)); // (1 - g e)/(1 - g) = 1 + z
        C log1p = new C(0.5 * Math.log1p(2.0 * z.re() + z.re() * z.re() + z.im() * z.im()),
                Math.atan2(z.im(), 1.0 + z.re()));
        C cc = bmd.times(t).minus(log1p.times(2.0)).times(p.kappa() / xi2);
        C dd = bmd.times(1.0 / xi2).times(ONE.minus(e).div(one));
        return cc.times(p.theta()).plus(dd.times(p.v0())).exp();
    }

    /** Lognormal jump factor of X, compensated [Bat96]. */
    static C jumpFactor(C u, double t, Jumps j) {
        C iu = I.times(u);
        C inner = iu.times(j.mean()).minus(u.times(u).times(j.vol() * j.vol() / 2.0)).exp()
                .minus(ONE).minus(iu.times(j.kbar()));
        return inner.times(j.intensity() * t).exp();
    }

    /** Lewis call price [Lew01] by Gauss-Legendre on [0, U_MAX] (ruling E-A13); puts by parity. */
    static double lewis(double f, double k, double r, double t, boolean call, Function<C, C> phi) {
        double lk = Math.log(f / k);
        double top = U_MAX / Math.sqrt(Math.min(t, 1.0));
        double integral = 0.0;
        for (int i = 0; i < NODES; i++) {
            double u = top / 2.0 * (1.0 + GL[0][i]);
            C z = phi.apply(new C(u, -0.5));
            C e = new C(0.0, u * lk).exp();
            integral += GL[1][i] * e.times(z).re() / (u * u + 0.25);
        }
        integral *= top / 2.0;
        double df = Math.exp(-r * t);
        double c = df * (f - Math.sqrt(f * k) / Math.PI * integral);
        return call ? c : c - df * (f - k);
    }

    public static double[] prices(double s, double t, double r, double q, boolean call, double[] k, Params p,
                                  Jumps j) {
        Finite.check("s", s);
        Finite.check("t", t);
        Finite.check("r", r);
        Finite.check("q", q);
        Finite.check("k", k);
        double f = s * Math.exp((r - q) * t);
        double[] out = new double[k.length];
        for (int i = 0; i < k.length; i++) {
            out[i] = lewis(f, k[i], r, t, call, u -> j == null ? cf(u, t, p) : cf(u, t, p).times(jumpFactor(u, t, j)));
        }
        return out;
    }

    /** Merton's series [Mer76]: Poisson weights at lambda (1 + kbar), BS terms at r_n and v_n. */
    public static double[] merton(double s, double t, double r, double q, boolean call, double[] k, double v,
                                  Jumps j) {
        Finite.check("s", s);
        Finite.check("t", t);
        Finite.check("r", r);
        Finite.check("q", q);
        Finite.check("k", k);
        Finite.check("v", v);
        double kbar = j.kbar();
        double lp = j.intensity() * (1.0 + kbar) * t;
        double phi = call ? 1.0 : -1.0;
        double[] out = new double[k.length];
        for (int i = 0; i < k.length; i++) {
            double w = Math.exp(-lp);
            double sumW = 0.0;
            double price = 0.0;
            for (int n = 0; n < 200; n++) {
                if (n > 0) {
                    w *= lp / n;
                }
                double vn = Math.sqrt(v * v + n * j.vol() * j.vol() / t);
                double rn = r - j.intensity() * kbar + (n == 0 ? 0.0 : n * Math.log1p(kbar) / t);
                double fn = s * Math.exp((rn - q) * t);
                price += w * Black.lognormal(phi, fn, k[i], t, Math.exp(-rn * t), vn);
                sumW += w;
                if (sumW >= 1.0 - 1e-16) {
                    break;
                }
            }
            out[i] = price;
        }
        return out;
    }
}
