package org.quantforge.risk;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.quantforge.core.Json;
import org.quantforge.risk.LiveSnapshot.HedgeInstrument;
import org.quantforge.risk.LiveSnapshot.HedgeSnapshot;
import org.quantforge.risk.StageK.ZeroPosition;

/**
 * K-5 (PROPOSED, KR-280 to KR-288) on the shared scenario {@code datasets/scenarios/k5_snapshot.json}. The JVM
 * memory-model test is the jcstress profile ({@code src/jcstress}); this is the scenario-level race test.
 * Latency-aware analytics on simulated data; nothing here is timed.
 */
class LiveSnapshotTest {
    private static final Map<?, ?> SCEN;
    private static final List<ZeroPosition> BOOK = new ArrayList<>();
    private static final HedgeInstrument HEDGE;

    static {
        try {
            SCEN = (Map<?, ?>) Json.parse(Files.readString(Path.of("..", "datasets", "scenarios",
                "k5_snapshot.json"))).value();
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
        for (Object o : (List<?>) SCEN.get("book")) {
            Map<?, ?> p = (Map<?, ?>) o;
            BOOK.add(new ZeroPosition(num(p, "notional"), num(p, "maturity"), num(p, "yield")));
        }
        Map<?, ?> h = (Map<?, ?>) SCEN.get("hedge");
        HEDGE = new HedgeInstrument(num(h, "maturity"), num(h, "yield"));
    }

    private static double num(Map<?, ?> m, String k) {
        return ((Json.Number) m.get(k)).value();
    }

    private static HedgeSnapshot build(long k, double h) {
        return LiveSnapshot.build(k, k, BOOK, HEDGE, h);
    }

    private static boolean close(double a, double b, double tol) {
        return Math.abs(a - b) <= tol * Math.abs(b);
    }

    @Test
    void scenarioExpectedValues() {
        double tol = num(SCEN, "tolerance_relative");
        for (Object o : (List<?>) SCEN.get("expected")) {
            Map<?, ?> row = (Map<?, ?>) o;
            long k = (long) num(row, "version");
            HedgeSnapshot s = build(k, LiveSnapshot.scenarioShift(k));
            assertTrue(s.intact());
            assertEquals(num(row, "shift"), s.shift());
            assertTrue(close(s.estimatePnl(), num(row, "estimate_pnl"), tol));
            assertTrue(close(s.bound(), num(row, "bound"), tol));
            assertTrue(close(s.bookDelta(), num(row, "book_delta"), tol));
            assertTrue(close(s.hedgeUnitDelta(), num(row, "hedge_unit_delta"), tol));
            assertTrue(close(s.hedgeNotional(), num(row, "hedge_notional"), tol));
            double residual = s.bookDelta() + s.hedgeNotional() * s.hedgeUnitDelta();
            assertTrue(Math.abs(residual) <= 1e-9 * Math.abs(s.bookDelta()));
        }
    }

    @Test
    void checksumPinnedValues() {
        assertEquals(LiveSnapshot.CHECK_SEED, LiveSnapshot.checksum());
        assertEquals(0xF6E599AEF89D022FL, LiveSnapshot.checksum(0L));
        assertEquals(0x8517CC75DE438E52L, LiveSnapshot.checksum(1L, 2L, 3L));
    }

    @Test
    void exactness1000Publishes() {
        LiveSnapshotCell<HedgeSnapshot> cell = new LiveSnapshotCell<>(build(0, 0.0), HedgeSnapshot::version);
        long n = (long) num(SCEN, "exactness_publishes");
        for (long k = 1; k <= n; k++) {
            double h = LiveSnapshot.scenarioShift(k);
            cell.publish(build(k, h));
            HedgeSnapshot s = cell.read();
            StageK.Intraday risk = StageK.deltaGammaBound(BOOK, h);
            double d = LiveSnapshot.bookDelta(BOOK, h);
            double u = LiveSnapshot.hedgeUnitDelta(HEDGE, h);
            assertEquals(k, s.version());
            assertArrayEquals(new long[] {bits(risk.estimatePnl()), bits(risk.bound()), bits(d), bits(u), bits(-d / u)},
                new long[] {bits(s.estimatePnl()), bits(s.bound()), bits(s.bookDelta()), bits(s.hedgeUnitDelta()),
                    bits(s.hedgeNotional())});
        }
    }

    private static long bits(double x) {
        return Double.doubleToRawLongBits(x);
    }

    @Test
    void corruptedFieldFailsTheReaderCheck() {
        HedgeSnapshot s = build(5, LiveSnapshot.scenarioShift(5));
        HedgeSnapshot bad = new HedgeSnapshot(s.version(), s.asOf(), s.shift(), s.estimatePnl(),
            Math.nextUp(s.bound()), s.bookDelta(), s.hedgeUnitDelta(), s.hedgeNotional(), s.check());
        assertFalse(bad.intact());
        HedgeSnapshot bad2 = new HedgeSnapshot(6, s.asOf(), s.shift(), s.estimatePnl(), s.bound(), s.bookDelta(),
            s.hedgeUnitDelta(), s.hedgeNotional(), s.check());
        assertFalse(bad2.intact());
    }

    @Test
    void writerRules() {
        HedgeSnapshot s0 = build(3, 0.0);
        LiveSnapshotCell<HedgeSnapshot> cell = new LiveSnapshotCell<>(s0, HedgeSnapshot::version);
        assertSame(s0, cell.read());
        assertThrows(IllegalArgumentException.class, () -> cell.publish(build(3, 0.0)));
        assertThrows(IllegalArgumentException.class, () -> new LiveSnapshotCell<HedgeSnapshot>(null,
            HedgeSnapshot::version));
        // A second writer inside publish is refused: simulate it with a version function that re-enters.
        AtomicReference<LiveSnapshotCell<HedgeSnapshot>> holder = new AtomicReference<>();
        holder.set(new LiveSnapshotCell<>(s0, x -> {
            if (x.version() == 10) {
                holder.get().publish(build(11, 0.0));
            }
            return x.version();
        }));
        assertThrows(IllegalStateException.class, () -> holder.get().publish(build(10, 0.0)));
        holder.get().publish(build(12, 0.0));
        assertEquals(12, holder.get().read().version());
        assertEquals(0.0, LiveSnapshot.scenarioShift(0));
        assertEquals(0.005, LiveSnapshot.scenarioShift(1));
    }

    private static long publishes() {
        String env = System.getenv("QF_SNAPSHOT_PUBLISHES");
        return env != null ? Long.parseLong(env)
            : (long) num((Map<?, ?>) SCEN.get("race"), "publishes_default");
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 4, 16})
    void raceScenario(int readers) throws InterruptedException {
        long p = publishes();
        LiveSnapshotCell<HedgeSnapshot> cell = new LiveSnapshotCell<>(build(0, 0.0), HedgeSnapshot::version);
        AtomicLong torn = new AtomicLong();
        AtomicLong nonMonotone = new AtomicLong();
        AtomicLong mismatched = new AtomicLong();
        AtomicLong finalSeen = new AtomicLong();
        AtomicLong reads = new AtomicLong();
        CountDownLatch ready = new CountDownLatch(readers);
        List<Thread> threads = new ArrayList<>();
        for (int i = 0; i < readers; i++) {
            threads.add(Thread.ofPlatform().start(() -> {
                ready.countDown();
                long last = -1;
                long n = 0;
                while (true) {
                    HedgeSnapshot s = cell.read();
                    n++;
                    if (!s.intact()) {
                        torn.incrementAndGet();
                    }
                    if (s.version() < last) {
                        nonMonotone.incrementAndGet();
                    }
                    last = Math.max(last, s.version());
                    if (n % 64 == 0 && !s.equals(LiveSnapshot.build(s.version(), s.asOf(), BOOK, HEDGE, s.shift()))) {
                        mismatched.incrementAndGet();
                    }
                    if (s.version() >= p) {
                        finalSeen.incrementAndGet();
                        reads.addAndGet(n);
                        return;
                    }
                }
            }));
        }
        ready.await();
        for (long k = 1; k <= p; k++) {
            cell.publish(build(k, LiveSnapshot.scenarioShift(k)));
        }
        for (Thread t : threads) {
            t.join();
        }
        System.out.printf("race: readers=%d publishes=%d reads=%d torn=%d non_monotone=%d mismatched=%d final_seen=%s"
            + " (latency-aware analytics on simulated data; not timed)%n", readers, p, reads.get(), torn.get(),
            nonMonotone.get(), mismatched.get(), finalSeen.get() == readers);
        assertEquals(0, torn.get());
        assertEquals(0, nonMonotone.get());
        assertEquals(0, mismatched.get());
        assertEquals(readers, finalSeen.get());
    }
}
