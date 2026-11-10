package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Random;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Conventions;
import org.quantforge.core.Json;
import org.quantforge.curves.Curve;
import org.quantforge.curves.CurveSolver;
import org.quantforge.curves.Jumps;
import org.quantforge.curves.Ois;
import org.quantforge.curves.RatesCurves;
import org.quantforge.curves.StepCurve;

/** Stage D wave 1: each operation's rules, edge and error paths, and a fuzz pass. */
class RatesCurvesSpecTest {
    private static final LocalDate AS_OF = LocalDate.of(2026, 11, 6);
    private static final String CURVE = "{\"as_of\":\"2026-11-06\",\"interpolation\":\"LOG_LINEAR_DF\",\"pillars\":"
            + "[{\"date\":\"2027-11-06\",\"discount_factor\":0.96},{\"date\":\"2028-11-06\",\"discount_factor\":0.92}]";

    private static Map<?, ?> run(String op, String inputs) {
        String text = "{\"schema_version\":\"1.0\",\"case_id\":\"t\",\"operation\":\"" + op + "\",\"inputs\":" + inputs + "}";
        return (Map<?, ?>) Json.parse(Main.handle(text).json()).value();
    }

    private static Map<?, ?> ok(String op, String inputs) {
        Map<?, ?> r = run(op, inputs);
        assertEquals("ok", r.get("status"), () -> String.valueOf(r.get("error")));
        return (Map<?, ?>) r.get("outputs");
    }

    private static void error(String code, String op, String inputs) {
        Map<?, ?> r = run(op, inputs);
        assertEquals("error", r.get("status"), op + " " + inputs);
        assertEquals(code, ((Map<?, ?>) r.get("error")).get("code"), op + " " + inputs);
    }

    private static double num(Object o) {
        return o instanceof Json.Number n ? n.value() : ((Number) o).doubleValue();
    }

    private static double at(Map<?, ?> out, String key, int i) {
        return num(((List<?>) out.get(key)).get(i));
    }

    // Jumps on the curve object.

    @Test
    void jumpAppliesStrictlyAfterItsDate() {
        String jumped = CURVE + ",\"jumps\":[{\"date\":\"2026-12-31\",\"factor\":0.999}]}";
        Map<?, ?> a = ok("rates.curve.discount", "{\"curve\":" + CURVE + "},\"dates\":[\"2026-12-31\",\"2027-01-01\",\"2027-11-06\"]}");
        Map<?, ?> b = ok("rates.curve.discount", "{\"curve\":" + jumped + ",\"dates\":[\"2026-12-31\",\"2027-01-01\",\"2027-11-06\"]}");
        // Pillars hold the full D; interpolation is on S = D / J, and J moves only after the jump's date.
        double lnS = Math.log(0.96 / 0.999);
        assertEquals(Math.exp(55 / 365.0 * lnS), at(b, "discount_factors", 0), 1e-15);
        assertEquals(Math.exp(56 / 365.0 * lnS) * 0.999, at(b, "discount_factors", 1), 1e-15);
        assertEquals(0.96, at(b, "discount_factors", 2), 1e-15);
        assertEquals(Math.exp(55 / 365.0 * Math.log(0.96)), at(a, "discount_factors", 0), 1e-15);
    }

    @Test
    void badJumpsAreRejected() {
        String base = "{\"curve\":" + CURVE + ",\"jumps\":%s},\"dates\":[\"2027-01-01\"]}";
        error("E_INPUT", "rates.curve.discount", base.formatted("[{\"date\":\"2026-11-06\",\"factor\":0.99}]"));
        error("E_INPUT", "rates.curve.discount", base.formatted(
                "[{\"date\":\"2027-12-31\",\"factor\":0.99},{\"date\":\"2026-12-31\",\"factor\":0.99}]"));
        error("E_DOMAIN", "rates.curve.discount", base.formatted("[{\"date\":\"2026-12-31\",\"factor\":-1}]"));
        error("E_SCHEMA", "rates.curve.discount", base.formatted("null"));
        ok("rates.curve.discount", base.formatted("[]"));
    }

