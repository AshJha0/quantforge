package org.quantforge.risk;

import org.quantforge.core.Finite;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.quantforge.core.Conventions;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.Ois;
import org.quantforge.pricing.Pricing;

/** Bump-and-rebuild sensitivities and the calibration report (rates-sensitivities.md, least-squares.md). */
public final class RatesRisk {
    private RatesRisk() {}

    public record Sensitivity(double dv01, double[] keyRate) {}

    public record Cashflow(double t, double amount) {}

    public record CashflowMeasures(double pv, double duration, double convexity) {}

    public record CurveReport(double[][] jacobian, double conditionNumber, double maxRepricingError) {}

    private static final double BP = 1e-4;
    private static final double REPORT_BUMP = 1e-5;

    private static Curve rebuilt(Conventions.RateIndex c, LocalDate asOf, List<Ois.Quote> quotes,
                                 Curve.Interpolation interp, double[] bump) {
        return Ois.bootstrap(c, asOf, quotes, interp, CurveSolver.Method.SEQUENTIAL, bump).curve();
    }

    /** All quotes when {@code bucket} is negative, otherwise one. */
    private static double[] bump(int n, int bucket, double size) {
        double[] b = new double[n];
        for (int i = 0; i < n; i++) {
            b[i] = bucket < 0 || bucket == i ? size : 0.0;
        }
        return b;
    }

    /** Sensitivities of several trades on one convention, from one set of bumped curves. Periods stay fixed. */
    public static List<Sensitivity> sensitivities(LocalDate asOf, List<Ois.Quote> quotes, Curve.Interpolation interp,
                                                  List<Pricing.OisTrade> trades) {
        int n = quotes.size();
        Conventions.RateIndex c = trades.getFirst().convention();
        rebuilt(c, asOf, quotes, interp, null); // Raises the quote checks before any bump.
        List<Ois.Legs> legs = new ArrayList<>();
        for (Pricing.OisTrade t : trades) {
            legs.add(Ois.legs(t.convention(), asOf, t.tenor()));
        }
        double[][] rows = new double[trades.size()][n + 1];
        for (int b = -1; b < n; b++) {
            Curve up = rebuilt(c, asOf, quotes, interp, bump(n, b, BP));
            Curve down = rebuilt(c, asOf, quotes, interp, bump(n, b, -BP));
            for (int k = 0; k < trades.size(); k++) {
                Pricing.OisTrade t = trades.get(k);
                rows[k][b + 1] = (Pricing.oisPv(t, legs.get(k), up) - Pricing.oisPv(t, legs.get(k), down)) / 2.0;
            }
        }
        List<Sensitivity> out = new ArrayList<>();
        for (double[] r : rows) {
            out.add(new Sensitivity(r[0], Arrays.copyOfRange(r, 1, n + 1)));
        }
        return out;
    }

    public static CashflowMeasures cashflows(List<Cashflow> flows, double yield) {
        Finite.check("yield", yield);
        if (flows.isEmpty()) {
            throw new QfError("E_INPUT", "no cashflows", "cashflows");
        }
        double pv = 0.0;
        double first = 0.0;
        double second = 0.0;
        for (Cashflow f : flows) {
            if (f.t() < 0.0) {
                throw new QfError("E_DOMAIN", "t is negative", "cashflows");
            }
            double v = f.amount() * Math.exp(-yield * f.t());
            pv += v;
            first += f.t() * v;
            second += f.t() * f.t() * v;
        }
        if (pv == 0.0) {
            throw new QfError("E_DOMAIN", "pv is zero");
        }
        return new CashflowMeasures(pv, first / pv, second / pv);
    }

    private static double[] zeros(Curve c) {
        LocalDate[] d = c.dates();
        double[] z = new double[d.length];
        for (int i = 0; i < z.length; i++) {
            z[i] = c.zeroRate(d[i]);
        }
        return z;
    }

    /** d z_i / d q_j by central bump, and its 2-norm condition number. */
    public static CurveReport curveReport(Conventions.RateIndex c, LocalDate asOf, List<Ois.Quote> quotes,
                                          Curve.Interpolation interp) {
        CurveSolver.Solved base = Ois.bootstrap(c, asOf, quotes, interp, CurveSolver.Method.SEQUENTIAL, null);
        int n = quotes.size();
        double[][] jac = new double[n][n];
        for (int j = 0; j < n; j++) {
            double[] up = zeros(rebuilt(c, asOf, quotes, interp, bump(n, j, REPORT_BUMP)));
            double[] down = zeros(rebuilt(c, asOf, quotes, interp, bump(n, j, -REPORT_BUMP)));
            for (int i = 0; i < n; i++) {
                jac[i][j] = (up[i] - down[i]) / (2.0 * REPORT_BUMP);
            }
        }
        double[] sigma = LinearAlgebra.singularValues(jac);
        return new CurveReport(jac, sigma[0] / sigma[n - 1], base.maxRepricingError());
    }
}
