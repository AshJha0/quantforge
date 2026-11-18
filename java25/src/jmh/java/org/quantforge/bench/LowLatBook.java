package org.quantforge.bench;

import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeMap;
import org.quantforge.core.Rng;
import org.quantforge.micro.FastBook;

/**
 * H-9 harness, Java ({@code specifications/09-microstructure/low-latency-book.md}; targets L3 and L5 in
 * {@code low-latency-targets.md}). Reads workload S as written by the C++ {@code qf_lowlat_book gen} (same file, same
 * hash). Same method as the C++ and Rust harnesses: correctness pass first; warm-up 1,000,000 messages unmeasured;
 * {@code System.nanoTime} before and after each {@code apply}; HDR-style histogram (3 significant digits, 1 ns to
 * 10 s) per op kind and pooled; queries every 1,000th measured message; clock cost on 1,000,000 empty pairs, not
 * subtracted; batch timing (1,000 per sample).
 *
 * <p>Allocation (H-9(b), Java rule): run under {@code -XX:StartFlightRecording} and {@code -Xlog:gc}; in addition the
 * harness reads the thread's allocated bytes ({@code com.sun.management.ThreadMXBean}) before and after the measured
 * region and reports them, and reports the GC count over the region.
 *
 * <pre>
 * java -cp target/classes -Xlog:gc:file=gc.log -XX:StartFlightRecording=filename=h9.jfr,settings=profile \
 *   org.quantforge.bench.LowLatBook S.bin 5 java_S.json
 * </pre>
 */
public final class LowLatBook {
    static final int DEPTH = 100;
    static final int WARMUP = 1_000_000;
    static final long SEED = 20261117L;
    static final String[] KINDS = {"snapshot", "add", "modify", "delete", "trade", "sweep", "refill", "truncated_price"};
    static final String[] QUERIES = {"best_bid", "best_ask", "qty_at_present", "qty_at_absent", "top10", "top100"};

    /** HdrHistogram's bucket rule at 3 significant digits (2048 sub-buckets, unit 1 ns, highest 10 s). */
    static final class Hist {
        static final long MAX = 10_000_000_000L;
        final long[] counts = new long[index(MAX) + 1];
        long n;
        long sum;
        long mn = Long.MAX_VALUE;
        long mx;

        static int index(long v) {
            int bucket = 64 - Long.numberOfLeadingZeros(v | 2047L) - 11;
            return (bucket << 10) + (int) (v >>> bucket);
        }

        static long highest(int i) {
            int b = i >> 10;
            int sub = i - (b << 10);
            if (b > 0 && sub < 1024) {
                b--;
                sub += 1024;
            }
            return ((long) (sub + 1) << b) - 1;
        }

        void record(long v) {
            long x = Math.min(Math.max(v, 0), MAX);
            counts[index(x)]++;
            n++;
            sum += x;
            mn = Math.min(mn, x);
            mx = Math.max(mx, x);
        }

        long pct(double p) {
            if (n == 0) {
                return 0;
            }
            long rank = Math.max(1, (long) (p / 100.0 * n + 0.5));
            long acc = 0;
            for (int i = 0; i < counts.length; i++) {
                acc += counts[i];
                if (acc >= rank) {
                    return Math.min(highest(i), mx);
                }
            }
            return mx;
        }

        String json() {
            if (n == 0) {
                return "{\"count\":0}";
            }
            String p9999 = n >= 1_000_000 ? "\"p99_99\":" + pct(99.99) + "," : "";
            return String.format("{\"count\":%d,\"min\":%d,\"p50\":%d,\"p90\":%d,\"p99\":%d,\"p99_9\":%d,%s\"max\":%d,\"mean\":%.2f}",
                    n, mn, pct(50), pct(90), pct(99), pct(99.9), p9999, mx, (double) sum / n);
        }
    }

    static FastBook.Stream read(Path p) throws IOException {
        try (FileChannel ch = FileChannel.open(p, StandardOpenOption.READ)) {
            ByteBuffer b = ch.map(FileChannel.MapMode.READ_ONLY, 0, ch.size()).order(ByteOrder.LITTLE_ENDIAN);
            byte[] magic = new byte[8];
            b.get(magic);
            if (!new String(magic, java.nio.charset.StandardCharsets.US_ASCII).equals("QFH9S001")) {
                throw new IOException("not a workload S file");
            }
            int nm = (int) b.getLong();
            int nl = (int) b.getLong();
            FastBook.Stream s = new FastBook.Stream(nm, nl);
            for (int k = 0; k < nm; k++) {
                s.type[k] = b.get();
                s.flags[k] = b.get();
                s.nBids[k] = b.getShort();
                s.nAsks[k] = b.getShort();
                s.kind[k] = b.getShort();
                s.checksum[k] = b.getInt() & 0xFFFFFFFFL;
                s.first[k] = b.getInt();
            }
            for (int k = 0; k < nl; k++) {
                s.px[k] = b.getLong();
                s.qty[k] = b.getLong();
            }
            return s;
        }
    }

