package org.quantforge.jcstress;

import org.openjdk.jcstress.annotations.Actor;
import org.openjdk.jcstress.annotations.Expect;
import org.openjdk.jcstress.annotations.JCStressTest;
import org.openjdk.jcstress.annotations.Outcome;
import org.openjdk.jcstress.annotations.State;
import org.openjdk.jcstress.infra.results.JJ_Result;

/**
 * K-5 planted fault 3 (KR-288): what the snapshot design forbids, done on purpose. The writer updates a mutable
 * snapshot in place instead of publishing a new immutable one; the reader can then see one field from the new
 * version and one from the old. Graded ACCEPTABLE_INTERESTING so the default run stays green; the count of mixed
 * outcomes is the evidence that jcstress sees the fault (spec section 4). Latency-aware analytics on simulated
 * data.
 */
@JCStressTest
@Outcome(id = {"0, 0", "1, 1"}, expect = Expect.ACCEPTABLE, desc = "whole old or whole new")
@Outcome(id = {"1, 0", "0, 1"}, expect = Expect.ACCEPTABLE_INTERESTING,
    desc = "planted fault 3: fields from two versions (in-place mutation)")
@State
public class InPlaceMutationFault {
    static final class Mutable {
        long estimate;
        long bound;
    }

    private final Mutable m = new Mutable();

    @Actor
    public void writer() {
        m.estimate = 1;
        m.bound = 1;
    }

    @Actor
    public void reader(JJ_Result r) {
        r.r1 = m.bound;
        r.r2 = m.estimate;
    }
}
