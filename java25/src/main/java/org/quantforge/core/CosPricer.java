package org.quantforge.core;

/** COS Fourier pricing of a European option (cos.md). */
public final class CosPricer {
    private CosPricer() {}

    public sealed interface Model permits BlackScholes, Heston {}

    public record BlackScholes(double sigma) implements Model {}

    public record Heston(double v0, double kappa, double theta, double sigma, double rho) implements Model {}

    public record Inputs(boolean call, double spot, double strike, double r, double q, double t, Model model,
                         long terms, double truncation) {}

    public record Result(double price, double a, double b) {}

    private record C(double re, double im) {
        C add(C o) {
            return new C(re + o.re, im + o.im);
        }

        C sub(C o) {
            return new C(re - o.re, im - o.im);
        }

        C mul(C o) {
            return new C(re * o.re - im * o.im, re * o.im + im * o.re);
        }

        C scale(double s) {
            return new C(re * s, im * s);
        }

        C div(C o) {
            double d = o.re * o.re + o.im * o.im;
            return new C((re * o.re + im * o.im) / d, (im * o.re - re * o.im) / d);
        }

        C exp() {
            double e = Math.exp(re);
            return new C(e * Math.cos(im), e * Math.sin(im));
        }

        C log() {
            return new C(Math.log(Math.hypot(re, im)), Math.atan2(im, re));
        }

        C sqrt() {
            double m = Math.hypot(re, im);
            if (m == 0.0) {
                return new C(0.0, 0.0);
            }
            double a = Math.sqrt((m + Math.abs(re)) / 2.0);
            double b = Math.abs(im) / (2.0 * a);
            return re >= 0.0 ? new C(a, Math.copySign(b, im)) : new C(b, Math.copySign(a, im));
        }
    }

    private static final C ONE = new C(1.0, 0.0);

    private static C phiBlackScholes(BlackScholes m, double u, double r, double q, double t) {
        double s2 = m.sigma() * m.sigma();
        return new C(-s2 * u * u * t / 2.0, u * (r - q - s2 / 2.0) * t).exp();
    }

    private static C phiHeston(Heston m, double u, double r, double q, double t) {
        double s = m.sigma();
        C beta = new C(m.kappa(), -m.rho() * s * u);
        C d = beta.mul(beta).add(new C(u * u, u).scale(s * s)).sqrt();
        C bMinus = beta.sub(d);
        C g = bMinus.div(beta.add(d));
        C edt = d.scale(-t).exp();
        C oneMinusGE = ONE.sub(g.mul(edt));
        C logTerm = oneMinusGE.div(ONE.sub(g)).log();
        C first = bMinus.scale(t).sub(logTerm.scale(2.0)).scale(m.kappa() * m.theta() / (s * s));
        C second = bMinus.mul(ONE.sub(edt)).div(oneMinusGE).scale(m.v0() / (s * s));
        return new C(0.0, u * (r - q) * t).add(first).add(second).exp();
    }

    private static void positive(double v, String name) {
        if (v <= 0.0) {
            throw new QfError("E_DOMAIN", name + " must be positive", name);
        }
    }

    public static Result price(Inputs in) {
        positive(in.spot(), "spot");
        positive(in.strike(), "strike");
        positive(in.t(), "t");
        positive(in.truncation(), "truncation");
        double t = in.t();
        double w;
        switch (in.model()) {
            case BlackScholes m -> {
                positive(m.sigma(), "sigma");
                w = m.sigma() * m.sigma() * t;
            }
            case Heston m -> {
                positive(m.sigma(), "sigma");
                positive(m.v0(), "v0");
                positive(m.kappa(), "kappa");
                positive(m.theta(), "theta");
                if (Math.abs(m.rho()) >= 1.0) {
                    throw new QfError("E_DOMAIN", "|rho| must be below 1", "rho");
                }
                double kt = m.kappa() * t;
                w = (m.theta() + (m.v0() - m.theta()) * (1.0 - Math.exp(-kt)) / kt) * t;
            }
        }
        if (in.terms() < 2) {
            throw new QfError("E_INPUT", "need at least 2 terms", "terms");
        }
        double x = Math.log(in.spot() / in.strike());
        double c1 = x + (in.r() - in.q()) * t - w / 2.0;
        double a = c1 - in.truncation() * Math.sqrt(w);
        double b = c1 + in.truncation() * Math.sqrt(w);
        if (a >= 0.0 || b <= 0.0) {
            throw new QfError("E_INPUT", "the range does not hold the strike");
        }
        double ea = Math.exp(a);
        double sum = 0.0;
        for (long k = 0; k < in.terms(); k++) {
            double u = k * Math.PI / (b - a);
            double chi = (Math.cos(-u * a) + u * Math.sin(-u * a) - ea) / (1.0 + u * u);
            double psi = k == 0 ? -a : Math.sin(-u * a) / u;
            double v = 2.0 / (b - a) * in.strike() * (psi - chi);
            C phi = k == 0 ? ONE : switch (in.model()) {
                case BlackScholes m -> phiBlackScholes(m, u, in.r(), in.q(), t);
                case Heston m -> phiHeston(m, u, in.r(), in.q(), t);
            };
            double angle = u * (x - a);
            double re = phi.re() * Math.cos(angle) - phi.im() * Math.sin(angle);
            sum += (k == 0 ? 0.5 : 1.0) * re * v;
        }
        double put = Math.exp(-in.r() * t) * sum;
        double price = in.call() ? put + in.spot() * Math.exp(-in.q() * t) - in.strike() * Math.exp(-in.r() * t) : put;
        return new Result(price, a, b);
    }
}