    @Test
    void estrAndJumpedBootstrapsAgreeAcrossMethods() {
        List<Ois.Quote> q = List.of(new Ois.Quote("1M", 0.022, null, null), new Ois.Quote("1Y", 0.0205, null, null),
                new Ois.Quote("5Y", 0.019, null, null), new Ois.Quote("30Y", 0.0225, null, null));
        Jumps j = new Jumps(new LocalDate[] {LocalDate.of(2026, 12, 31)}, new double[] {Math.exp(-0.002 * 1 / 365.0)});
        for (Curve.Interpolation interp : new Curve.Interpolation[] {Curve.Interpolation.LOG_LINEAR_DF, Curve.Interpolation.LINEAR_ZERO}) {
            CurveSolver.Solved a = Ois.bootstrap(Conventions.ESTR, AS_OF, q, interp, CurveSolver.Method.SEQUENTIAL, null, j);
            CurveSolver.Solved b = Ois.bootstrap(Conventions.ESTR, AS_OF, q, interp, CurveSolver.Method.GLOBAL, null, j);
            assertTrue(a.maxRepricingError() < 1e-13 && b.maxRepricingError() < 1e-13);
            for (int i = 0; i < q.size(); i++) {
                assertEquals(a.curve().discountFactors()[i], b.curve().discountFactors()[i], 1e-11);
                assertEquals(q.get(i).mid(), Ois.legs(Conventions.ESTR, AS_OF, q.get(i).tenor()).parRate(a.curve()), 1e-13);
            }
        }
    }

    // Dated compounding.

    private static final String FIX;

    static {
        StringBuilder b = new StringBuilder("[");
        LocalDate d = LocalDate.of(2026, 10, 1);
        for (int i = 0; d.isBefore(LocalDate.of(2027, 3, 1)); d = d.plusDays(1), i++) {
            b.append(i == 0 ? "" : ",").append("{\"date\":\"").append(d).append("\",\"rate\":").append(0.04 + i * 1e-5).append('}');
        }
        FIX = b.append(']').toString();
    }

    private static String dated(String conv, String start, String end, String method, long k) {
        return "{\"convention\":\"" + conv + "\",\"start\":\"" + start + "\",\"end\":\"" + end + "\",\"method\":\"" + method
                + "\",\"shift_days\":" + k + ",\"fixings\":" + FIX + "}";
    }

    @Test
    void datedCompoundingByHandOverAWeekend() {
        // Fri 2026-11-13 to Tue 2026-11-17 on USGS: steps Fri (3 days), Mon (1 day).
        double rFri = 0.04 + 43 * 1e-5;
        double rMon = 0.04 + 46 * 1e-5;
        double growth = (1 + rFri * 3 / 360.0) * (1 + rMon / 360.0);
        Map<?, ?> o = ok("rates.ois.compound_dated", dated("SOFR", "2026-11-13", "2026-11-17", "NONE", 0));
        assertEquals((growth - 1) * 360 / 4, num(o.get("compounded_rate")), 1e-15);
        assertEquals(4 / 360.0, num(o.get("accrual")), 1e-16);
        // Lockout 1: the last step uses the cut-off date's own fixing (Mon), so nothing changes here.
        Map<?, ?> lock = ok("rates.ois.compound_dated", dated("SOFR", "2026-11-13", "2026-11-17", "LOCKOUT", 1));
        assertEquals(num(o.get("compounded_rate")), num(lock.get("compounded_rate")), 1e-15);
        // Observation shift by 1: observe Thu (1 day to Fri) and Fri (3 days to Mon).
        double rThu = 0.04 + 42 * 1e-5;
        double g2 = (1 + rThu * 1 / 360.0) * (1 + rFri * 3 / 360.0);
        Map<?, ?> obs = ok("rates.ois.compound_dated", dated("SOFR", "2026-11-13", "2026-11-17", "OBSERVATION_SHIFT", 1));
        assertEquals((g2 - 1) * 360 / 4, num(obs.get("compounded_rate")), 1e-15);
        // Lookback by 1: Thu's rate for 3 days, Fri's for 1.
        double g3 = (1 + rThu * 3 / 360.0) * (1 + rFri / 360.0);
        Map<?, ?> lb = ok("rates.ois.compound_dated", dated("SOFR", "2026-11-13", "2026-11-17", "LOOKBACK", 1));
        assertEquals((g3 - 1) * 360 / 4, num(lb.get("compounded_rate")), 1e-15);
    }

