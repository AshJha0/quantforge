package org.quantforge.curves;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.DoubleUnaryOperator;
import org.quantforge.core.Conventions;
import org.quantforge.core.QfError;

/** Stage D rates: step fit, futures convexity, CSA discounting, OIS basis, joint bootstrap. */
public final class RatesCurves {
    private RatesCurves() {}

    private static final double TARGET = 1e-15;
    private static final double ACCEPT = 1e-13;

    public record StepFit(double baseRate, double[] stepRates, double maxRepricingError) {}

    /** meeting-steps.md: triangular, one unknown per quote in order. */
    public static StepFit fitSteps(Conventions.RateIndex c, LocalDate asOf, LocalDate[] stepDates, List<Ois.Quote> quotes,
                                   Jumps jumps) {
        int m = stepDates.length;
        if (quotes.size() != m + 1) {
            throw new QfError("E_INPUT", "need one quote more than step dates", "quotes");
        }
        if (m == 0) {
            throw new QfError("E_INPUT", "no step dates (ruling D12)", "step_dates");
        }
        StepCurve.checkSteps(asOf, stepDates);
        List<Ois.Legs> legs = new ArrayList<>();
        for (int j = 0; j <= m; j++) {
            Ois.Legs l = Ois.legs(c, asOf, quotes.get(j).tenor());
            LocalDate p = l.periods().getLast().payment();
            LocalDate lower = j == 0 ? asOf : stepDates[j - 1];
            if (!p.isAfter(lower) || (j < m && p.isAfter(stepDates[j]))) {
                throw new QfError("E_INPUT", "quote " + j + " breaks the pillar rule", "quotes");
            }
            legs.add(l);
        }
        for (Ois.Quote q : quotes) {
            if (q.crossed()) {
                throw new QfError("E_INPUT", "bid is above ask", "quotes");
            }
        }
        jumps.check(asOf);
        double[] x = new double[m + 1]; // x[0] base, x[k] step k-1.
        for (int j = 0; j <= m; j++) {
            int index = j;
            double quote = quotes.get(j).mid();
            DoubleUnaryOperator error = v -> {
                for (int k = index; k <= m; k++) {
                    x[k] = v;
                }
                return legs.get(index).parRate(curve(asOf, stepDates, x, jumps)) - quote;
            };
            double root = secant(error, quote, quote + 1e-4);
            error.applyAsDouble(root);
        }
        StepCurve fitted = curve(asOf, stepDates, x, jumps);
        double worst = 0.0;
        for (int j = 0; j <= m; j++) {
            double e = Math.abs(legs.get(j).parRate(fitted) - quotes.get(j).mid());
            worst = Double.isNaN(e) || Double.isNaN(worst) ? Double.NaN : Math.max(worst, e);
        }
        if (!(worst < ACCEPT)) {
            throw new QfError("E_NO_CONVERGENCE", "step fit stopped at repricing error " + worst);
        }
        double[] steps = new double[m];
        System.arraycopy(x, 1, steps, 0, m);
        return new StepFit(x[0], steps, worst);
    }

    private static StepCurve curve(LocalDate asOf, LocalDate[] stepDates, double[] x, Jumps jumps) {
        double[] steps = new double[stepDates.length];
        System.arraycopy(x, 1, steps, 0, steps.length);
        return StepCurve.unchecked(asOf, x[0], stepDates, steps, jumps);
    }

    private static double secant(DoubleUnaryOperator g, double a, double b) {
        double ga = g.applyAsDouble(a);
        double gb = g.applyAsDouble(b);
        double best = Math.abs(ga) < Math.abs(gb) ? a : b;
        double bestError = Math.min(Math.abs(ga), Math.abs(gb));
        int stalled = 0;
        for (int i = 0; i < 60 && bestError > TARGET && stalled < 3 && gb != ga; i++) {
            double next = b - gb * (b - a) / (gb - ga);
            a = b;
            ga = gb;
            b = next;
            gb = g.applyAsDouble(b);
            if (Math.abs(gb) < bestError) {
                bestError = Math.abs(gb);
                best = b;
                stalled = 0;
            } else {
                stalled++;
            }
        }
        return best;
    }

