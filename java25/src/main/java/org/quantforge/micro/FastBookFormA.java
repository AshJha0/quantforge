package org.quantforge.micro;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Workload R2 and row L7 helpers for the H-9 harness ({@code specifications/09-microstructure/low-latency-book.md} items
 * 2a and 2b; {@code low-latency-targets.md} sections (g) and (h)). Everything here runs outside the timed region, except
 * {@link #perLevelNs}, which turns one measured apply time into the L7 sample after the clock has been read.
 *
 * <p>Checkpoint file (written by {@code benchmarks/h9/build_r2.py}): "QFH9C001", u64 rows, u64 levels; 16-byte rows (u32
 * lo, u16 bids, u16 asks, u32 first level, u32 hi), then levels (i64 price ticks, i64 lots), bids descending then asks
 * ascending. A row is compared after each message index in [lo, hi]: lo is the last book message received strictly
 * before the row's millisecond, hi the last one at or before it; the order inside one millisecond is not recorded, so
 * the row passes if it equals the book after one of them (ruling HR-132). Rows that do not match at lo would fail the
 * strict "before t" reading; that count is published as checkpoint_failed_strict_reading.
 */
public final class FastBookFormA {
    /** Venue checksum carried on a book message, checked outside the timed apply (not {@link FastBook#FLAG_CHECKSUM}). */
    public static final int FLAG_VENUE_CHECKSUM = 4;

    private FastBookFormA() {}

    /** The checkpoint rows and their levels as parallel arrays. */
    public static final class Checkpoints {
        public final int[] lo;
        public final int[] hi;
        public final int[] nBids;
        public final int[] nAsks;
        public final int[] first;
        public final long[] px;
        public final long[] qty;

        Checkpoints(int rows, int levels) {
            lo = new int[rows];
            hi = new int[rows];
            nBids = new int[rows];
            nAsks = new int[rows];
            first = new int[rows];
            px = new long[levels];
            qty = new long[levels];
        }

        public int rows() {
            return lo.length;
        }
    }

    /** Form A counts of low-latency-targets.md (g). */
    public static final class Counts {
        public long checksumChecked;
        public long checksumFailed;
        public long checkpointChecked;
        public long failedTop10;
        public long failedBelow10;
        public long matchedAtLo;
        public long matchedAtHi;
        public long matchedOnlyInsideTie;
        public long rowsWithTie;

        public String json() {
            return "{\"checksum_checked\":" + checksumChecked + ",\"checksum_failed\":" + checksumFailed
                    + ",\"checkpoint_checked\":" + checkpointChecked + ",\"checkpoint_failed_top10\":" + failedTop10
                    + ",\"checkpoint_failed_below10\":" + failedBelow10 + ",\"checkpoint_matched_at_lo\":" + matchedAtLo
                    + ",\"checkpoint_matched_at_hi\":" + matchedAtHi + ",\"checkpoint_matched_only_inside_tie\":"
                    + matchedOnlyInsideTie + ",\"checkpoint_rows_with_tie\":" + rowsWithTie
                    + ",\"checkpoint_failed_strict_reading\":" + (checkpointChecked - matchedAtLo) + "}";
        }
    }

    /** Reads a checkpoint file; IOException if it is not one or a row points outside the levels. */
    public static Checkpoints read(Path p) throws IOException {
        ByteBuffer b = ByteBuffer.wrap(Files.readAllBytes(p)).order(ByteOrder.LITTLE_ENDIAN);
        byte[] magic = new byte[8];
        b.get(magic);
        if (!new String(magic, StandardCharsets.US_ASCII).equals("QFH9C001")) {
            throw new IOException("not a checkpoint file");
        }
        int nr = (int) b.getLong();
        int nl = (int) b.getLong();
        Checkpoints c = new Checkpoints(nr, nl);
        for (int k = 0; k < nr; k++) {
            c.lo[k] = b.getInt();
            c.nBids[k] = Short.toUnsignedInt(b.getShort());
            c.nAsks[k] = Short.toUnsignedInt(b.getShort());
            c.first[k] = b.getInt();
            c.hi[k] = b.getInt();
            if (c.lo[k] > c.hi[k] || (long) c.first[k] + c.nBids[k] + c.nAsks[k] > nl) {
                throw new IOException("bad checkpoint row " + k);
            }
        }
        for (int k = 0; k < nl; k++) {
            c.px[k] = b.getLong();
            c.qty[k] = b.getLong();
        }
        return c;
    }

    /** L7 sample: apply time over the message's levels, rounded up to a whole nanosecond (item 2b); n &gt;= 1. */
    public static long perLevelNs(long dt, int n) {
        return (dt + n - 1) / n;
    }

    /**
     * 0: the book equals the row on all the row's levels; 1: the first 10 a side equal, a deeper level differs; 2: the
     * first 10 differ. Each side compares our best n levels with the row's n (micro.book.rebuild's checkpoint rule).
     */
    public static int compare(FastBook b, Checkpoints c, int row, long[] spx, long[] sq) {
        int worst = 0;
        int f = c.first[row];
        for (boolean bid : new boolean[] {true, false}) {
            int n = bid ? c.nBids[row] : c.nAsks[row];
            int off = bid ? f : f + c.nBids[row];
            int got = b.top(bid, n, spx, sq);
            int k10 = Math.min(10, n);
            if (got < k10) {
                return 2;
            }
            for (int k = 0; k < k10; k++) {
                if (spx[k] != c.px[off + k] || sq[k] != c.qty[off + k]) {
                    return 2;
                }
            }
            boolean all = got == n;
            for (int k = k10; all && k < n; k++) {
                all = spx[k] == c.px[off + k] && sq[k] == c.qty[off + k];
            }
            if (!all) {
                worst = 1;
            }
        }
        return worst;
    }

    /** One replay on a fresh book, outside any timing: venue checksums and every checkpoint row over its range. */
    public static Counts verify(FastBook.Stream s, Checkpoints c, int depth) {
        FastBook b = new FastBook(depth);
        Counts out = new Counts();
        long[] spx = new long[1024];
        long[] sq = new long[1024];
        int rows = c.rows();
        int[] best = new int[rows];
        java.util.Arrays.fill(best, 3);
        boolean[] atLo = new boolean[rows];
        boolean[] atHi = new boolean[rows];
        int next = 0;
        List<Integer> live = new ArrayList<>();
        for (int i = 0; i < s.messages; i++) {
            b.apply(s, i);
            if (s.type[i] != FastBook.TRADE && (s.flags[i] & FLAG_VENUE_CHECKSUM) != 0) {
                out.checksumChecked++;
                if (b.checksum() != s.checksum[i]) {
                    out.checksumFailed++;
                }
            }
            while (next < rows && c.lo[next] <= i) {
                live.add(next++);
            }
            for (int k = 0; k < live.size();) {
                int j = live.get(k);
                int res = compare(b, c, j, spx, sq);
                best[j] = Math.min(best[j], res);
                if (res == 0 && i == c.lo[j]) {
                    atLo[j] = true;
                }
                if (res == 0 && i == c.hi[j]) {
                    atHi[j] = true;
                }
                if (i >= c.hi[j]) {
                    live.set(k, live.get(live.size() - 1));
                    live.remove(live.size() - 1);
                } else {
                    k++;
                }
            }
        }
        for (int j = 0; j < rows; j++) {
            out.checkpointChecked++;
            if (c.hi[j] > c.lo[j]) {
                out.rowsWithTie++;
            }
            if (best[j] == 0) {
                out.matchedAtLo += atLo[j] ? 1 : 0;
                out.matchedAtHi += atHi[j] ? 1 : 0;
                out.matchedOnlyInsideTie += !atLo[j] && !atHi[j] ? 1 : 0;
            } else if (best[j] == 1) {
                out.failedBelow10++;
            } else {
                out.failedTop10++;
            }
        }
        return out;
    }
}
