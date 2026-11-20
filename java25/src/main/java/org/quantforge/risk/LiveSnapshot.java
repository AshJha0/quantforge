package org.quantforge.risk;

import java.util.List;
import org.quantforge.research.StressDrift;
import org.quantforge.risk.StageK.ZeroPosition;

/**
 * Stage K, K-5 (KR-283, KR-287, confirmed 2026-11-20): the hedge snapshot the writer publishes, and its per-publish
 * computation. Latency-aware analytics on simulated data. The hedge is a recommended quantity only: no order,
 * no venue.
 */
public final class LiveSnapshot {
    private LiveSnapshot() {}

    /** KR-287 checksum seed. */
    public static final long CHECK_SEED = 0x9E3779B97F4A7C15L;
    /** KR-287 checksum multiplier. */
    public static final long CHECK_MUL = 0x94D049BB133111EBL;

    /** KR-287: {@code c = rotl64(c xor w, 27) * MUL mod 2^64} from {@code SEED}. */
    public static long checksum(long... words) {
        long c = CHECK_SEED;
        for (long w : words) {
            c = Long.rotateLeft(c ^ w, 27) * CHECK_MUL;
        }
        return c;
    }

    /** One immutable snapshot (KR-280): final fields only. */
    public record HedgeSnapshot(long version, long asOf, double shift, double estimatePnl, double bound,
            double bookDelta, double hedgeUnitDelta, double hedgeNotional, long check) {
        /** The eight checksummed words (KR-287). */
        public long[] words() {
            return new long[] {version, asOf, Double.doubleToRawLongBits(shift),
                Double.doubleToRawLongBits(estimatePnl), Double.doubleToRawLongBits(bound),
                Double.doubleToRawLongBits(bookDelta), Double.doubleToRawLongBits(hedgeUnitDelta),
                Double.doubleToRawLongBits(hedgeNotional)};
        }

        /** The reader's torn-read test. */
        public boolean intact() {
            return checksum(words()) == check;
        }
    }

    /** The zero-coupon hedge instrument: one unit pays 1 at {@code maturity}. */
    public record HedgeInstrument(double maturity, double yield) {}

    /** {@code fsum(-T * (N * exp(-(y + h) * T)))}: the book's parallel delta at the shifted yields (KR-283). */
    public static double bookDelta(List<ZeroPosition> positions, double shift) {
        double[] terms = new double[positions.size()];
        for (int i = 0; i < terms.length; i++) {
            ZeroPosition p = positions.get(i);
            terms[i] = -p.maturity() * (p.notional() * Math.exp(-(p.yield() + shift) * p.maturity()));
        }
        return StressDrift.fsum(terms);
    }

    /** {@code -T_H * exp(-(y_H + h) * T_H)}: the delta of one unit of the hedge zero (KR-283). */
    public static double hedgeUnitDelta(HedgeInstrument hedge, double shift) {
        return -hedge.maturity() * Math.exp(-(hedge.yield() + shift) * hedge.maturity());
    }

    /** The writer's per-publish computation: direct library calls only (KR-283, KR-284). */
    public static HedgeSnapshot build(long version, long asOf, List<ZeroPosition> positions,
            HedgeInstrument hedge, double shift) {
        StageK.Intraday risk = StageK.deltaGammaBound(positions, shift);
        double d = bookDelta(positions, shift);
        double u = hedgeUnitDelta(hedge, shift);
        double q = -d / u;
        long c = checksum(version, asOf, Double.doubleToRawLongBits(shift),
            Double.doubleToRawLongBits(risk.estimatePnl()), Double.doubleToRawLongBits(risk.bound()),
            Double.doubleToRawLongBits(d), Double.doubleToRawLongBits(u), Double.doubleToRawLongBits(q));
        return new HedgeSnapshot(version, asOf, shift, risk.estimatePnl(), risk.bound(), d, u, q, c);
    }

    /** KR-287: 0 for version 0, else {@code ((k * 7919) mod 401 - 200) * 5e-5}. */
    public static double scenarioShift(long k) {
        return k == 0 ? 0.0 : (double) (Math.floorMod(k * 7919L, 401L) - 200) * 5e-5;
    }
}
