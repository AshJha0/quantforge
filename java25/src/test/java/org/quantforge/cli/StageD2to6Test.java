package org.quantforge.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import java.util.Random;
import org.junit.jupiter.api.Test;
import org.quantforge.core.Json;
import org.quantforge.curves.Curve;
import org.quantforge.curves.Xccy;
import org.quantforge.pricing.Bonds;
import org.quantforge.pricing.Credit;
import org.quantforge.pricing.EquityD;
import org.quantforge.pricing.Inflation;

/** Stage D waves 2 and 3: identities, edge and error paths, and a fuzz pass. */
class StageD2to6Test {
    private static final LocalDate AS_OF = LocalDate.of(2026, 11, 6);
    private static final String CURVE = "{\"as_of\":\"2026-11-06\",\"interpolation\":\"LOG_LINEAR_DF\",\"pillars\":"
            + "[{\"date\":\"2027-11-06\",\"discount_factor\":0.96},{\"date\":\"2046-11-06\",\"discount_factor\":0.45}]}";
    private static final Curve FLAT = Curve.of(AS_OF, Curve.Interpolation.LOG_LINEAR_DF,
            new LocalDate[] {LocalDate.of(2027, 11, 6), LocalDate.of(2056, 11, 6)},
            new double[] {Math.exp(-0.04), Math.exp(-0.04 * 30.0274)});
    private static final Bonds.Bond BOND = new Bonds.Bond(LocalDate.of(2029, 11, 15), 0.0425, 2);
    private static final LocalDate SETTLE = LocalDate.of(2026, 11, 9);

    private static Map<?, ?> run(String op, String inputs) {
        String text = "{\"schema_version\":\"1.0\",\"case_id\":\"t\",\"operation\":\"" + op + "\",\"inputs\":" + inputs + "}";
        return (Map<?, ?>) Json.parse(Main.handle(text).json()).value();
    }

    private static void error(String code, String op, String inputs) {
        Map<?, ?> r = run(op, inputs);
        assertEquals("error", r.get("status"), op + " " + inputs);
        assertEquals(code, ((Map<?, ?>) r.get("error")).get("code"), op + " " + inputs);
    }

    // D2

    @Test
    void yieldRoundTripsAndDurationsMatchBumps() {
        Bonds.YieldPrice p = Bonds.fromYield(BOND, SETTLE, 0.041);
        assertEquals(0.041, Bonds.yieldFromPrice(BOND, SETTLE, p.clean()), 1e-14);
        double h = 1e-6;
        double up = Bonds.fromYield(BOND, SETTLE, 0.041 + h).dirty();
        double dn = Bonds.fromYield(BOND, SETTLE, 0.041 - h).dirty();
        assertEquals(p.modified(), -(up - dn) / (2 * h) / p.dirty(), 1e-7);
        // On a coupon date accrued is zero; a par-yield bond prices at 100.
        Bonds.YieldPrice par = Bonds.fromYield(BOND, LocalDate.of(2027, 5, 15), 0.0425);
        assertEquals(0.0, par.accrued(), 0.0);
        assertEquals(100.0, par.clean(), 1e-11);
        // Month-end maturity keeps month-end coupons.
        Bonds.Bond eom = new Bonds.Bond(LocalDate.of(2031, 2, 28), 0.04, 2);
        assertEquals(LocalDate.of(2030, 8, 31), eom.back(1));
    }

    @Test
    void zSpreadInvertsCurvePriceAndFrnIsParOnACouponDate() {
        double dirty = Bonds.curveDirty(BOND, SETTLE, FLAT, 0.0035);
        double z = Bonds.zSpread(BOND, SETTLE, FLAT, dirty - BOND.accrued(SETTLE));
        assertEquals(0.0035, z, 1e-13);
        LocalDate s = LocalDate.of(2026, 11, 16);
        LocalDate next = LocalDate.of(2027, 2, 16);
        double current = (FLAT.discount(s) / FLAT.discount(next) - 1) / (92 / 360.0);
        Bonds.Frn f = Bonds.frn(s, LocalDate.of(2029, 11, 16), 4, current, 0, 0, FLAT, FLAT);
        assertEquals(100.0, f.dirty(), 1e-11);
    }

