package org.quantforge.curves;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** Q4: the four-curve system solves, structural zeros are exact, turn sensitivity, Jacobian against a rebuild. */
class JointSolverTest {
    private static final LocalDate AS_OF = LocalDate.parse("2026-11-09");

    private static JointSolver.CurveSpec ois(String name, String conv, Curve.Interpolation m, LocalDate... turns) {
        return new JointSolver.CurveSpec(name, JointSolver.CurveType.OIS, conv, m, Curve.Shape.NONE, Jumps.NONE,
                turns, null, null, null, null, null, null, null, null);
    }

    private static JointSolver.CurveSpec term(Curve.Interpolation m) {
        return new JointSolver.CurveSpec("USD-TERM-3M", JointSolver.CurveType.PROJECTION, null, m, Curve.Shape.NONE,
                Jumps.NONE, new LocalDate[0], null, "USD-TERM-3M", "USD-SOFR", null, null, null, null, null);
    }

    private static JointSolver.CurveSpec xccy() {
        return new JointSolver.CurveSpec("EUR-XCCY", JointSolver.CurveType.XCCY, null, Curve.Interpolation.LOG_LINEAR_DF,
                Curve.Shape.NONE, Jumps.NONE, new LocalDate[0], null, null, null, "USD-SOFR", "EUR-ESTR", "SOFR",
                "ESTR", LocalDate.parse("2026-11-12"));
    }

    private static JointSolver.InstrumentSpec o(String id, String curve, String tenor, double rate, boolean turn) {
        return new JointSolver.InstrumentSpec(id, curve, JointSolver.InstrumentType.OIS, turn, rate, tenor, null,
                null, null, null, null);
    }

    private static JointSolver.InstrumentSpec t(String id, JointSolver.InstrumentType type, long months, double rate) {
        return new JointSolver.InstrumentSpec(id, "USD-TERM-3M", type, false, rate, null, months, null, null, null,
                null);
    }

    private static JointSolver.InstrumentSpec x(String id, long months, double spread) {
        return new JointSolver.InstrumentSpec(id, "EUR-XCCY", JointSolver.InstrumentType.XCCY, false, spread, null,
                months, null, null, null, null);
    }

