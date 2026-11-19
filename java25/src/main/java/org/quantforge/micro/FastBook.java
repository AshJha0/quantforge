package org.quantforge.micro;

import java.util.Arrays;

/**
 * H-9 low-latency MBP book ({@code specifications/09-microstructure/low-latency-book.md}, rulings HR-18 to HR-24): the
 * same operation as {@link OrderBook#rebuild} built for speed, mirroring the C++ and Rust ports. Prices are integer
 * ticks and quantities integer lots (HR-20); every array is sized at construction and {@link #apply} and the
 * queries allocate nothing. The one stated exception: a single message carrying more levels than a side's spare
 * capacity (about 7 x depth) grows the arrays, counted in {@link #grows()}.
 *
 * <p>Each side is a sorted pair of arrays (key, qty), best level at the high end, key = price for bids and -price
 * for asks. Truncation moves one index; inserts and deletes near the touch shift only the levels between the price
 * and the touch (HR-19). {@code qtyAt} reads a direct-mapped index on the price grid (slot = price mod 1024 ticks)
 * and falls back to the sorted search only when two present prices share a slot (counted). The top of book is
 * cached at the end of every {@code apply}.
 */
public final class FastBook {
    public static final int SNAPSHOT = 0;
    public static final int UPDATE = 1;
    public static final int GAP = 2;
    public static final int TRADE = 3;
    public static final int FLAG_CHECKSUM = 1;
    public static final int FLAG_RESUBSCRIBE = 2;
    public static final int MAX_EVENTS = 10_000;
    public static final int EV_CHECKSUM_FAIL = 0;
    public static final int EV_CROSSED = 1;
    public static final int EV_LOCKED = 2;
    public static final int EV_GAP = 3;
    public static final int EV_UPDATE_BEFORE_SNAPSHOT = 4;
    public static final long NO_PX = Long.MIN_VALUE;
    private static final String[] EVENT_NAMES = {"CHECKSUM_FAIL", "CROSSED", "LOCKED", "GAP", "UPDATE_BEFORE_SNAPSHOT"};

    /**
     * A pre-decoded stream as parallel arrays: per message type, flags, bid and ask level counts, checksum (u32 in a
     * long), first level index and a free {@code kind} tag; per level price ticks and quantity lots, bids first.
     */
    public static final class Stream {
        public byte[] type;
        public byte[] flags;
        public short[] nBids;
        public short[] nAsks;
        public short[] kind;
        public long[] checksum;
        public int[] first;
        public long[] px;
        public long[] qty;
        public int messages;

        public Stream(int messages, int levels) {
            this.messages = messages;
            type = new byte[messages];
            flags = new byte[messages];
            nBids = new short[messages];
            nAsks = new short[messages];
            kind = new short[messages];
            checksum = new long[messages];
            first = new int[messages];
            px = new long[levels];
            qty = new long[levels];
        }
    }

    /** Counters of {@code order-book.md} (checkpoint counters stay with the caller) plus {@code trades}. */
    public long messages, snapshots, updates, levelChanges, deletesOfAbsentLevel, truncatedLevels, checksumChecked,
            checksumFailed, crossed, locked, gaps, resyncs, trades;

    private static final int SLOTS = 1024;

    /** One side; see the class note. */
    private static final class Side {
        final boolean bid;
        long[] key;
        long[] q;
        int lo;
        int hi;
        final long[] slotPx = new long[SLOTS];
        final long[] slotQty = new long[SLOTS];
        final int[] slotN = new int[SLOTS];
        long grows;
        long far;
        long fallbacks;

        Side(boolean bid, int cap) {
            this.bid = bid;
            key = new long[cap];
            q = new long[cap];
            lo = hi = cap / 2;
            Arrays.fill(slotPx, NO_PX);
        }

        int size() {
            return hi - lo;
        }

        long toKey(long px) {
            return bid ? px : -px;
        }

        static int slot(long px) {
            return (int) (px & (SLOTS - 1));
        }

        void unindex(long px) {
            int s = slot(px);
            if (--slotN[s] == 0 || slotPx[s] == px) {
                slotPx[s] = NO_PX;
            }
        }

        void clear() {
            for (int k = lo; k < hi; k++) {
                unindex(bid ? key[k] : -key[k]);
            }
            lo = hi = key.length / 2;
        }

        int lowerBound(long k) {
            int j = hi;
            int stop = hi - Math.min(8, hi - lo);
            while (j > stop && key[j - 1] >= k) {
                j--;
            }
            if (j == lo || key[j - 1] < k) {
                return j;
            }
            far++;
            int a = lo;
            int z = j - 1;
            while (a < z) {
                int mid = (a + z) >>> 1;
                if (key[mid] < k) {
                    a = mid + 1;
                } else {
                    z = mid;
                }
            }
            return a;
        }