    @Test
    void datedCompoundingChecks() {
        String op = "rates.ois.compound_dated";
        error("E_INPUT", op, dated("USD-TERM-3M", "2026-11-10", "2026-12-10", "NONE", 0));
        error("E_SCHEMA", op, dated("NOPE", "2026-11-10", "2026-12-10", "NONE", 0));
        error("E_DATE_ORDER", op, dated("SOFR", "2026-11-10", "2026-11-10", "NONE", 0));
        error("E_INPUT", op, dated("SOFR", "2026-11-10", "2026-12-10", "NONE", 1));
        error("E_INPUT", op, dated("SOFR", "2026-11-10", "2026-12-10", "LOOKBACK", -1));
        error("E_INPUT", op, dated("SOFR", "2026-11-10", "2026-11-12", "LOCKOUT", 2));
        error("E_INPUT", op, dated("SOFR", "2026-11-14", "2026-12-10", "NONE", 0));
        error("E_INPUT", op, dated("SOFR", "2027-02-10", "2027-03-10", "NONE", 0));
        error("E_INPUT", op, dated("SOFR", "2026-11-10", "2026-12-10", "LOOKBACK", 60));
        error("E_DATE_RANGE", op, dated("SOFR", "2026-11-10", "2026-12-10", "LOOKBACK", 9_000_000_000L));
        error("E_INPUT", op, "{\"convention\":\"SOFR\",\"start\":\"2026-11-10\",\"end\":\"2026-11-11\",\"method\":\"NONE\","
                + "\"shift_days\":0,\"fixings\":[{\"date\":\"2026-11-10\",\"rate\":0.04},{\"date\":\"2026-11-10\",\"rate\":0.05}]}");
        ok(op, dated("ESTR", "2026-11-10", "2026-12-10", "OBSERVATION_SHIFT", 2));
        ok(op, dated("SONIA", "2026-11-10", "2026-12-10", "LOCKOUT", 5));
    }

    @Test
    void fallbackAddsTheIsdaSpread() {
        String fix = FIX;
        Map<?, ?> f = ok("rates.fallback.rate", "{\"ibor\":\"GBP-LIBOR-6M\",\"start\":\"2026-11-10\",\"end\":\"2027-02-10\",\"fixings\":" + fix + "}");
        Map<?, ?> c = ok("rates.ois.compound_dated", dated("SONIA", "2026-11-10", "2027-02-10", "OBSERVATION_SHIFT", 2));
        assertEquals(0.0027660, num(f.get("spread_adjustment")), 0.0);
        assertEquals(num(c.get("compounded_rate")), num(f.get("compounded_rate")), 0.0);
        assertEquals(num(c.get("compounded_rate")) + 0.0027660, num(f.get("fallback_rate")), 1e-17);
        error("E_SCHEMA", "rates.fallback.rate", "{\"ibor\":\"EUR-LIBOR-3M\",\"start\":\"2026-11-10\",\"end\":\"2027-02-10\",\"fixings\":[]}");
        error("E_INPUT", "rates.fallback.rate", "{\"ibor\":\"USD-LIBOR-1M\",\"start\":\"2026-11-10\",\"end\":\"2027-02-10\",\"fixings\":[]}");
    }

    // Step curve and fit.

    @Test
    void stepCurveIntegratesExactly() {
        String in = "{\"as_of\":\"2026-11-06\",\"base_rate\":0.04,\"steps\":[{\"date\":\"2026-11-16\",\"rate\":0.03}],"
                + "\"jumps\":[{\"date\":\"2026-11-20\",\"factor\":0.9}],\"dates\":[\"2026-11-06\",\"2026-11-16\",\"2026-11-20\",\"2026-11-21\"]}";
        Map<?, ?> o = ok("rates.ois.step_curve", in);
        assertEquals(1.0, at(o, "discount_factors", 0), 0.0);
        assertEquals(Math.exp(-0.4 / 365), at(o, "discount_factors", 1), 1e-16);
        assertEquals(Math.exp(-(0.4 + 0.12) / 365), at(o, "discount_factors", 2), 1e-16);
        assertEquals(Math.exp(-(0.4 + 0.15) / 365) * 0.9, at(o, "discount_factors", 3), 4e-16);
        assertEquals(0.04, at(o, "overnight_forwards", 0), 0.0);
        assertEquals(0.03, at(o, "overnight_forwards", 1), 0.0);
    }