    public record Convexity(double futuresRate, double convexity, double forwardRate) {}

    /** futures-convexity.md, Hull-White. */
    public static Convexity convexity(double price, double t, double bigT, double sigma, double a) {
        if (!(bigT > t)) {
            throw new QfError("E_INPUT", "end_years must be after start_years", "end_years");
        }
        if (t < 0.0 || sigma < 0.0 || a < 0.0) {
            throw new QfError("E_DOMAIN", "start_years, sigma and mean_reversion must not be negative");
        }
        double d = bigT - t;
        double bd = a == 0.0 ? d : -Math.expm1(-a * d) / a;
        double l = a == 0.0 ? 2.0 * t : -Math.expm1(-2.0 * a * t) / a;
        double bt = a == 0.0 ? t : -Math.expm1(-a * t) / a;
        double z = sigma * sigma / 2.0 * (l * bd * bd + bd * bt * bt);
        double futures = (100.0 - price) / 100.0;
        double cx = -Math.expm1(-z) * (futures + 1.0 / d);
        return new Convexity(futures, cx, futures - cx);
    }

    /** csa-and-basis.md: {@code fxSpot} null means no FX; forwards are matched by exact date. */
    public static double[] csaDiscount(Curve c, double s, Double fxSpot, LocalDate[] fwdDates, double[] fwds,
                                       LocalDate[] dates) {
        Map<LocalDate, Double> forwards = new HashMap<>();
        if (fxSpot != null) {
            if (!(fxSpot > 0.0)) {
                throw new QfError("E_DOMAIN", "spot must be positive", "fx");
            }
            for (double f : fwds) {
                if (!(f > 0.0)) {
                    throw new QfError("E_DOMAIN", "forward must be positive", "fx");
                }
            }
            for (int i = 0; i < fwds.length; i++) {
                if (forwards.put(fwdDates[i], fwds[i]) != null) {
                    throw new QfError("E_INPUT", "two forwards on " + fwdDates[i], "fx");
                }
            }
            for (LocalDate d : dates) {
                if (!forwards.containsKey(d)) {
                    throw new QfError("E_INPUT", "no forward for " + d, "fx");
                }
            }
        }
        double[] out = new double[dates.length];
        for (int i = 0; i < out.length; i++) {
            double v = c.discount(dates[i]) * Math.exp(-s * c.time(dates[i]));
            out[i] = fxSpot == null ? v : v * fxSpot / forwards.get(dates[i]);
        }
        return out;
    }

    /** {@code (F_a - F_b) / A}, both legs discounted on {@code d}. */
    public static double oisSpread(Conventions.RateIndex c, String tenor, Curve d, Curve a, Curve b) {
        if (!d.asOf().equals(a.asOf()) || !d.asOf().equals(b.asOf())) {
            throw new QfError("E_INPUT", "curves have different as_of dates");
        }
        Ois.Legs legs = Ois.legs(c, d.asOf(), tenor);
        return (legs.floating(a, d) - legs.floating(b, d)) / legs.annuity(d);
    }

    public record Joint(Curve discount, Curve projection, double maxRepricingError) {}

    /** Block triangular: the OIS block first, then the term block on it. Both methods give one answer. */
    public static Joint jointBootstrap(Conventions.RateIndex c, Conventions.RateIndex ix, LocalDate asOf,
                                       List<Ois.Quote> ois, List<Projection.Quote> term, Curve.Interpolation interp,
                                       CurveSolver.Method method) {
        if (ois.isEmpty() || term.isEmpty()) {
            throw new QfError("E_INPUT", "both quote lists must be non-empty");
        }
        CurveSolver.Solved d = Ois.bootstrap(c, asOf, ois, interp, method, null);
        CurveSolver.Solved p = Projection.bootstrap(d.curve(), ix, asOf, term, interp);
        return new Joint(d.curve(), p.curve(), Math.max(d.maxRepricingError(), p.maxRepricingError()));
    }
}