    @Test
    void repoImpliedRateInvertsForward() {
        LocalDate end = LocalDate.of(2027, 6, 1); // Crosses the 2027-05-15 coupon.
        Bonds.Repo r = Bonds.repo(BOND, SETTLE, end, 100.4, 0.0385, 0.04);
        assertEquals(0.0385, Bonds.impliedRepo(BOND, SETTLE, end, 100.4, r.forwardClean()), 1e-14);
        assertEquals(0.0015, r.specialSpread(), 1e-17);
        assertEquals(0.9040, Bonds.conversionFactor(new Bonds.Bond(LocalDate.of(2033, 11, 15), 0.0425, 2),
                YearMonth.of(2026, 12), 0.06, Bonds.Contract.TEN_YEAR), 0.0);
        String b = "{\"maturity\":\"2029-11-15\",\"coupon\":0.0425,\"frequency\":2}";
        error("E_DATE_ORDER", "repo.forward", "{\"bond\":" + b + ",\"start\":\"2026-11-09\",\"end\":\"2026-11-09\","
                + "\"clean_price\":99,\"repo_rate\":0.04,\"gc_rate\":null}");
        error("E_SCHEMA", "repo.forward", "{\"bond\":" + b + ",\"start\":\"2026-11-09\",\"end\":\"2026-12-09\","
                + "\"clean_price\":99,\"repo_rate\":0.04}");
        error("E_INPUT", "bond.futures.conversion_factor", "{\"bond\":" + b + ",\"delivery_month\":\"2026-12\",\"notional_coupon\":0.05}");
        error("E_SCHEMA", "bond.futures.conversion_factor", "{\"bond\":" + b + ",\"delivery_month\":\"2026-13\",\"notional_coupon\":0.06}");
        error("E_INPUT", "bond.futures.basis", "{\"futures_price\":100,\"settlement\":\"2026-11-09\",\"delivery\":\"2026-12-01\","
                + "\"repo_rate\":0.04,\"bonds\":[]}");
        error("E_SCHEMA", "bond.price.from_yield", "{\"bond\":{\"maturity\":\"2029-11-15\",\"coupon\":0.04,\"frequency\":3},"
                + "\"settlement\":\"2026-11-09\",\"yield\":0.04}");
        error("E_OUT_OF_RANGE", "bond.price.from_curve", "{\"bond\":" + b + ",\"settlement\":\"2026-11-05\",\"curve\":" + CURVE + "}");
    }

    @Test
    void nelsonSiegelFitRecoversTruth() {
        double[] truth = {0.042, -0.006, 0.004};
        List<Bonds.Bond> bonds = List.of(BOND, new Bonds.Bond(LocalDate.of(2036, 8, 15), 0.045, 2),
                new Bonds.Bond(LocalDate.of(2034, 3, 31), 0.03, 1), new Bonds.Bond(LocalDate.of(2055, 5, 15), 0.0475, 2));
        double[] dirty = new double[bonds.size()];
        for (int i = 0; i < dirty.length; i++) {
            dirty[i] = Bonds.nsModel(bonds.get(i), SETTLE, 2.5, truth, null);
        }
        double[] w = {1, 1, 1, 1};
        double[] b = Bonds.nsBetas(bonds, dirty, w, SETTLE, 2.5);
        for (int i = 0; i < 3; i++) {
            assertEquals(truth[i], b[i], 1e-10);
        }
        try {
            Bonds.nsBetas(bonds, dirty, new double[] {1, 1, 0, 0}, SETTLE, 2.5);
            throw new AssertionError("expected E_INPUT");
        } catch (org.quantforge.core.QfError e) {
            assertEquals("E_INPUT", e.code());
        }
    }