    @Test
    void stepCurveChecks() {
        String op = "rates.ois.step_curve";
        String f = "{\"as_of\":\"2026-11-06\",\"base_rate\":0.04,\"steps\":%s,\"jumps\":%s,\"dates\":%s}";
        error("E_INPUT", op, f.formatted("[{\"date\":\"2026-11-06\",\"rate\":0.03}]", "[]", "[\"2027-01-01\"]"));
        error("E_INPUT", op, f.formatted("[{\"date\":\"2027-01-06\",\"rate\":0.03},{\"date\":\"2026-12-06\",\"rate\":0.03}]", "[]", "[\"2027-01-01\"]"));
        error("E_OUT_OF_RANGE", op, f.formatted("[]", "[]", "[\"2026-11-05\"]"));
        error("E_INPUT", op, f.formatted("[]", "[]", "[]"));
        error("E_DOMAIN", op, f.formatted("[]", "[{\"date\":\"2026-12-31\",\"factor\":0}]", "[\"2027-01-01\"]"));
        error("E_SCHEMA", op, f.formatted("[]", "null", "[\"2027-01-01\"]"));
        error("E_SCHEMA", op, "{\"as_of\":\"2026-11-06\",\"base_rate\":0.04,\"steps\":[],\"dates\":[\"2027-01-01\"]}");
        ok(op, f.formatted("[]", "[]", "[\"2027-01-01\"]"));
    }

    @Test
    void stepFitRecoversItsTruth() {
        LocalDate[] steps = {LocalDate.of(2026, 12, 10), LocalDate.of(2027, 1, 28), LocalDate.of(2027, 3, 18)};
        double[] truth = {0.04, 0.037, 0.037};
        Jumps j = new Jumps(new LocalDate[] {LocalDate.of(2026, 12, 31)}, new double[] {0.9999});
        StepCurve c = StepCurve.of(AS_OF, 0.0425, steps, truth, j);
        String[] tenors = {"3W", "2M", "3M", "6M"};
        List<Ois.Quote> q = new java.util.ArrayList<>();
        for (String t : tenors) {
            q.add(new Ois.Quote(t, Ois.legs(Conventions.SOFR, AS_OF, t).parRate(c), null, null));
        }
        RatesCurves.StepFit fit = RatesCurves.fitSteps(Conventions.SOFR, AS_OF, steps, q, j);
        assertEquals(0.0425, fit.baseRate(), 1e-12);
        for (int i = 0; i < truth.length; i++) {
            assertEquals(truth[i], fit.stepRates()[i], 1e-12);
        }
        assertTrue(fit.maxRepricingError() < 1e-13);
    }

    @Test
    void stepFitChecks() {
        String op = "rates.ois.fit_steps";
        String f = "{\"convention\":\"%s\",\"as_of\":\"2026-11-06\",\"step_dates\":%s,\"quotes\":%s,\"jumps\":[]}";
        String two = "[{\"tenor\":\"3W\",\"rate\":0.04},{\"tenor\":\"2M\",\"rate\":0.04}]";
        error("E_INPUT", op, f.formatted("SOFR", "[\"2026-12-10\",\"2027-01-28\"]", two));
        error("E_INPUT", op, f.formatted("SOFR", "[]", "[{\"tenor\":\"3W\",\"rate\":0.04}]"));
        error("E_INPUT", op, f.formatted("SOFR", "[\"2027-01-28\"]", two));
        error("E_INPUT", op, f.formatted("SOFR", "[\"2026-11-06\"]", two));
        error("E_INPUT", op, f.formatted("USD-TERM-3M", "[\"2026-12-10\"]", two));
        error("E_SCHEMA", op, "{\"convention\":\"SOFR\",\"as_of\":\"2026-11-06\",\"step_dates\":[\"2026-12-10\"],\"quotes\":" + two + "}");
        ok(op, f.formatted("SOFR", "[\"2026-12-10\"]", two));
    }

    // Futures convexity.

