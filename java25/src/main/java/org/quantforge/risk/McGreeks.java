package org.quantforge.risk;

import org.quantforge.core.Rng;

/** Monte Carlo price, delta and vega: pathwise, likelihood ratio and bump with common draws (mc-greeks.md). */
public final class McGreeks {
    private McGreeks() {}

    public enum Payoff { CALL, PUT, DIGITAL_CALL }

    public enum Method { PATHWISE, LIKELIHOOD_RATIO, BUMP }

    public record Result(double price, double priceSe, double delta, double deltaSe, double vega, double vegaSe) {}

    /** Running mean and standard deviation (divisor n - 1) of one per-path term. */
    private static final class Acc {
        private double sum;
        private double sumSq;

        void add(double x) {
            sum += x;
            sumSq += x * x;
        }

        double mean(long n) {
            return sum / n;
        }

        double se(long n) {
            double m = sum / n;
            double var = Math.max((sumSq - n * m * m) / (n - 1), 0.0);
            return Math.sqrt(var) / Math.sqrt(n);
        }
    }

    private static double payoff(Payoff p, double st, double k) {
        return switch (p) {
            case CALL -> Math.max(st - k, 0.0);
            case PUT -> Math.max(k - st, 0.0);
            case DIGITAL_CALL -> st > k ? 1.0 : 0.0;
        };
    }

    private static double terminal(double s, double t, double r, double q, double v, double z) {
        return s * Math.exp((r - q - v * v / 2.0) * t + v * Math.sqrt(t) * z);
    }

    /** {@code width} applies to the smoothed pathwise digital; {@code bump} to BUMP; the other is ignored. */
    public static Result run(Payoff pay, Method method, double s, double k, double t, double r, double q, double v,
                             long n, long seed, double width, double bump) {
        Rng rng = Rng.seeded(seed, 0);
        double d = Math.exp(-r * t);
        Acc price = new Acc();
        Acc delta = new Acc();
        Acc vega = new Acc();
        double sqrtT = Math.sqrt(t);
        for (long i = 0; i < n; i++) {
            double z = rng.nextNormal();
            double st = terminal(s, t, r, q, v, z);
            double f = payoff(pay, st, k);
            price.add(d * f);
            double dsdv = st * (sqrtT * z - v * t);
            switch (method) {
                case PATHWISE -> {
                    double w;
                    switch (pay) {
                        case CALL -> w = st > k ? 1.0 : 0.0;
                        case PUT -> w = st < k ? -1.0 : 0.0;
                        default -> w = Math.abs(st - k) < width ? 1.0 / (2.0 * width) : 0.0;
                    }
                    delta.add(d * w * st / s);
                    vega.add(d * w * dsdv);
                }
                case LIKELIHOOD_RATIO -> {
                    delta.add(d * f * z / (s * v * sqrtT));
                    vega.add(d * f * ((z * z - 1.0) / v - z * sqrtT));
                }
                case BUMP -> {
                    double up = payoff(pay, terminal(s * (1.0 + bump), t, r, q, v, z), k);
                    double dn = payoff(pay, terminal(s * (1.0 - bump), t, r, q, v, z), k);
                    delta.add(d * (up - dn) / (2.0 * bump * s));
                    double vu = payoff(pay, terminal(s, t, r, q, v * (1.0 + bump), z), k);
                    double vd = payoff(pay, terminal(s, t, r, q, v * (1.0 - bump), z), k);
                    vega.add(d * (vu - vd) / (2.0 * bump * v));
                }
            }
        }
        return new Result(price.mean(n), price.se(n), delta.mean(n), delta.se(n), vega.mean(n), vega.se(n));
    }
}
