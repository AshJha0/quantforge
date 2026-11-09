package org.quantforge.vol;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.quantforge.core.QfError;

/** R8 lnGamma and digamma, R10 VIX null quotes and local-vol continuity at slice expiries (ruling F-17). */
class StageFVolTest {
    @Test
    void lnGammaAgainstKnownValues() {
        assertEquals(0.0, GarchMle.lnGamma(1.0), 1e-15);
        assertEquals(0.0, GarchMle.lnGamma(2.0), 1e-15);
        assertEquals(0.5 * Math.log(Math.PI), GarchMle.lnGamma(0.5), 1e-15);
        assertEquals(Math.log(362880.0), GarchMle.lnGamma(10.0), 1e-14 * Math.log(362880.0));
        assertEquals(5905.220423209181, GarchMle.lnGamma(1000.0), 1e-14 * 5905.22);
        assertEquals(-0.5772156649015329, GarchMle.digamma(1.0), 1e-13);
        assertEquals("E_DOMAIN", assertThrows(QfError.class, () -> GarchMle.lnGamma(0.0)).code());
    }

    private static List<VarianceStrip.Quote> strip() {
        List<VarianceStrip.Quote> q = new ArrayList<>();
        for (int k = 70; k <= 130; k += 5) {
            double c = Black.lognormal(1, 100, k, 0.1, 1, 0.2);
            double p = Black.lognormal(-1, 100, k, 0.1, 1, 0.2);
            q.add(new VarianceStrip.Quote(k, c - 0.05 < 0 ? 0 : c - 0.05, c + 0.05, p - 0.05 < 0 ? 0 : p - 0.05,
                    p + 0.05));
        }
        return q;
    }

    @Test
    void vixNullQuotes() {
        VarianceStrip.Term base = VarianceStrip.term(52560, 0.0, strip());
        // a null put on the far wing removes only that put
        List<VarianceStrip.Quote> q = strip();
        VarianceStrip.Quote w = q.getFirst();
        q.set(0, new VarianceStrip.Quote(w.strike(), w.callBid(), w.callAsk(), Double.NaN, w.putAsk()));
        VarianceStrip.Term t = VarianceStrip.term(52560, 0.0, q);
        assertEquals(base.forward(), t.forward(), 0.0);
        assertEquals(base.k0(), t.k0(), 0.0);
        // null at K0 refuses the term
        List<VarianceStrip.Quote> atm = strip();
        int i0 = (int) ((base.k0() - 70) / 5);
        VarianceStrip.Quote k0 = atm.get(i0);
        atm.set(i0, new VarianceStrip.Quote(k0.strike(), Double.NaN, k0.callAsk(), k0.putBid(), k0.putAsk()));
        assertEquals("E_INPUT", assertThrows(QfError.class, () -> VarianceStrip.term(52560, 0.0, atm)).code());
        // no strike with both sides quoted
        List<VarianceStrip.Quote> none = new ArrayList<>();
        for (VarianceStrip.Quote x : strip()) {
            none.add(new VarianceStrip.Quote(x.strike(), Double.NaN, Double.NaN, x.putBid(), x.putAsk()));
        }
        assertEquals("E_INPUT", assertThrows(QfError.class, () -> VarianceStrip.term(52560, 0.0, none)).code());
    }

    @Test
    void localVolContinuityAtSliceExpiries() {
        List<Surfaces.Slice> s = List.of(new Surfaces.Slice(0.5, new Smile.Svi(0.01, 0.1, -0.3, 0.0, 0.2)),
                new Surfaces.Slice(1.0, new Smile.Svi(0.02, 0.1, -0.3, 0.0, 0.2)));
        for (double k : new double[] {-0.4, 0.0, 0.3}) {
            for (double tj : new double[] {0.5, 1.0}) {
                double[] t = {tj * (1 - 1e-9), tj, tj * (1 + 1e-9)};
                Surfaces.LocalVol lv = Surfaces.dupire(s, t, new double[] {k, k, k});
                assertEquals(lv.totalVariance()[1], lv.totalVariance()[0], 3e-9 * lv.totalVariance()[1]); // SQ F-J7
                assertEquals(lv.impliedVol()[1], lv.impliedVol()[0], 3e-9 * lv.impliedVol()[1]); // SQ F-J7
                assertEquals(lv.localVol()[1], lv.localVol()[2], 1e-6 * lv.localVol()[1]); // a node is its right limit
            }
            // the short-end jump: left uses w_1/T_1, right the first interval slope; g is shared
            Surfaces.LocalVol at = Surfaces.dupire(s, new double[] {0.5 * (1 - 1e-12), 0.5}, new double[] {k, k});
            double w1 = s.get(0).svi().w(k);
            double w2 = s.get(1).svi().w(k);
            assertEquals(Math.sqrt((w1 / 0.5) / ((w2 - w1) / 0.5)), at.localVol()[0] / at.localVol()[1], 1e-8);
        }
    }
}
