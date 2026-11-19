package org.quantforge.micro;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * H-9 workload R2 and row L7 helpers ({@link FastBookFormA}; low-latency-book.md items 2a and 2b). Hand-built messages
 * only, no recorded rows: truncation to depth 100 inside {@link FastBook#apply}, the per-level sample, the form A
 * counts (checksums, rows matched at any message of their millisecond, below-10 and top-10 failures apart) and the
 * checkpoint file.
 */
class FastBookFormATest {
    /** Builds a stream from (type, nBids, nAsks, levels...) entries. */
    static final class Builder {
        final List<long[]> lv = new ArrayList<>();
        final List<int[]> msgs = new ArrayList<>();

        Builder msg(int type, int nb, int na, long... pxq) {
            msgs.add(new int[] {type, nb, na, lv.size()});
            for (int k = 0; k < pxq.length; k += 2) {
                lv.add(new long[] {pxq[k], pxq[k + 1]});
            }
            return this;
        }

        FastBook.Stream build() {
            FastBook.Stream s = new FastBook.Stream(msgs.size(), lv.size());
            for (int i = 0; i < msgs.size(); i++) {
                int[] m = msgs.get(i);
                s.type[i] = (byte) m[0];
                s.nBids[i] = (short) m[1];
                s.nAsks[i] = (short) m[2];
                s.kind[i] = (short) (m[0] == FastBook.TRADE ? 4 : 2);
                s.first[i] = m[3];
            }
            for (int k = 0; k < lv.size(); k++) {
                s.px[k] = lv.get(k)[0];
                s.qty[k] = lv.get(k)[1];
            }
            return s;
        }
    }

    static long[] side(long start, long step, long qty, int n, boolean qtyGrows) {
        long[] out = new long[2 * n];
        for (int k = 0; k < n; k++) {
            out[2 * k] = start + step * k;
            out[2 * k + 1] = qtyGrows ? 1 + k : qty;
        }
        return out;
    }

    static long[] concat(long[] a, long[] b) {
        long[] out = new long[a.length + b.length];
        System.arraycopy(a, 0, out, 0, a.length);
        System.arraycopy(b, 0, out, a.length, b.length);
        return out;
    }

    @Test
    void truncationTo100LevelsIsInsideApply() {
        FastBook.Stream s = new Builder()
                .msg(FastBook.SNAPSHOT, 100, 100, concat(side(10_000, -10, 0, 100, true), side(10_010, 10, 0, 100, true)))
                .msg(FastBook.UPDATE, 1, 0, 10_005, 7)
                .msg(FastBook.UPDATE, 1, 0, 5_000, 3)
                .build();
        FastBook b = new FastBook(100);
        b.apply(s, 0);
        b.apply(s, 1);
        assertEquals(1, b.truncatedLevels);
        long[] px = new long[100];
        long[] q = new long[100];
        assertEquals(100, b.top(true, 100, px, q));
        assertEquals(10_005, px[0]);
        assertEquals(10_000 - 10 * 98, px[99]);
        assertEquals(0, b.qtyAt(true, 9_010));
        long before = b.checksum();
        b.apply(s, 2); // beyond depth on the far side: inserted and truncated in the same apply
        assertEquals(2, b.truncatedLevels);
        assertEquals(before, b.checksum());
        assertEquals(0, b.grows());
    }

    @Test
    void perLevelSampleRoundsUp() {
        assertEquals(100, FastBookFormA.perLevelNs(100, 1));
        assertEquals(51, FastBookFormA.perLevelNs(101, 2));
        assertEquals(34, FastBookFormA.perLevelNs(100, 3));
        assertEquals(33, FastBookFormA.perLevelNs(99, 3));
        assertEquals(0, FastBookFormA.perLevelNs(0, 5));
        assertEquals(1, FastBookFormA.perLevelNs(1, 200));
    }

    @Test
    void formACountsChecksumsAndCheckpointClasses() throws IOException {
        // 0 snapshot (bids 100..89, asks 101..112, qty 5), 1 bid 100 -> 6, 2 trade, 3 bid 89 -> 9 (level 12), 4 bid 100 -> 7
        FastBook.Stream s = new Builder()
                .msg(FastBook.SNAPSHOT, 12, 12, concat(side(100, -1, 5, 12, false), side(101, 1, 5, 12, false)))
                .msg(FastBook.UPDATE, 1, 0, 100, 6)
                .msg(FastBook.TRADE, 1, 0, 101, 1)
                .msg(FastBook.UPDATE, 1, 0, 89, 9)
                .msg(FastBook.UPDATE, 1, 0, 100, 7)
                .build();
        FastBook ref = new FastBook(100);
        for (int i = 0; i < s.messages; i++) {
            ref.apply(s, i);
            if (s.type[i] != FastBook.TRADE) {
                s.flags[i] = (byte) FastBookFormA.FLAG_VENUE_CHECKSUM;
                s.checksum[i] = i == 3 ? ref.checksum() ^ 1L : ref.checksum();
            }
        }
        int[][] spec = {{0, 0, 0, 0}, {1, 0, 2, 0}, {4, 3, 4, 0}, {3, 3, 3, 1}, {4, 4, 4, 2}}; // after, lo, hi, tweak
        List<long[]> rows = new ArrayList<>();
        for (int[] r : spec) {
            FastBook b = new FastBook(100);
            for (int i = 0; i <= r[0]; i++) {
                b.apply(s, i);
            }
            long[] bp = new long[100];
            long[] bq = new long[100];
            long[] ap = new long[100];
            long[] aq = new long[100];
            int nb = b.top(true, 100, bp, bq);
            int na = b.top(false, 100, ap, aq);
            if (r[3] == 1) {
                bq[11]++;
            }
            if (r[3] == 2) {
                aq[0]++;
            }
            long[] row = new long[3 + 2 * (nb + na)];
            row[0] = r[1];
            row[1] = r[2];
            row[2] = ((long) nb << 16) | na;
            for (int k = 0; k < nb; k++) {
                row[3 + 2 * k] = bp[k];
                row[4 + 2 * k] = bq[k];
            }
            for (int k = 0; k < na; k++) {
                row[3 + 2 * (nb + k)] = ap[k];
                row[4 + 2 * (nb + k)] = aq[k];
            }
            rows.add(row);
        }
        Path p = Files.createTempFile("qf_formA", ".bin");
        try {
            Files.write(p, file(rows));
            FastBookFormA.Checkpoints c = FastBookFormA.read(p);
            assertEquals(5, c.rows());
            FastBookFormA.Counts n = FastBookFormA.verify(s, c, 100);
            assertEquals(4, n.checksumChecked);
            assertEquals(1, n.checksumFailed);
            assertEquals(5, n.checkpointChecked);
            assertEquals(1, n.failedTop10);
            assertEquals(1, n.failedBelow10);
            assertEquals(1, n.matchedAtLo);
            assertEquals(3, n.matchedAtHi);
            assertEquals(0, n.matchedOnlyInsideTie);
            assertEquals(2, n.rowsWithTie);
            assertTrue(n.json().startsWith("{\"checksum_checked\":4,\"checksum_failed\":1,"), n.json());
        } finally {
            Files.deleteIfExists(p);
        }
    }

    @Test
    void readRejectsAForeignFileAndABadRow() throws IOException {
        Path p = Files.createTempFile("qf_formA_bad", ".bin");
        try {
            Files.write(p, "NOTAFILE0000000000000000".getBytes(java.nio.charset.StandardCharsets.US_ASCII));
            assertThrows(IOException.class, () -> FastBookFormA.read(p));
            List<long[]> rows = new ArrayList<>();
            rows.add(new long[] {5, 4, (1L << 16) | 1, 100, 1, 101, 1}); // lo > hi
            Files.write(p, file(rows));
            assertThrows(IOException.class, () -> FastBookFormA.read(p));
        } finally {
            Files.deleteIfExists(p);
        }
    }

    /** rows: lo, hi, (nBids << 16 | nAsks), then price/qty pairs. */
    static byte[] file(List<long[]> rows) {
        int levels = 0;
        for (long[] r : rows) {
            levels += (r.length - 3) / 2;
        }
        ByteBuffer b = ByteBuffer.allocate(24 + 16 * rows.size() + 16 * levels).order(ByteOrder.LITTLE_ENDIAN);
        b.put("QFH9C001".getBytes(java.nio.charset.StandardCharsets.US_ASCII)).putLong(rows.size()).putLong(levels);
        int first = 0;
        for (long[] r : rows) {
            b.putInt((int) r[0]).putShort((short) (r[2] >> 16)).putShort((short) (r[2] & 0xFFFF)).putInt(first).putInt((int) r[1]);
            first += (r.length - 3) / 2;
        }
        for (long[] r : rows) {
            for (int k = 3; k < r.length; k++) {
                b.putLong(r[k]);
            }
        }
        return b.array();
    }
}
