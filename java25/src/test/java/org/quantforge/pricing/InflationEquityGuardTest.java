package org.quantforge.pricing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.quantforge.pricing.BondsGuardTest.C;
import static org.quantforge.pricing.BondsGuardTest.NAN;
import static org.quantforge.pricing.BondsGuardTest.S;
import static org.quantforge.pricing.BondsGuardTest.fails;
import static org.quantforge.pricing.BondsGuardTest.nan;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** Library-level guards of Inflation and EquityCurves. */
class InflationEquityGuardTest {
    static final Inflation.CpiCurve CPI = new Inflation.CpiCurve(YearMonth.of(2025, 12), 300.0, new long[] {1, 5},
            new double[] {0.02, 0.025}, null);
    static final Bonds.Bond B = new Bonds.Bond(LocalDate.of(2031, 2, 15), 0.01, 2);

    @Test
    void inflationGuards() {
        LocalDate pay = LocalDate.of(2031, 3, 2);
        nan("k", () -> Inflation.zcis(CPI, C, 5, NAN, 1e6, true, pay));
        nan("n", () -> Inflation.zcis(CPI, C, 5, 0.02, NAN, true, pay));
        fails("E_INPUT", "years", () -> Inflation.zcis(CPI, C, 0, 0.02, 1e6, true, pay));
        fails("E_INPUT", "years", () -> Inflation.zcis(CPI, C, 101, 0.02, 1e6, true, pay));
        assertTrue(Double.isFinite(Inflation.zcis(CPI, C, 1, 0.02, 1e6, true, pay).pv()));
        assertTrue(Double.isFinite(Inflation.zcis(CPI, C, 100, 0.02, 1e6, true, pay).pv()));
        Map<Long, Double> fx = Map.of(Inflation.index(YearMonth.of(2025, 12)), 300.0,
                Inflation.index(YearMonth.of(2026, 1)), 301.0);
        nan("realYield", () -> Inflation.linker(B, S, NAN, 290.0, fx));
        nan("baseRef", () -> Inflation.linker(B, S, 0.01, NAN, fx));
        fails("E_DOMAIN", "base_ref_cpi", () -> Inflation.linker(B, S, 0.01, 0.0, fx));
        fails("E_DATE_ORDER", "settlement", () -> Inflation.linker(B, B.maturity(), 0.01, 290.0, fx));
        assertEquals(300.0 + 1.0 / 31.0 * 1.0, Inflation.linker(B, S, 0.01, 290.0, fx).refCpi(), 1e-12);
        nan("baseRef", () -> Inflation.linkerCurve(B, S, NAN, CPI, C));
        fails("E_DOMAIN", "base_ref_cpi", () -> Inflation.linkerCurve(B, S, 0.0, CPI, C));
        fails("E_DATE_ORDER", "settlement", () -> Inflation.linkerCurve(B, B.maturity(), 290.0, CPI, C));
    }

    @Test
    void equityGuards() {
        List<EquityCurves.Div> none = List.of();
        LocalDate e = LocalDate.of(2027, 3, 2);
        nan("spot", () -> EquityCurves.forward(NAN, C, 0.0, 0.0, none, e));
        nan("b", () -> EquityCurves.forward(100.0, C, NAN, 0.0, none, e));
        nan("s", () -> EquityCurves.forward(100.0, C, 0.0, NAN, none, e));
        LocalDate[] ex = {e};
        nan("spot", () -> EquityCurves.impliedDividends(NAN, C, 0.0, ex, new double[] {100.0}));
        nan("b", () -> EquityCurves.impliedDividends(100.0, C, NAN, ex, new double[] {100.0}));
        nan("prices", () -> EquityCurves.impliedDividends(100.0, C, 0.0, ex, new double[] {NAN}));
        nan("spot", () -> EquityCurves.impliedBorrow(NAN, C, none, e, 101.0));
        nan("forward", () -> EquityCurves.impliedBorrow(100.0, C, none, e, NAN));
        nan("spot", () -> EquityCurves.futuresBasis(NAN, C, 0.0, 0.0, none, e, 101.0));
        nan("b", () -> EquityCurves.futuresBasis(100.0, C, NAN, 0.0, none, e, 101.0));
        nan("s", () -> EquityCurves.futuresBasis(100.0, C, 0.0, NAN, none, e, 101.0));
        nan("price", () -> EquityCurves.futuresBasis(100.0, C, 0.0, 0.0, none, e, NAN));
        List<EquityCurves.Constituent> cs = List.of(new EquityCurves.Constituent("A", 10.0, 50.0, none));
        nan("divisor", () -> EquityCurves.indexDividends(NAN, cs, ex, ex, new double[] {1.0}));
        nan("implied", () -> EquityCurves.indexDividends(5.0, cs, ex, ex, new double[] {NAN}));
        nan("divisor", () -> EquityCurves.rebalance(NAN, cs, cs));
        List<EquityCurves.Constituent> dup = List.of(cs.get(0), cs.get(0));
        fails("E_INPUT", "constituents", () -> EquityCurves.rebalance(5.0, dup, cs));
        fails("E_INPUT", "new_constituents", () -> EquityCurves.rebalance(5.0, cs, dup));
        fails("E_DOMAIN", "divisor", () -> EquityCurves.rebalance(0.0, cs, cs));
        nan("p", () -> EquityCurves.corporateAction("SPLIT", NAN, 100.0, 50.0, 2.0, null, null, null));
        nan("shares", () -> EquityCurves.corporateAction("SPLIT", 80.0, NAN, 50.0, 2.0, null, null, null));
        nan("strike", () -> EquityCurves.corporateAction("SPLIT", 80.0, 100.0, NAN, 2.0, null, null, null));
        fails("E_DOMAIN", "ratio", () -> EquityCurves.corporateAction("SPLIT", 80.0, 100.0, 50.0, 0.0, null,
                null, null));
        fails("E_DOMAIN", null, () -> EquityCurves.corporateAction("RIGHTS", 80.0, 100.0, 50.0, null, 0.0, 60.0,
                null));
        fails("E_DOMAIN", null, () -> EquityCurves.corporateAction("RIGHTS", 80.0, 100.0, 50.0, null, 1.0, 0.0,
                null));
        fails("E_DOMAIN", "amount", () -> EquityCurves.corporateAction("SPECIAL_DIVIDEND", 80.0, 100.0, 50.0, null,
                null, null, 0.0));
        fails("E_DOMAIN", "amount", () -> EquityCurves.corporateAction("SPECIAL_DIVIDEND", 80.0, 100.0, 50.0, null,
                null, null, 80.0));
        assertEquals(0.5, EquityCurves.corporateAction("SPECIAL_DIVIDEND", 80.0, 100.0, 50.0, null, null, null,
                40.0).factor(), 0.0);
        LocalDate st = LocalDate.of(2026, 6, 2);
        nan("spot", () -> EquityCurves.trs(NAN, C, 0.0, none, st, e, 100.0, 1e6, 0.0, true, null));
        nan("b", () -> EquityCurves.trs(100.0, C, NAN, none, st, e, 100.0, 1e6, 0.0, true, null));
        nan("s0", () -> EquityCurves.trs(100.0, C, 0.0, none, st, e, NAN, 1e6, 0.0, true, null));
        nan("n", () -> EquityCurves.trs(100.0, C, 0.0, none, st, e, 100.0, NAN, 0.0, true, null));
        nan("spread", () -> EquityCurves.trs(100.0, C, 0.0, none, st, e, 100.0, 1e6, NAN, true, null));
    }
}
