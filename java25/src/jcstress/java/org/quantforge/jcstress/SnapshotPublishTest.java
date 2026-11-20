package org.quantforge.jcstress;

import org.openjdk.jcstress.annotations.Actor;
import org.openjdk.jcstress.annotations.Expect;
import org.openjdk.jcstress.annotations.JCStressTest;
import org.openjdk.jcstress.annotations.Outcome;
import org.openjdk.jcstress.annotations.State;
import org.openjdk.jcstress.infra.results.JI_Result;
import org.quantforge.risk.LiveSnapshot;
import org.quantforge.risk.LiveSnapshot.HedgeSnapshot;
import org.quantforge.risk.LiveSnapshotCell;

/**
 * K-5 (KR-280, KR-285, confirmed 2026-11-20): the writer builds a snapshot inside its actor and publishes it; the reader must
 * see either the initial snapshot or the new one, each whole (checksum intact). Fields from two versions, or a
 * partly constructed record, are FORBIDDEN. Latency-aware analytics on simulated data.
 */
@JCStressTest
@Outcome(id = "0, 1", expect = Expect.ACCEPTABLE, desc = "initial snapshot, whole")
@Outcome(id = "1, 1", expect = Expect.ACCEPTABLE, desc = "published snapshot, whole")
@Outcome(expect = Expect.FORBIDDEN, desc = "torn or partly constructed snapshot")
@State
public class SnapshotPublishTest {
    private final LiveSnapshotCell<HedgeSnapshot> cell = new LiveSnapshotCell<>(snap(0), HedgeSnapshot::version);

    static HedgeSnapshot snap(long v) {
        double x = v * 0.25;
        double y = v * -1.5;
        double z = v + 7.0;
        long c = LiveSnapshot.checksum(v, v, Double.doubleToRawLongBits(x), Double.doubleToRawLongBits(y),
            Double.doubleToRawLongBits(z), Double.doubleToRawLongBits(x), Double.doubleToRawLongBits(y),
            Double.doubleToRawLongBits(z));
        return new HedgeSnapshot(v, v, x, y, z, x, y, z, c);
    }

    @Actor
    public void writer() {
        cell.publish(snap(1));
    }

    @Actor
    public void reader(JI_Result r) {
        HedgeSnapshot s = cell.read();
        r.r1 = s.version();
        r.r2 = s.intact() ? 1 : 0;
    }
}