    // D3

    @Test
    void xccyBootstrapRepricesAndNdfChecks() {
        Curve fp = FLAT;
        LocalDate start = LocalDate.of(2026, 11, 10);
        var s = Xccy.bootstrap(FLAT, fp, start, new long[] {12, 60}, new double[] {0.001, 0.002},
                Curve.Interpolation.LOG_LINEAR_DF);
        assertTrue(s.maxRepricingError() < 1e-13);
        assertEquals(0.0, Xccy.leg(Xccy.schedule(start, 12), fp, s.curve(), 0.001), 1e-13);
        // Same curve for projection and discount, no spread: the leg is zero.
        assertEquals(0.0, Xccy.leg(Xccy.schedule(start, 24), FLAT, FLAT, 0.0), 1e-15);
        String trade = "{\"fixing_date\":\"%s\",\"payment_date\":\"%s\",\"strike\":90,\"usd_notional\":1e6,\"side\":\"BUY\"}";
        error("E_DATE_ORDER", "fx.ndf.pv", "{\"usd_curve\":" + CURVE + ",\"offshore_curve\":" + CURVE + ",\"spot\":88,"
                + "\"trade\":" + trade.formatted("2027-05-10", "2027-05-06") + ",\"fixing\":null}");
        error("E_INPUT", "fx.ndf.pv", "{\"usd_curve\":" + CURVE + ",\"offshore_curve\":" + CURVE + ",\"spot\":88,"
                + "\"trade\":" + trade.formatted("2026-11-05", "2026-11-09") + ",\"fixing\":null}");
        error("E_SCHEMA", "fx.ndf.pv", "{\"usd_curve\":" + CURVE + ",\"offshore_curve\":" + CURVE + ",\"spot\":88,"
                + "\"trade\":" + trade.formatted("2027-05-06", "2027-05-10") + "}");
        try {
            Xccy.schedule(LocalDate.of(2026, 11, 10), 10);
            throw new AssertionError();
        } catch (org.quantforge.core.QfError e) {
            assertEquals("E_INPUT", e.code());
        }
    }

    // D4

    @Test
    void cdsBootstrapRepricesAndChecks() {
        LocalDate t = AS_OF;
        String[] tenors = {"1Y", "5Y", "10Y"};
        double[] spreads = {0.006, 0.012, 0.015};
        Credit.Hazard h = Credit.bootstrap(t, FLAT, 0.4, tenors, spreads);
        for (int i = 0; i < tenors.length; i++) {
            Credit.Price p = Credit.price(t, FLAT, h, 0.4, Credit.maturity(t, tenors[i]), 0.01, 1, true, false);
            assertEquals(spreads[i], p.parSpread(), 1e-9); // observation past maturity sees the next segment
        }
        assertEquals(LocalDate.of(2031, 12, 20), Credit.maturity(t, "5Y"));
        assertEquals(LocalDate.of(2026, 6, 20), Credit.roll(LocalDate.of(2026, 9, 19)));
        // Digital pays 1, not 1 - R.
        Credit.Price std = Credit.price(t, FLAT, h, 0.4, Credit.maturity(t, "5Y"), 0.01, 1, true, false);
        Credit.Price dig = Credit.price(t, FLAT, h, 0.4, Credit.maturity(t, "5Y"), 0.01, 1, true, true);
        assertEquals(std.protection() / 0.6, dig.protection(), 1e-15);
        for (Object[] c : new Object[][] {{1.0, spreads, "E_DOMAIN"}, {0.4, new double[] {0.006, -1, 0.01}, "E_DOMAIN"}}) {
            try {
                Credit.bootstrap(t, FLAT, (Double) c[0], tenors, (double[]) c[1]);
                throw new AssertionError();
            } catch (org.quantforge.core.QfError e) {
                assertEquals(c[2], e.code());
            }
        }
        try {
            Credit.bootstrap(LocalDate.of(2026, 12, 21), FLAT, 0.4, tenors, spreads);
            throw new AssertionError();
        } catch (org.quantforge.core.QfError e) {
            assertEquals("E_INPUT", e.code());
        }
    }