    @Test
    void convexityAtZeroMeanReversionIsTheLimit() {
        RatesCurves.Convexity zero = RatesCurves.convexity(96, 1, 1.25, 0.01, 0);
        RatesCurves.Convexity tiny = RatesCurves.convexity(96, 1, 1.25, 0.01, 1e-9);
        assertEquals(zero.convexity(), tiny.convexity(), 1e-12);
        double z = 0.0001 / 2 * (2 * 0.0625 + 0.25 * 1);
        assertEquals(-Math.expm1(-z) * (0.04 + 4), zero.convexity(), 1e-17);
        assertEquals(0.04 - zero.convexity(), zero.forwardRate(), 0.0);
        assertEquals(0.0, RatesCurves.convexity(96, 0, 0.25, 0.0, 0.1).convexity(), 0.0);
        String f = "{\"price\":96,\"start_years\":%s,\"end_years\":%s,\"sigma\":%s,\"mean_reversion\":%s}";
        error("E_INPUT", "rates.futures.convexity", f.formatted(1, 1, 0.01, 0.03));
        error("E_INPUT", "rates.futures.convexity", f.formatted(-1, -2, 0.01, 0.03));
        error("E_DOMAIN", "rates.futures.convexity", f.formatted(-0.1, 1, 0.01, 0.03));
        error("E_DOMAIN", "rates.futures.convexity", f.formatted(0, 1, -0.01, 0.03));
        error("E_DOMAIN", "rates.futures.convexity", f.formatted(0, 1, 0.01, -0.03));
    }

    // CSA, basis, joint build.

    @Test
    void csaDiscount() {
        String op = "rates.csa.discount";
        Map<?, ?> o = ok(op, "{\"curve\":" + CURVE + "},\"collateral_spread\":0.01,\"fx\":null,\"dates\":[\"2027-11-06\"]}");
        assertEquals(0.96 * Math.exp(-0.01), at(o, "discount_factors", 0), 1e-16);
        Map<?, ?> x = ok(op, "{\"curve\":" + CURVE + "},\"collateral_spread\":0,\"fx\":{\"spot\":1.1,\"forwards\":"
                + "[{\"date\":\"2027-11-06\",\"forward\":1.2}]},\"dates\":[\"2027-11-06\"]}");
        assertEquals(0.96 * 1.1 / 1.2, at(x, "discount_factors", 0), 1e-16);
        error("E_SCHEMA", op, "{\"curve\":" + CURVE + "},\"collateral_spread\":0,\"dates\":[\"2027-11-06\"]}");
        error("E_INPUT", op, "{\"curve\":" + CURVE + "},\"collateral_spread\":0,\"fx\":{\"spot\":1.1,\"forwards\":[]},\"dates\":[\"2027-11-06\"]}");
        error("E_DOMAIN", op, "{\"curve\":" + CURVE + "},\"collateral_spread\":0,\"fx\":{\"spot\":1.1,\"forwards\":"
                + "[{\"date\":\"2027-11-06\",\"forward\":0}]},\"dates\":[\"2027-11-06\"]}");
        error("E_OUT_OF_RANGE", op, "{\"curve\":" + CURVE + "},\"collateral_spread\":0,\"fx\":null,\"dates\":[\"2026-11-05\"]}");
    }

    @Test
    void oisSpreadIsZeroOnOneCurveAndChecksAsOf() {
        String c = CURVE + "}";
        Map<?, ?> o = ok("rates.basis.ois_spread", "{\"convention\":\"SOFR\",\"tenor\":\"2Y\",\"discount\":" + c
                + ",\"projection_a\":" + c + ",\"projection_b\":" + c + "}");
        assertEquals(0.0, num(o.get("spread")), 0.0);
        String other = c.replace("\"as_of\":\"2026-11-06\"", "\"as_of\":\"2026-11-05\"");
        error("E_INPUT", "rates.basis.ois_spread", "{\"convention\":\"SOFR\",\"tenor\":\"2Y\",\"discount\":" + c
                + ",\"projection_a\":" + other + ",\"projection_b\":" + c + "}");
    }

    @Test
    void jointBootstrapMethodsAgree() {
        String f = "{\"convention\":\"SOFR\",\"index\":\"USD-TERM-3M\",\"as_of\":\"2026-11-06\",\"ois_quotes\":%s,"
                + "\"term_quotes\":%s,\"interpolation\":\"LINEAR_ZERO\",\"method\":\"%s\"}";
        String ois = "[{\"tenor\":\"3M\",\"rate\":0.038},{\"tenor\":\"2Y\",\"rate\":0.035},{\"tenor\":\"10Y\",\"rate\":0.037}]";
        String term = "[{\"type\":\"DEPOSIT\",\"months\":3,\"rate\":0.039},{\"type\":\"SWAP\",\"months\":24,\"rate\":0.037},"
                + "{\"type\":\"SWAP\",\"months\":120,\"rate\":0.039}]";
        Map<?, ?> a = ok("rates.curve.joint_bootstrap", f.formatted(ois, term, "SEQUENTIAL"));
        Map<?, ?> b = ok("rates.curve.joint_bootstrap", f.formatted(ois, term, "GLOBAL"));
        for (String key : List.of("discount_pillars", "projection_pillars")) {
            List<?> pa = (List<?>) a.get(key);
            List<?> pb = (List<?>) b.get(key);
            assertEquals(3, pa.size());
            for (int i = 0; i < 3; i++) {
                assertEquals(num(((Map<?, ?>) pa.get(i)).get("discount_factor")),
                        num(((Map<?, ?>) pb.get(i)).get("discount_factor")), 1e-11);
            }
        }
        error("E_INPUT", "rates.curve.joint_bootstrap", f.formatted(ois, "[]", "GLOBAL"));
        error("E_INPUT", "rates.curve.joint_bootstrap", f.formatted("[]", term, "SEQUENTIAL"));
    }

