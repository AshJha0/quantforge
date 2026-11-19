package org.quantforge.execution;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;
import org.quantforge.execution.Execution.*;

/** H-5 ({@code 10-execution/library-interfaces.md} 2.5): validated value types and the typed fill overload. */
class ExecutionApiH5Test {
    private static void code(Runnable r, String c) {
        QfError e = assertThrows(QfError.class, r::run);
        assertEquals(c, e.code());
    }

    @Test
    void acParamsValidatedWhenBuilt() {
        code(() -> new AcParams(0, 5, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7), "E_INPUT");
        code(() -> new AcParams(1e6, 5, 0, 0.95, 0.0625, 2.5e-6, 2.5e-7), "E_INPUT");
        code(() -> new AcParams(1e6, 5, 5, -1, 0.0625, 2.5e-6, 2.5e-7), "E_DOMAIN");
        code(() -> new AcParams(1e6, 5, 5, Double.NaN, 0.0625, 2.5e-6, 2.5e-7), "E_DOMAIN");
        code(() -> new AcParams(1e6, 5, 5, 0.95, 0.0625, 1e-9, 2.5e-7), "E_DOMAIN");
        assertNotNull(new AcParams(1e6, 5, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7));
    }

    @Test
    void fillAndQuotesValidated() {
        code(() -> new Fill(0, 10), "E_INPUT");
        code(() -> new Fill(1, -1), "E_DOMAIN");
        code(() -> new Fill(1, Double.POSITIVE_INFINITY), "E_DOMAIN");
        code(() -> new Quotes(1, 1, 2, 1), "E_DOMAIN");
    }

    @Test
    void typedFillsEqualArrays() {
        Shortfall a = Execution.shortfall(Side.SELL, 10, 10.05, 10.3, 200, List.of(new Fill(100, 10.1), new Fill(50, 10.2)), 1.5, 10.12);
        Shortfall b = Execution.shortfall(Side.SELL, 10, 10.05, 10.3, 200, new double[] {100, 50}, new double[] {10.1, 10.2}, 1.5, 10.12);
        assertEquals(b, a);
        assertNull(Execution.shortfall(Side.BUY, 10, 10, 10, 1, List.of(), 0, null).vwapSlippage());
    }
}