    // D5

    @Test
    void equityImpliedRatesInvert() {
        List<EquityD.Div> divs = List.of(new EquityD.Div(LocalDate.of(2026, 12, 18), 18),
                new EquityD.Div(LocalDate.of(2027, 3, 19), 16.5));
        LocalDate expiry = LocalDate.of(2027, 3, 19);
        double fwd = EquityD.forward(5000, FLAT, 0.003, 0, divs, expiry);
        assertEquals(0.003, EquityD.impliedBorrow(5000, FLAT, divs, expiry, fwd), 1e-14);
        EquityD.Basis b = EquityD.futuresBasis(5000, FLAT, 0.003, 0.001, divs, expiry, fwd);
        assertEquals(0.0, b.impliedSpread(), 1e-13);
        try {
            EquityD.impliedBorrow(5000, FLAT, divs, expiry, 1e9);
            throw new AssertionError();
        } catch (org.quantforge.core.QfError e) {
            assertEquals("E_NOT_BRACKETED", e.code());
        }
        EquityD.Action rights = EquityD.corporateAction("RIGHTS", 100, 10, 90, null, 0.5, 70.0, null);
        assertEquals(90.0 / 100.0, rights.factor(), 1e-15);
        assertEquals(90.0, rights.exPrice(), 1e-13);
        EquityD.Rebalance r = EquityD.rebalance(2, List.of(new EquityD.Constituent("A", 10, 10, List.of())),
                List.of(new EquityD.Constituent("A", 5, 10, List.of()), new EquityD.Constituent("B", 5, 10, List.of())));
        assertEquals(50.0, r.level(), 0.0);
        assertEquals(2.0, r.newDivisor(), 0.0);
        error("E_INPUT", "eq.trs.pv", "{\"spot\":5000,\"funding\":" + CURVE + ",\"borrow_rate\":0,\"dividends\":[],"
                + "\"trade\":{\"start\":\"2026-09-18\",\"end\":\"2027-03-19\",\"initial_price\":4890,\"shares\":1,"
                + "\"spread\":0,\"side\":\"RECEIVE_EQUITY\"},\"current_rate\":null}");
        error("E_DOMAIN", "eq.corporate_action.adjust", "{\"action\":\"SPECIAL_DIVIDEND\",\"cum_price\":10,\"shares\":1,"
                + "\"strike\":1,\"amount\":10}");
        error("E_SCHEMA", "eq.corporate_action.adjust", "{\"action\":\"MERGER\",\"cum_price\":10,\"shares\":1,\"strike\":1}");
    }

    // D6

    @Test
    void cpiCurveRepricesPillarsWithSeasonality() {
        double[] season = {0.9978, 0.9992, 1.0011, 1.0018, 1.0012, 1.0005, 0.9989, 0.9994, 1.0006, 1.0003, 0.9995, 0.9997};
        Inflation.CpiCurve c = new Inflation.CpiCurve(YearMonth.of(2026, 8), 300, new long[] {1, 5},
                new double[] {0.03, 0.025}, season);
        long base = Inflation.index(YearMonth.of(2026, 8));
        assertEquals(300 * 1.03, c.cpi(base + 12), 1e-11);
        assertEquals(300 * Math.pow(1.025, 5), c.cpi(base + 60), 1e-10);
        assertEquals(Math.sqrt(300 * 300 * 1.03) * season[1] / season[7], c.cpi(base + 6), 1e-10);
        String q = "\"base_month\":\"2026-08\",\"base_cpi\":300,\"quotes\":[{\"years\":1,\"rate\":0.03}]";
        error("E_INPUT", "infl.curve.cpi", "{" + q + ",\"seasonality\":[1,1,1],\"months\":[\"2027-01\"]}");
        error("E_DOMAIN", "infl.curve.cpi", "{" + q + ",\"seasonality\":[1,1,1,1,1,1,1,1,1,1,1,0],\"months\":[\"2027-01\"]}");
        error("E_SCHEMA", "infl.curve.cpi", "{" + q + ",\"months\":[\"2027-01\"]}");
        error("E_OUT_OF_RANGE", "infl.curve.cpi", "{" + q + ",\"seasonality\":null,\"months\":[\"2026-07\"]}");
        error("E_SCHEMA", "infl.curve.cpi", "{" + q + ",\"seasonality\":null,\"months\":[\"2026-7\"]}");
    }