    static long verify(FastBook.Stream s) {
        FastBook b = new FastBook(DEPTH);
        TreeMap<Long, Long> bids = new TreeMap<>();
        TreeMap<Long, Long> asks = new TreeMap<>();
        long[] px = new long[DEPTH];
        long[] q = new long[DEPTH];
        long checks = 0;
        long bad = 0;
        for (int i = 0; i < s.messages; i++) {
            b.apply(s, i);
            if (s.type[i] != FastBook.TRADE) {
                if (s.type[i] == FastBook.SNAPSHOT) {
                    bids.clear();
                    asks.clear();
                }
                int f = s.first[i];
                for (int k = f; k < f + s.nBids[i] + s.nAsks[i]; k++) {
                    TreeMap<Long, Long> side = k < f + s.nBids[i] ? bids : asks;
                    if (s.qty[k] != 0) {
                        side.put(s.px[k], s.qty[k]);
                    } else {
                        side.remove(s.px[k]);
                    }
                }
                while (bids.size() > DEPTH) {
                    bids.pollFirstEntry();
                }
                while (asks.size() > DEPTH) {
                    asks.pollLastEntry();
                }
            }
            if (i % 1000 == 999 || i + 1 == s.messages) {
                checks++;
                boolean same = true;
                for (boolean bid : new boolean[] {true, false}) {
                    var want = new ArrayList<>((bid ? bids.descendingMap() : asks).entrySet());
                    int n = b.top(bid, DEPTH, px, q);
                    same &= n == want.size();
                    for (int k = 0; same && k < n; k++) {
                        same = px[k] == want.get(k).getKey() && q[k] == want.get(k).getValue();
                    }
                }
                if (!same) {
                    bad++;
                }
            }
        }
        System.err.printf("correctness: %d checkpoints, %d mismatches; crossed %d, grows %d%n", checks, bad, b.crossed, b.grows());
        return bad;
    }

    static long gcCount() {
        long c = 0;
        for (var g : ManagementFactory.getGarbageCollectorMXBeans()) {
            c += Math.max(0, g.getCollectionCount());
        }
        return c;
    }

    static long allocatedBytes() {
        var mx = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        return mx.getCurrentThreadAllocatedBytes();
    }

    static volatile long sink;