    // Curve fits.

    @Test
    void smoothFit() {
        String op = "calib.curve.smooth";
        // Exact fit at lambda 0 with one maturity per knot.
        Map<?, ?> o = ok(op, "{\"knots\":[1,2],\"maturities\":[1,2],\"zero_rates\":[0.03,0.035],\"lambda\":0}");
        assertEquals(0.03, at(o, "forwards", 0), 1e-15);
        assertEquals(0.04, at(o, "forwards", 1), 1e-15);
        assertEquals(0.0, num(o.get("objective")), 1e-30);
        // A huge penalty flattens the forwards.
        Map<?, ?> flat = ok(op, "{\"knots\":[1,2],\"maturities\":[1,2],\"zero_rates\":[0.03,0.035],\"lambda\":1e12}");
        assertEquals(at(flat, "forwards", 0), at(flat, "forwards", 1), 1e-9);
        // Zero weight drops a point.
        Map<?, ?> w = ok(op, "{\"knots\":[2],\"maturities\":[1,2],\"zero_rates\":[0.03,0.05],\"lambda\":0,\"weights\":[1,0]}");
        assertEquals(0.03, at(w, "forwards", 0), 1e-15);
        error("E_SCHEMA", op, "{\"knots\":[2],\"maturities\":[1],\"zero_rates\":[0.03],\"lambda\":0,\"weights\":null}");
        error("E_INPUT", op, "{\"knots\":[2],\"maturities\":[1],\"zero_rates\":[0.03],\"lambda\":0,\"weights\":[1,1]}");
        error("E_INPUT", op, "{\"knots\":[2],\"maturities\":[],\"zero_rates\":[],\"lambda\":0}");
        error("E_INPUT", op, "{\"knots\":[0,2],\"maturities\":[1],\"zero_rates\":[0.03],\"lambda\":0}");
        error("E_DOMAIN", op, "{\"knots\":[2],\"maturities\":[1],\"zero_rates\":[0.03],\"lambda\":0,\"weights\":[-1]}");
        error("E_DOMAIN", op, "{\"knots\":[2],\"maturities\":[0],\"zero_rates\":[0.03],\"lambda\":0}");
        error("E_INPUT", op, "{\"knots\":[2],\"maturities\":[3],\"zero_rates\":[0.03],\"lambda\":0}");
        error("E_SINGULAR", op, "{\"knots\":[1,2],\"maturities\":[1],\"zero_rates\":[0.03],\"lambda\":0}");
    }