    private static List<JointSolver.InstrumentSpec> usd(boolean withTurn, double[] bump) {
        String[] tenors = {"1M", "2M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "10Y"};
        double[] rates = {0.043, 0.0428, 0.0425, 0.0412, 0.039, 0.0365, 0.0355, 0.0352, 0.0364};
        List<JointSolver.InstrumentSpec> out = new ArrayList<>();
        for (int i = 0; i < tenors.length; i++) {
            if (!withTurn && i == 1) {
                continue;
            }
            out.add(o("SOFR-" + tenors[i], "USD-SOFR", tenors[i], rates[i] + bump[out.size()], withTurn && i == 1));
        }
        int k = out.size();
        out.add(t("T-DEP", JointSolver.InstrumentType.DEPOSIT, 3, 0.0445 + bump[k]));
        out.add(t("T-FRA3", JointSolver.InstrumentType.FRA, 3, 0.0432 + bump[k + 1]));
        out.add(t("T-FRA6", JointSolver.InstrumentType.FRA, 6, 0.0418 + bump[k + 2]));
        out.add(t("T-SW2", JointSolver.InstrumentType.SWAP, 24, 0.0388 + bump[k + 3]));
        out.add(t("T-SW5", JointSolver.InstrumentType.SWAP, 60, 0.0376 + bump[k + 4]));
        out.add(t("T-SW10", JointSolver.InstrumentType.SWAP, 120, 0.0389 + bump[k + 5]));
        return out;
    }

    private static JointSolver.Result fourCurves() {
        LocalDate turn = LocalDate.parse("2026-12-31");
        List<JointSolver.CurveSpec> curves = List.of(ois("USD-SOFR", "SOFR", Curve.Interpolation.MONOTONE_CONVEX, turn),
                term(Curve.Interpolation.LOG_LINEAR_DF), ois("EUR-ESTR", "ESTR", Curve.Interpolation.MONOTONIC_LOG_CUBIC),
                xccy());
        List<JointSolver.InstrumentSpec> ins = usd(true, new double[20]);
        String[] et = {"1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y"};
        double[] er = {0.0205, 0.0201, 0.0196, 0.019, 0.0189, 0.0205, 0.0238};
        for (int i = 0; i < et.length; i++) {
            ins.add(o("ESTR-" + et[i], "EUR-ESTR", et[i], er[i], false));
        }
        ins.add(x("XC-12", 12, -0.0012));
        ins.add(x("XC-24", 24, -0.0015));
        ins.add(x("XC-60", 60, -0.0019));
        ins.add(x("XC-120", 120, -0.0021));
        return JointSolver.solve(AS_OF, curves, ins);
    }

    @Test
    void fourCurveSystemHasExactStructuralZeros() {
        JointSolver.Result r = fourCurves();
        assertTrue(r.maxRepricingError() <= 1e-13);
        assertEquals(26, r.unknowns().size());
        assertEquals("USD-SOFR:turn:2026-12-31", r.unknowns().get(8));
        // USD-SOFR rows (0..8) against every later quote (9..25): exact zeros.
        for (int i = 0; i <= 8; i++) {
            for (int j = 9; j < 26; j++) {
                assertEquals(0.0, r.jacobian()[i][j], 0.0);
            }
        }
        // EUR-ESTR rows (15..21) against USD term quotes (9..14) and xccy quotes (22..25): exact zeros.
        for (int i = 15; i <= 21; i++) {
            for (int j = 9; j <= 14; j++) {
                assertEquals(0.0, r.jacobian()[i][j], 0.0);
            }
        }
        double[] sens = r.turnSensitivity()[0];
        assertEquals(0.0, sens[0], 0.0);       // SOFR-1M ends before the turn
        assertNotEquals(0.0, sens[1]);         // SOFR-2M spans it
        for (int j = 9; j < 26; j++) {
            assertEquals(0.0, sens[j], 0.0);  // other curves
        }
    }

    @Test
    void jacobianMatchesBumpAndRebuild() {
        List<JointSolver.CurveSpec> curves = List.of(ois("USD-SOFR", "SOFR", Curve.Interpolation.LOG_LINEAR_DF),
                term(Curve.Interpolation.LOG_LINEAR_DF));
        JointSolver.Result base = JointSolver.solve(AS_OF, curves, usd(false, new double[14]));
        double h = 1e-5;
        for (int q : new int[] {0, 4, 8, 12}) {
            double[] up = new double[14];
            up[q] = h;
            double[] dn = new double[14];
            dn[q] = -h;
            double[] a = logs(JointSolver.solve(AS_OF, curves, usd(false, up)));
            double[] b = logs(JointSolver.solve(AS_OF, curves, usd(false, dn)));
            for (int i = 0; i < a.length; i++) {
                double ref = (a[i] - b[i]) / (2 * h);
                double got = base.jacobian()[i][q];
                assertEquals(ref, got, 1e-7 + 1e-5 * Math.abs(ref), "row " + i + " quote " + q);
            }
        }
    }

    private static double[] logs(JointSolver.Result r) {
        List<Double> out = new ArrayList<>();
        for (JointSolver.SolvedCurve c : r.curves()) {
            for (double d : c.discountFactors()) {
                out.add(Math.log(d));
            }
        }
        return out.stream().mapToDouble(Double::doubleValue).toArray();
    }

    @Test
    void laterCurveNameIsInputError() {
        List<JointSolver.CurveSpec> curves = List.of(term(Curve.Interpolation.LOG_LINEAR_DF),
                ois("USD-SOFR", "SOFR", Curve.Interpolation.LOG_LINEAR_DF));
        QfError e = assertThrows(QfError.class, () -> JointSolver.solve(AS_OF, curves, usd(false, new double[14])));
        assertEquals("E_INPUT", e.code());
    }

    @Test
    void fundingAtOisSimpleRatesHasZeroSpreads() {
        LocalDate[] pd = {LocalDate.parse("2027-02-08"), LocalDate.parse("2027-11-09"), LocalDate.parse("2031-11-09")};
        Curve ois = Curve.of(AS_OF, Curve.Interpolation.LOG_LINEAR_DF, pd, new double[] {0.989, 0.96, 0.84});
        double[] rates = new double[3];
        for (int i = 0; i < 3; i++) {
            rates[i] = (1.0 / ois.discount(pd[i]) - 1.0) * 360.0 / java.time.temporal.ChronoUnit.DAYS.between(AS_OF, pd[i]);
        }
        JointSolver.Funding f = JointSolver.funding(ois, pd, rates, new LocalDate[] {LocalDate.parse("2029-01-01")});
        for (double s : f.spreads()) {
            assertEquals(0.0, s, 1e-14);
        }
        assertEquals(ois.discount(LocalDate.parse("2029-01-01")), f.discountFactors()[0], 1e-14);
    }
}