    static String timedRun(FastBook.Stream s, long qseed) {
        Hist all = new Hist();
        Hist[] kinds = new Hist[KINDS.length];
        for (int k = 0; k < kinds.length; k++) {
            kinds[k] = new Hist();
        }
        Hist[] queries = new Hist[QUERIES.length];
        for (int k = 0; k < queries.length; k++) {
            queries[k] = new Hist();
        }
        Hist batch = new Hist();
        Hist[] qbatch = new Hist[QUERIES.length];
        for (int k = 0; k < qbatch.length; k++) {
            qbatch[k] = new Hist();
        }
        long[] ppx = new long[DEPTH];
        long[] pq = new long[DEPTH];
        Rng r = Rng.seeded(qseed, 0);
        long[] px = new long[DEPTH];
        long[] q = new long[DEPTH];
        FastBook b = new FastBook(DEPTH);
        for (int i = 0; i < WARMUP; i++) {
            b.apply(s, i);
        }
        long gc0 = gcCount();
        long bytes0 = allocatedBytes();
        for (int i = WARMUP; i < s.messages; i++) {
            long t0 = System.nanoTime();
            b.apply(s, i);
            long dt = System.nanoTime() - t0;
            all.record(dt);
            kinds[s.kind[i]].record(dt);
            if ((i - WARMUP) % 1000 == 999) {
                long a = System.nanoTime();
                sink = b.bestBidPx();
                queries[0].record(System.nanoTime() - a);
                a = System.nanoTime();
                sink = b.bestAskPx();
                queries[1].record(System.nanoTime() - a);
                boolean bid = (r.nextLong() & 1) != 0;
                int n = b.top(bid, DEPTH, px, q);
                long present = n > 0 ? px[(int) Long.remainderUnsigned(r.nextLong(), n)] : 0;
                long absent = b.hasBestAsk() ? b.bestAskPx() + 5 : 1;
                a = System.nanoTime();
                sink = b.qtyAt(bid, present);
                queries[2].record(System.nanoTime() - a);
                a = System.nanoTime();
                sink = b.qtyAt(true, absent);
                queries[3].record(System.nanoTime() - a);
                a = System.nanoTime();
                sink = b.top(bid, 10, px, q);
                queries[4].record(System.nanoTime() - a);
                a = System.nanoTime();
                sink = b.top(bid, 100, px, q);
                queries[5].record(System.nanoTime() - a);
                // HR-21 batch timing: each query 1,000 times in a row, total divided by 1,000; prices cycle so
                // no call repeats the previous one.
                long acc = 0;
                a = System.nanoTime();
                for (int j = 0; j < 1000; j++) {
                    acc += b.hasBestBid() ? b.bestBidQty() : 0;
                }
                qbatch[0].record((System.nanoTime() - a + 500) / 1000);
                a = System.nanoTime();
                for (int j = 0; j < 1000; j++) {
                    acc += b.hasBestAsk() ? b.bestAskQty() : 0;
                }
                qbatch[1].record((System.nanoTime() - a + 500) / 1000);
                int np = Math.max(1, b.top(bid, DEPTH, ppx, pq));
                a = System.nanoTime();
                for (int j = 0; j < 1000; j++) {
                    acc += b.qtyAt(bid, ppx[j % np]);
                }
                qbatch[2].record((System.nanoTime() - a + 500) / 1000);
                a = System.nanoTime();
                for (int j = 0; j < 1000; j++) {
                    acc += b.qtyAt(true, absent + j);
                }
                qbatch[3].record((System.nanoTime() - a + 500) / 1000);
                a = System.nanoTime();
                for (int j = 0; j < 1000; j++) {
                    acc += b.top(bid, 10, px, q) + q[0];
                }
                qbatch[4].record((System.nanoTime() - a + 500) / 1000);
                a = System.nanoTime();
                for (int j = 0; j < 1000; j++) {
                    acc += b.top(bid, 100, px, q) + q[99];
                }
                qbatch[5].record((System.nanoTime() - a + 500) / 1000);
                sink = acc;
            }
        }
        long bytes = allocatedBytes() - bytes0;
        long gcs = gcCount() - gc0;
        long fallbacks = b.indexFallbacks();
        FastBook c = new FastBook(DEPTH);
        for (int i = 0; i < WARMUP; i++) {
            c.apply(s, i);
        }
        long cb0 = allocatedBytes();
        for (int i = WARMUP; i + 1000 <= s.messages; i += 1000) {
            long t0 = System.nanoTime();
            for (int j = i; j < i + 1000; j++) {
                c.apply(s, j);
            }
            batch.record((System.nanoTime() - t0 + 500) / 1000);
        }
        long batchBytes = allocatedBytes() - cb0;
        System.err.printf("run: p50 %d p99 %d p99.9 %d ns, allocated bytes %d, gc %d%n", all.pct(50), all.pct(99), all.pct(99.9),
                bytes, gcs);
        StringBuilder o = new StringBuilder("{\"all\":").append(all.json()).append(",\"kinds\":{");
        for (int k = 0; k < KINDS.length; k++) {
            o.append(k > 0 ? "," : "").append('"').append(KINDS[k]).append("\":").append(kinds[k].json());
        }
        o.append("},\"queries\":{");
        for (int k = 0; k < QUERIES.length; k++) {
            o.append(k > 0 ? "," : "").append('"').append(QUERIES[k]).append("\":").append(queries[k].json());
        }
        o.append("},\"queries_batch_per_call\":{");
        for (int k = 0; k < QUERIES.length; k++) {
            o.append(k > 0 ? "," : "").append('"').append(QUERIES[k]).append("\":").append(qbatch[k].json());
        }
        return o.append("},\"batch_per_message\":").append(batch.json()).append(",\"allocated_bytes_measured\":").append(bytes)
                .append(",\"allocated_bytes_batch\":").append(batchBytes).append(",\"gc_count_measured\":").append(gcs)
                .append(",\"buffer_grows\":").append(b.grows()).append(",\"qty_at_index_fallbacks\":").append(fallbacks)
                .append('}').toString();
    }

    public static void main(String[] args) throws IOException {
        if (args.length < 1) {
            System.err.println("usage: LowLatBook <workload S file> [runs] [out.json]");
            System.exit(2);
        }
        FastBook.Stream s = read(Path.of(args[0]));
        int runs = args.length >= 2 ? Integer.parseInt(args[1]) : 5;
        long bad = verify(s);
        Hist clock = new Hist();
        for (int i = 0; i < 1_000_000; i++) {
            long a = System.nanoTime();
            clock.record(System.nanoTime() - a);
        }
        List<String> rs = new ArrayList<>();
        for (int k = 0; k < runs; k++) {
            rs.add(timedRun(s, SEED + 1 + k));
        }
        String out = "{\"workload\":\"S\",\"messages\":" + s.messages + ",\"warmup\":" + WARMUP + ",\"depth\":100,"
                + "\"alloc_method\":\"ThreadMXBean allocated bytes + GC count; JFR and -Xlog:gc alongside\","
                + "\"jvm\":\"" + System.getProperty("java.vm.name") + " " + System.getProperty("java.vm.version") + "\","
                + "\"jvm_args\":\"" + String.join(" ", ManagementFactory.getRuntimeMXBean().getInputArguments()).replace("\\", "/").replace("\"", "'") + "\","
                + "\"correctness_mismatches\":" + bad + ",\"clock_overhead\":" + clock.json() + ",\"runs\":[" + String.join(",", rs) + "]}\n";
        if (args.length >= 3) {
            Files.writeString(Path.of(args[2]), out);
        } else {
            System.out.print(out);
        }
        System.exit(bad == 0 ? 0 : 1);
    }
}
