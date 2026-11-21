package org.quantforge.risk;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.ToLongFunction;

/**
 * Stage K, K-5 (spec {@code 12-platform/lock-free-snapshots.md} 1.0.0, ruling KR-280, confirmed 2026-11-20): one writer
 * publishes immutable snapshots to many readers. Latency-aware analytics on simulated data.
 *
 * <p>The current snapshot sits in one {@link AtomicReference}: the writer builds an immutable value (a record
 * with final fields), then stores it with release semantics; a reader loads it with acquire semantics and reads
 * the final fields. The garbage collector reclaims old snapshots. A publish and a read are each one access
 * (KR-282: wait-free on the JVM's terms; a safepoint can still pause any thread). No latency is claimed: no
 * timing run exists.
 *
 * @param <T> the immutable snapshot type
 */
public final class LiveSnapshotCell<T> {
    private final AtomicReference<T> current;
    private final AtomicBoolean writing = new AtomicBoolean();
    private final ToLongFunction<T> version;

    /**
     * @param initial the first snapshot
     * @param version reads the strictly increasing version of a snapshot
     */
    public LiveSnapshotCell(T initial, ToLongFunction<T> version) {
        if (initial == null) {
            throw new IllegalArgumentException("initial snapshot is null");
        }
        this.current = new AtomicReference<>(initial);
        this.version = version;
    }

    /** The reader's acquire load. */
    public T read() {
        return current.getAcquire();
    }

    /**
     * The writer's release store. One writer only (KR-280): a second concurrent publish is refused, and so is a
     * version that does not increase.
     */
    public void publish(T next) {
        if (!writing.compareAndSet(false, true)) {
            throw new IllegalStateException("LiveSnapshotCell has one writer (KR-280)");
        }
        try {
            if (version.applyAsLong(next) <= version.applyAsLong(current.getPlain())) {
                throw new IllegalArgumentException("versions must strictly increase (KR-280)");
            }
            current.setRelease(next);
        } finally {
            writing.set(false);
        }
    }
}