    // Fuzz: extreme numbers give a result or a coded error, never an exception.

    @Test
    void fuzzExtremeInputs() {
        String[] x = {"0", "-0.0", "1e308", "-1e308", "1e-308", "-1", "1e15", "0.5", "100"};
        String b = "{\"maturity\":\"2029-11-15\",\"coupon\":%s,\"frequency\":2}";
        String[] templates = {
            "bond.price.from_yield|{\"bond\":" + b + ",\"settlement\":\"2026-11-09\",\"yield\":%s}",
            "bond.yield.from_price|{\"bond\":" + b + ",\"settlement\":\"2026-11-09\",\"clean_price\":%s}",
            "bond.spread.z|{\"bond\":" + b + ",\"settlement\":\"2026-11-09\",\"curve\":" + CURVE + ",\"clean_price\":%s}",
            "repo.implied_rate|{\"bond\":" + b + ",\"start\":\"2026-11-09\",\"end\":\"2026-12-09\",\"clean_price\":%s,\"forward_clean\":%s}",
            "bond.fit.nelson_siegel|{\"settlement\":\"2026-11-09\",\"tau\":%s,\"bonds\":[{\"maturity\":\"2029-11-15\",\"coupon\":0.04,"
                    + "\"frequency\":2,\"dirty_price\":%s},{\"maturity\":\"2031-11-15\",\"coupon\":0.04,\"frequency\":2,\"dirty_price\":%s},"
                    + "{\"maturity\":\"2036-11-15\",\"coupon\":0.04,\"frequency\":2,\"dirty_price\":%s}]}",
            "credit.cds.bootstrap|{\"trade_date\":\"2026-11-06\",\"discount\":" + CURVE + ",\"recovery\":%s,"
                    + "\"quotes\":[{\"tenor\":\"1Y\",\"spread\":%s},{\"tenor\":\"5Y\",\"spread\":%s}]}",
            "eq.borrow.implied|{\"spot\":%s,\"funding\":" + CURVE + ",\"dividends\":[{\"ex_date\":\"2027-01-01\",\"amount\":%s}],"
                    + "\"expiry\":\"2027-06-01\",\"forward\":%s}",
            "infl.curve.cpi|{\"base_month\":\"2026-08\",\"base_cpi\":%s,\"quotes\":[{\"years\":1,\"rate\":%s},{\"years\":3,\"rate\":%s}],"
                    + "\"seasonality\":null,\"months\":[\"2099-12\",\"2026-08\"]}",
            "fx.ndf.pv|{\"usd_curve\":" + CURVE + ",\"offshore_curve\":" + CURVE + ",\"spot\":%s,\"trade\":{\"fixing_date\":\"2027-05-06\","
                    + "\"payment_date\":\"2027-05-10\",\"strike\":%s,\"usd_notional\":%s,\"side\":\"BUY\"},\"fixing\":null}",
        };
        Random rng = new Random(11);
        for (String t : templates) {
            String[] parts = t.split("\\|", 2);
            for (int trial = 0; trial < 40; trial++) {
                Object[] v = new Object[5];
                for (int i = 0; i < 5; i++) {
                    v[i] = x[rng.nextInt(x.length)];
                }
                assertNotNull(run(parts[0], parts[1].formatted(v)).get("status"));
            }
        }
    }
}