    @Test
    void robustFit() {
        double tau = 2.0;
        double[] m = {0.5, 1, 2, 3, 5, 7, 10, 20};
        double[] b = {0.04, -0.01, 0.005};
        double[] y = new double[m.length];
        for (int i = 0; i < m.length; i++) {
            double u = m[i] / tau;
            double e = (1 - Math.exp(-u)) / u;
            y[i] = b[0] + b[1] * e + b[2] * (e - Math.exp(-u));
        }
        y[3] += 0.003;
        var r = org.quantforge.calibration.CurveFits.robust(m, y, tau, 0.0005);
        // One outlier among clean points: only point 3 is flagged.
        assertEquals(1, r.outliers().length);
        assertEquals(3, r.outliers()[0]);
        // The first-order condition holds.
        double[] g = new double[3];
        for (int j = 0; j < m.length; j++) {
            double u = m[j] / tau;
            double e = (1 - Math.exp(-u)) / u;
            double[] x = {1, e, e - Math.exp(-u)};
            double psi = Math.max(-0.0005, Math.min(0.0005, r.residuals()[j]));
            for (int k = 0; k < 3; k++) {
                g[k] += psi * x[k];
            }
        }
        for (double v : g) {
            assertEquals(0.0, v, 1e-15);
        }
        String op = "calib.curve.robust";
        error("E_INPUT", op, "{\"maturities\":[1,2],\"zero_rates\":[0.03,0.03],\"tau\":2,\"delta\":0.001}");
        error("E_INPUT", op, "{\"maturities\":[1,2,3],\"zero_rates\":[0.03,0.03],\"tau\":2,\"delta\":0.001}");
        error("E_DOMAIN", op, "{\"maturities\":[1,2,3],\"zero_rates\":[0.03,0.03,0.03],\"tau\":0,\"delta\":0.001}");
        error("E_DOMAIN", op, "{\"maturities\":[1,2,3],\"zero_rates\":[0.03,0.03,0.03],\"tau\":2,\"delta\":0}");
        error("E_DOMAIN", op, "{\"maturities\":[-1,2,3],\"zero_rates\":[0.03,0.03,0.03],\"tau\":2,\"delta\":0.001}");
        Map<?, ?> flat = ok(op, "{\"maturities\":[1,2,3],\"zero_rates\":[0.03,0.03,0.03],\"tau\":2,\"delta\":0.001}");
        assertEquals(0.0, num(flat.get("objective")), 1e-30);
    }

    // Fuzz: extreme numbers in every numeric slot give a result or a coded error, never an exception.

    @Test
    void fuzzExtremeInputs() {
        String[] extremes = {"0", "-0.0", "1e308", "-1e308", "1e-308", "5e-324", "-1", "1e15", "3"};
        String[] templates = {
            "rates.futures.convexity|{\"price\":%s,\"start_years\":%s,\"end_years\":%s,\"sigma\":%s,\"mean_reversion\":%s}",
            "calib.curve.smooth|{\"knots\":[%s,%s],\"maturities\":[%s],\"zero_rates\":[%s],\"lambda\":%s}",
            "calib.curve.robust|{\"maturities\":[%s,2,%s],\"zero_rates\":[%s,0.01,%s],\"tau\":%s,\"delta\":0.001}",
            "rates.ois.step_curve|{\"as_of\":\"2026-11-06\",\"base_rate\":%s,\"steps\":[{\"date\":\"2027-01-01\",\"rate\":%s}],"
                    + "\"jumps\":[{\"date\":\"2026-12-31\",\"factor\":%s}],\"dates\":[\"2099-12-31\"]}",
            "rates.csa.discount|{\"curve\":" + CURVE + ",\"jumps\":[{\"date\":\"2027-12-31\",\"factor\":%s}]},"
                    + "\"collateral_spread\":%s,\"fx\":{\"spot\":%s,\"forwards\":[{\"date\":\"2099-01-01\",\"forward\":%s}]},"
                    + "\"dates\":[\"2099-01-01\"]}",
            "rates.ois.fit_steps|{\"convention\":\"SOFR\",\"as_of\":\"2026-11-06\",\"step_dates\":[\"2026-12-10\"],"
                    + "\"quotes\":[{\"tenor\":\"3W\",\"rate\":%s},{\"tenor\":\"2M\",\"rate\":%s}],"
                    + "\"jumps\":[{\"date\":\"2026-11-20\",\"factor\":%s}]}",
            "rates.ois.bootstrap|{\"convention\":\"ESTR\",\"as_of\":\"2026-11-06\",\"quotes\":[{\"tenor\":\"1Y\",\"rate\":%s},"
                    + "{\"tenor\":\"2Y\",\"rate\":%s}],\"interpolation\":\"LINEAR_ZERO\",\"method\":\"GLOBAL\","
                    + "\"jumps\":[{\"date\":\"2026-12-31\",\"factor\":%s}]}",
        };
        Random rng = new Random(7);
        for (String t : templates) {
            String[] parts = t.split("\\|", 2);
            for (int trial = 0; trial < 60; trial++) {
                Object[] v = new Object[5];
                for (int i = 0; i < 5; i++) {
                    v[i] = extremes[rng.nextInt(extremes.length)];
                }
                Map<?, ?> r = run(parts[0], parts[1].formatted(v));
                assertNotEquals(null, r.get("status"));
            }
        }
    }
}
