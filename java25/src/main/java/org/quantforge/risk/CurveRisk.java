package org.quantforge.risk;

import java.time.LocalDate;
import java.util.List;
import java.util.function.DoubleUnaryOperator;
import java.util.function.ToDoubleFunction;
import org.quantforge.core.Conventions;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.Ois;

/** Par-quote, key-rate and Jacobian risk by bump and revalue (06-risk/par-and-key-rate.md). Money per bp. */
public final class CurveRisk {
    private CurveRisk() {}

    public enum Scheme { CENTRAL, FORWARD }

    public enum Mode { TRIANGULAR, PILLAR }

    public record Par(double value, double parDv01, double[] parBuckets) {}

    public record KeyRate(double value, double[] keyRates, double zeroDv01) {}

    public record Jacobian(LocalDate[] pillarDates, double[] zeroRates, double[][] jacobian) {}

    private static final double BP = 1e-4;

    /** 0 < bump_bp <= 100, else E_DOMAIN. */
    public static void checkBump(double bumpBp) {
        if (!(bumpBp > 0.0 && bumpBp <= 100.0)) {
            throw new QfError("E_DOMAIN", "bump_bp must be in (0, 100]", "bump_bp");
        }
    }

    /** A value at signed bump {@code s} (in bp units of +1 or -1 times the bump), and its risk per bp. */
    private interface Bumped {
        double value(int sign);
    }

    private static double risk(Bumped v, double base, double bumpBp, Scheme scheme) {
        double up = v.value(1);
        return scheme == Scheme.CENTRAL ? (up - v.value(-1)) / (2.0 * bumpBp) : (up - base) / bumpBp;
    }

    private static Curve rebuilt(Conventions.RateIndex c, LocalDate asOf, List<Ois.Quote> quotes,
                                 Curve.Interpolation interp, double[] bump) {
        return Ois.bootstrap(c, asOf, quotes, interp, CurveSolver.Method.SEQUENTIAL, bump).curve();
    }

    /** All quotes moved by {@code size} when {@code bucket} is negative, otherwise quote {@code bucket} only. */
    private static double[] bump(int n, int bucket, double size) {
        double[] b = new double[n];
        for (int i = 0; i < n; i++) {
            b[i] = bucket < 0 || bucket == i ? size : 0.0;
        }
        return b;
    }

    public static Par par(Conventions.RateIndex c, LocalDate asOf, List<Ois.Quote> quotes, Curve.Interpolation interp,
                          ToDoubleFunction<Curve> product, double bumpBp, Scheme scheme) {
        double base = product.applyAsDouble(rebuilt(c, asOf, quotes, interp, null));
        int n = quotes.size();
        double h = bumpBp * BP;
        double[] buckets = new double[n];
        for (int j = 0; j < n; j++) {
            int bucket = j;
            buckets[j] = risk(s -> product.applyAsDouble(rebuilt(c, asOf, quotes, interp, bump(n, bucket, s * h))),
                    base, bumpBp, scheme);
        }
        double parallel = risk(s -> product.applyAsDouble(rebuilt(c, asOf, quotes, interp, bump(n, -1, s * h))),
                base, bumpBp, scheme);
        return new Par(base, parallel, buckets);
    }

    /** TRIANGULAR needs key dates strictly increasing after as_of; PILLAR needs none. Else E_INPUT. */
    public static void checkKeyDates(Curve curve, Mode mode, LocalDate[] keyDates) {
        if (mode == Mode.PILLAR) {
            if (keyDates != null) {
                throw new QfError("E_INPUT", "PILLAR takes no key_dates", "key_dates");
            }
            return;
        }
        if (keyDates == null || keyDates.length == 0) {
            throw new QfError("E_INPUT", "TRIANGULAR needs at least one key date", "key_dates");
        }
        LocalDate previous = curve.asOf();
        for (LocalDate d : keyDates) {
            if (!d.isAfter(previous)) {
                throw new QfError("E_INPUT", "key_dates must increase from as_of", "key_dates");
            }
            previous = d;
        }
    }

    /** Triangular weight of key {@code i} at time {@code t}; the weights sum to 1 at every t. */
    static double weight(double[] k, int i, double t) {
        int n = k.length;
        if (t <= k[0]) {
            return i == 0 ? 1.0 : 0.0;
        }
        if (t >= k[n - 1]) {
            return i == n - 1 ? 1.0 : 0.0;
        }
        if (i > 0 && t > k[i - 1] && t <= k[i]) {
            return (t - k[i - 1]) / (k[i] - k[i - 1]);
        }
        if (i < n - 1 && t > k[i] && t < k[i + 1]) {
            return (k[i + 1] - t) / (k[i + 1] - k[i]);
        }
        return 0.0;
    }

    public static KeyRate keyRate(Curve curve, Mode mode, LocalDate[] keyDates, ToDoubleFunction<Curve> product,
                                  double bumpBp, Scheme scheme) {
        double base = product.applyAsDouble(curve);
        double h = bumpBp * BP;
        double[] buckets;
        if (mode == Mode.TRIANGULAR) {
            double[] k = new double[keyDates.length];
            for (int i = 0; i < k.length; i++) {
                k[i] = curve.time(keyDates[i]);
            }
            buckets = new double[k.length];
            for (int i = 0; i < k.length; i++) {
                int key = i;
                buckets[i] = risk(s -> product.applyAsDouble(curve.withZeroShift(t -> s * h * weight(k, key, t))),
                        base, bumpBp, scheme);
            }
        } else {
            LocalDate[] dates = curve.dates();
            double[] df = curve.discountFactors();
            buckets = new double[dates.length];
            for (int i = 0; i < dates.length; i++) {
                int pillar = i;
                buckets[i] = risk(s -> {
                    double[] bumped = df.clone();
                    bumped[pillar] *= Math.exp(-s * h * curve.time(dates[pillar]));
                    return product.applyAsDouble(Curve.of(curve.asOf(), curve.interpolation(), dates, bumped,
                            curve.jumps()));
                }, base, bumpBp, scheme);
            }
        }
        double parallel = risk(s -> product.applyAsDouble(curve.withZeroShift(constant(s * h))), base, bumpBp, scheme);
        return new KeyRate(base, buckets, parallel);
    }

    private static DoubleUnaryOperator constant(double v) {
        return t -> v;
    }

    private static double[] zeros(Curve c) {
        LocalDate[] d = c.dates();
        double[] z = new double[d.length];
        for (int i = 0; i < z.length; i++) {
            z[i] = c.zeroRate(d[i]);
        }
        return z;
    }

    public static Jacobian jacobian(Conventions.RateIndex c, LocalDate asOf, List<Ois.Quote> quotes,
                                    Curve.Interpolation interp, double bumpBp) {
        Curve base = rebuilt(c, asOf, quotes, interp, null);
        int n = quotes.size();
        double h = bumpBp * BP;
        double[] z0 = zeros(base);
        double[][] jac = new double[z0.length][n];
        for (int j = 0; j < n; j++) {
            double[] up = zeros(rebuilt(c, asOf, quotes, interp, bump(n, j, h)));
            double[] down = zeros(rebuilt(c, asOf, quotes, interp, bump(n, j, -h)));
            for (int i = 0; i < z0.length; i++) {
                jac[i][j] = (up[i] - down[i]) / (2.0 * h);
            }
        }
        return new Jacobian(base.dates(), z0, jac);
    }
}
