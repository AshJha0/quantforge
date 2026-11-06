package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Conventions;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.Ois;
import org.quantforge.hedging.HedgeSolver;

/** Properties the specs state that golden values alone do not prove. */
class StageBSpecTest {
    private static final LocalDate AS_OF = LocalDate.of(2026, 11, 6);

    private static List<Ois.Quote> quotes() {
        List<Ois.Quote> q = new ArrayList<>();
        String[] tenors = {"1W", "3M", "1Y", "2Y", "5Y", "10Y", "30Y"};
        double[] rates = {0.0372, 0.0368, 0.035, 0.0335, 0.0335, 0.036, -0.001};
        for (int i = 0; i < tenors.length; i++) {
            q.add(new Ois.Quote(tenors[i], rates[i], null, null));
        }
        return q;
    }

    @Test
    void bothMethodsGiveTheSameCurveAndRepriceBelowTheLimit() {
        for (Conventions.RateIndex c : List.of(Conventions.SONIA, Conventions.SOFR)) {
            for (Curve.Interpolation interp : Curve.Interpolation.values()) {
                CurveSolver.Solved a = Ois.bootstrap(c, AS_OF, quotes(), interp, CurveSolver.Method.SEQUENTIAL, null);
                CurveSolver.Solved b = Ois.bootstrap(c, AS_OF, quotes(), interp, CurveSolver.Method.GLOBAL, null);
                assertTrue(a.maxRepricingError() < 1e-13);
                assertTrue(b.maxRepricingError() < 1e-13);
                double[] da = a.curve().discountFactors();
                double[] db = b.curve().discountFactors();
                for (int i = 0; i < da.length; i++) {
                    assertEquals(da[i], db[i], 1e-11);
                }
            }
        }
    }

    @Test
    void telescopedFloatingLegIsWrongUnderAPaymentLag() {
        Curve curve = Ois.bootstrap(Conventions.SOFR, AS_OF, quotes(), Curve.Interpolation.LOG_LINEAR_DF,
                CurveSolver.Method.SEQUENTIAL, null).curve();
        Ois.Legs legs = Ois.legs(Conventions.SOFR, AS_OF, "10Y");
        double telescoped = curve.discount(legs.periods().getFirst().start())
                - curve.discount(legs.periods().getLast().end());
        assertTrue(Math.abs(telescoped - legs.floating(curve)) > 1e-5);
    }

    @Test
    void hedgeMeetsItsFirstOrderConditionsAndCanLeaveOutACostlyHedge() {
        double[][] a = {{1.0, 0.2, 0.0}, {0.3, 1.0, 0.4}, {0.0, 0.3, 1.0}, {0.1, 0.1, 0.2}};
        double[] b = {10.0, -4.0, 6.0, 1.0};
        double[] w = {1.0, 2.0, 1.0, 0.5};
        double[] c = {0.5, 40.0, 1.0};
        double lambda = 1.0;
        HedgeSolver.Solution s = HedgeSolver.solve(a, b, w, c, lambda);
        assertEquals(0.0, s.x()[1]);
        for (int i = 0; i < 3; i++) {
            double g = 0.0;
            for (int r = 0; r < 4; r++) {
                g += 2.0 * a[r][i] * w[r] * s.residual()[r];
            }
            if (s.x()[i] != 0.0) {
                assertEquals(0.0, g + lambda * c[i] * Math.signum(s.x()[i]), 1e-9);
            } else {
                assertTrue(Math.abs(g) <= lambda * c[i] + 1e-9);
            }
        }
    }
}