        long qtyAt(long px) {
            int s = slot(px);
            if (slotN[s] == 0) {
                return 0;
            }
            if (slotPx[s] == px) {
                return slotQty[s];
            }
            fallbacks++;
            long k = toKey(px);
            int pos = lowerBound(k);
            return pos < hi && key[pos] == k ? q[pos] : 0;
        }

        int recenter(int pos) {
            int n = size();
            if (n + 2 > key.length) {
                grows++;
                int cap = key.length * 2;
                long[] nk = new long[cap];
                long[] nq = new long[cap];
                int nlo = (cap - n) / 2;
                System.arraycopy(key, lo, nk, nlo, n);
                System.arraycopy(q, lo, nq, nlo, n);
                key = nk;
                q = nq;
                int p = pos - lo + nlo;
                lo = nlo;
                hi = nlo + n;
                return p;
            }
            int nlo = (key.length - n) / 2;
            System.arraycopy(key, lo, key, nlo, n);
            System.arraycopy(q, lo, q, nlo, n);
            int p = pos - lo + nlo;
            lo = nlo;
            hi = nlo + n;
            return p;
        }

        void set(long px, long qty) {
            long k = toKey(px);
            int pos = lowerBound(k);
            int s = slot(px);
            if (pos < hi && key[pos] == k) {
                q[pos] = qty;
                if (slotPx[s] == px) {
                    slotQty[s] = qty;
                }
                return;
            }
            if (slotN[s]++ == 0 || slotPx[s] == NO_PX) {
                slotPx[s] = px;
                slotQty[s] = qty;
            }
            if (lo == 0 || hi == key.length) {
                pos = recenter(pos);
            }
            if (hi - pos <= pos - lo) {
                System.arraycopy(key, pos, key, pos + 1, hi - pos);
                System.arraycopy(q, pos, q, pos + 1, hi - pos);
                hi++;
            } else {
                System.arraycopy(key, lo, key, lo - 1, pos - lo);
                System.arraycopy(q, lo, q, lo - 1, pos - lo);
                lo--;
                pos--;
            }
            key[pos] = k;
            q[pos] = qty;
        }

        boolean erase(long px) {
            long k = toKey(px);
            int pos = lowerBound(k);
            if (pos >= hi || key[pos] != k) {
                return false;
            }
            unindex(px);
            if (hi - pos - 1 <= pos - lo) {
                System.arraycopy(key, pos + 1, key, pos, hi - pos - 1);
                System.arraycopy(q, pos + 1, q, pos, hi - pos - 1);
                hi--;
            } else {
                System.arraycopy(key, lo, key, lo + 1, pos - lo);
                System.arraycopy(q, lo, q, lo + 1, pos - lo);
                lo++;
            }
            return true;
        }

        long truncate(int depth) {
            int n = size();
            if (n <= depth) {
                return 0;
            }
            for (int k = lo; k < lo + (n - depth); k++) {
                unindex(bid ? key[k] : -key[k]);
            }
            lo += n - depth;
            return n - depth;
        }

        int top(int n, long[] outPx, long[] outQty) {
            int m = Math.min(n, size());
            for (int k = 0; k < m; k++) {
                long kk = key[hi - 1 - k];
                outPx[k] = bid ? kk : -kk;
                outQty[k] = q[hi - 1 - k];
            }
            return m;
        }
    }

    private final int depth;
    private final Side bids;
    private final Side asks;
    private boolean live;
    private boolean pendingResync;
    private long seq;
    private long omitted;
    private final long[] eventI = new long[MAX_EVENTS];
    private final byte[] eventKind = new byte[MAX_EVENTS];
    private int nEvents;
    private boolean hasBid;
    private boolean hasAsk;
    private long bidPx, bidQty, askPx, askQty;
    private final long[] csPx = new long[10];
    private final long[] csQty = new long[10];
    private final byte[] csBuf = new byte[800];
    private final byte[] digits = new byte[20];

    public FastBook(int depth) {
        this.depth = depth;
        int cap = 8 * depth + 64;
        bids = new Side(true, cap);
        asks = new Side(false, cap);
    }

    private void event(long i, int kind) {
        if (nEvents < MAX_EVENTS) {
            eventI[nEvents] = i;
            eventKind[nEvents++] = (byte) kind;
        } else {
            omitted++;
        }
    }

    /** Applies message {@code i} of {@code s}. */
    public void apply(Stream s, int i) {
        applyBook(s, i);
        hasBid = bids.size() > 0;
        if (hasBid) {
            bidPx = bids.key[bids.hi - 1];
            bidQty = bids.q[bids.hi - 1];
        }
        hasAsk = asks.size() > 0;
        if (hasAsk) {
            askPx = -asks.key[asks.hi - 1];
            askQty = asks.q[asks.hi - 1];
        }
    }

