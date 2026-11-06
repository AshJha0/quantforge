package org.quantforge.core;

/** European option under geometric Brownian motion (monte-carlo.md). Sums run in path order. */
public final class MonteCarlo {
    private MonteCarlo() {}

    public enum Method { PLAIN, ANTITHETIC, CONTROL_VARIATE, SOBOL }

    public record Inputs(boolean call, double spot, double strike, double r, double q, double sigma, double t,
                         long paths, long steps, long seed, int stream, Method method) {}

    public record Result(double price, double stderr) {}

    private record Model(boolean call, double logSpot, double strike, double drift, double vol, double discount) {
        double terminal(double[] z, double sign) {
            double ln = logSpot;
            for (double v : z) {
                ln += drift + vol * (sign * v);
            }
            return Math.exp(ln);
        }

        double discounted(double st) {
            return discount * Math.max(call ? st - strike : strike - st, 0.0);
        }
    }

    public static Result price(Inputs in) {
        if (in.spot() <= 0 || in.strike() <= 0 || in.sigma() <= 0 || in.t() <= 0) {
            throw new QfError("E_DOMAIN", "spot, strike, sigma and t must be positive");
        }
        if (in.paths() < 2 || in.steps() < 1) {
            throw new QfError("E_INPUT", "bad paths or steps");
        }
        if (in.method() == Method.SOBOL && in.steps() > Sobol.MAX_DIMENSIONS) {
            throw new QfError("E_INPUT", "SOBOL needs steps <= 64", "steps");
        }
        int n = (int) in.paths();
        int m = Math.toIntExact(in.steps());
        double dt = in.t() / m;
        Model model = new Model(in.call(), Math.log(in.spot()), in.strike(),
                (in.r() - in.q() - in.sigma() * in.sigma() / 2.0) * dt, in.sigma() * Math.sqrt(dt),
                Math.exp(-in.r() * in.t()));
        double[] z = new double[m];
        double[] p = new double[n];
        switch (in.method()) {
            case PLAIN -> {
                Rng rng = Rng.seeded(in.seed(), in.stream());
                for (int i = 0; i < n; i++) {
                    fill(rng, z);
                    p[i] = model.discounted(model.terminal(z, 1.0));
                }
            }
            case ANTITHETIC -> {
                Rng rng = Rng.seeded(in.seed(), in.stream());
                for (int i = 0; i < n; i++) {
                    fill(rng, z);
                    p[i] = (model.discounted(model.terminal(z, 1.0)) + model.discounted(model.terminal(z, -1.0))) / 2.0;
                }
            }
            case CONTROL_VARIATE -> {
                Rng rng = Rng.seeded(in.seed(), in.stream());
                double[] c = new double[n];
                for (int i = 0; i < n; i++) {
                    fill(rng, z);
                    double st = model.terminal(z, 1.0);
                    p[i] = model.discounted(st);
                    c[i] = model.discount() * st;
                }
                applyControl(p, c, in.spot() * Math.exp(-in.q() * in.t()));
            }
            case SOBOL -> {
                Sobol sobol = new Sobol(m, 0);
                double[] point = new double[m];
                for (int i = 0; i < n; i++) {
                    sobol.next(point);
                    for (int j = 0; j < m; j++) {
                        z[j] = Rng.ppnd16(point[j]);
                    }
                    p[i] = model.discounted(model.terminal(z, 1.0));
                }
            }
        }
        double mean = sum(p) / n;
        double ss = 0.0;
        for (double v : p) {
            ss += (v - mean) * (v - mean);
        }
        return new Result(mean, Math.sqrt(ss / (n - 1)) / Math.sqrt(n));
    }

    private static void fill(Rng rng, double[] z) {
        for (int j = 0; j < z.length; j++) {
            z[j] = rng.nextNormal();
        }
    }

    private static double sum(double[] x) {
        double s = 0.0;
        for (double v : x) {
            s += v;
        }
        return s;
    }

    private static void applyControl(double[] p, double[] c, double known) {
        int n = p.length;
        double mp = sum(p) / n;
        double mc = sum(c) / n;
        double cov = 0.0;
        double var = 0.0;
        for (int i = 0; i < n; i++) {
            cov += (p[i] - mp) * (c[i] - mc);
            var += (c[i] - mc) * (c[i] - mc);
        }
        double beta = (cov / (n - 1)) / (var / (n - 1));
        for (int i = 0; i < n; i++) {
            p[i] -= beta * (c[i] - known);
        }
    }
}