    private void applyBook(Stream s, int m) {
        int type = s.type[m];
        if (type == TRADE) {
            trades++;
            return;
        }
        if (type == GAP) {
            gaps++;
            bids.clear();
            asks.clear();
            live = false;
            event(seq++, EV_GAP);
            return;
        }
        long i = seq++;
        messages++;
        int f = s.first[m];
        int nb = s.nBids[m];
        int na = s.nAsks[m];
        if (type == SNAPSHOT) {
            snapshots++;
            if ((s.flags[m] & FLAG_RESUBSCRIBE) != 0 && pendingResync) {
                resyncs++;
            }
            pendingResync = false;
            bids.clear();
            asks.clear();
            for (int k = f; k < f + nb; k++) {
                if (s.qty[k] != 0) {
                    bids.set(s.px[k], s.qty[k]);
                }
            }
            for (int k = f + nb; k < f + nb + na; k++) {
                if (s.qty[k] != 0) {
                    asks.set(s.px[k], s.qty[k]);
                }
            }
            live = true;
        } else {
            updates++;
            if (!live) {
                event(i, EV_UPDATE_BEFORE_SNAPSHOT);
                return;
            }
            updateSide(bids, s, f, nb);
            updateSide(asks, s, f + nb, na);
        }
        truncatedLevels += bids.truncate(depth) + asks.truncate(depth);
        if ((s.flags[m] & FLAG_CHECKSUM) != 0) {
            checksumChecked++;
            if (checksum() != s.checksum[m]) {
                checksumFailed++;
                pendingResync = true;
                event(i, EV_CHECKSUM_FAIL);
            }
        }
        if (bids.size() > 0 && asks.size() > 0) {
            long b = bids.key[bids.hi - 1];
            long a = -asks.key[asks.hi - 1];
            if (a < b) {
                crossed++;
                event(i, EV_CROSSED);
            } else if (a == b) {
                locked++;
                event(i, EV_LOCKED);
            }
        }
    }

    private void updateSide(Side side, Stream s, int from, int n) {
        for (int k = from; k < from + n; k++) {
            levelChanges++;
            if (s.qty[k] == 0) {
                if (!side.erase(s.px[k])) {
                    deletesOfAbsentLevel++;
                }
            } else {
                side.set(s.px[k], s.qty[k]);
            }
        }
    }

    public boolean hasBestBid() {
        return hasBid;
    }

    public boolean hasBestAsk() {
        return hasAsk;
    }

    /** Best bid price; meaningful only when {@link #hasBestBid()} (the empty marker is {@code false}). */
    public long bestBidPx() {
        return bidPx;
    }

    public long bestBidQty() {
        return bidQty;
    }

    public long bestAskPx() {
        return askPx;
    }

    public long bestAskQty() {
        return askQty;
    }

    public long qtyAt(boolean bid, long px) {
        return bid ? bids.qtyAt(px) : asks.qtyAt(px);
    }

    /** The best n levels of one side into the caller's arrays; returns how many were written. */
    public int top(boolean bid, int n, long[] outPx, long[] outQty) {
        return bid ? bids.top(n, outPx, outQty) : asks.top(n, outPx, outQty);
    }

    private int putDigits(int at, long v) {
        int n = 0;
        long u = v;
        do {
            digits[n++] = (byte) ('0' + u % 10);
            u /= 10;
        } while (u != 0);
        for (int k = 0; k < n; k++) {
            csBuf[at + k] = digits[n - 1 - k];
        }
        return n;
    }

    /** [KR-CRC] CRC32 of the top 10 asks then the top 10 bids; no allocation. */
    public long checksum() {
        int n = 0;
        for (int side = 0; side < 2; side++) {
            int m = top(side == 1, 10, csPx, csQty);
            for (int k = 0; k < m; k++) {
                n += putDigits(n, csPx[k]);
                n += putDigits(n, csQty[k]);
            }
        }
        int c = 0xFFFFFFFF;
        for (int k = 0; k < n; k++) {
            c = CRC[(c ^ csBuf[k]) & 0xFF] ^ (c >>> 8);
        }
        return (c ^ 0xFFFFFFFFL) & 0xFFFFFFFFL;
    }

    private static final int[] CRC = new int[256];

    static {
        for (int n = 0; n < 256; n++) {
            int c = n;
            for (int k = 0; k < 8; k++) {
                c = (c & 1) != 0 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
            }
            CRC[n] = c;
        }
    }

    public int depth() {
        return depth;
    }

    public int eventCount() {
        return nEvents;
    }

    public long eventIndex(int k) {
        return eventI[k];
    }

    public String eventName(int k) {
        return EVENT_NAMES[eventKind[k]];
    }

    public long eventsOmitted() {
        return omitted;
    }

    public long grows() {
        return bids.grows + asks.grows;
    }

    public long farLookups() {
        return bids.far + asks.far;
    }

    public long indexFallbacks() {
        return bids.fallbacks + asks.fallbacks;
    }
}
