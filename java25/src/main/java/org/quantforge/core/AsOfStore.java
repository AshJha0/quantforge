package org.quantforge.core;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Append-only log of versioned values and its views (asof-store.md). Pure functions of the log. */
public final class AsOfStore {
    private AsOfStore() {}

    /** {@code raw} is the record as given, which the chain hashes. Instants are epoch seconds. */
    public record Entry(long sequence, String seriesId, long eventTime, long knowledgeTime, Object value,
                        boolean deleted, Map<?, ?> raw) {}

    public record Chain(String head, List<String> hashes) {}

    private record Key(String seriesId, long eventTime) {}

    private static final String ZERO_HASH = "0".repeat(64);

    private static final Comparator<Entry> VIEW_ORDER = Comparator
            .<Entry, byte[]>comparing(e -> e.seriesId().getBytes(StandardCharsets.UTF_8), Arrays::compareUnsigned)
            .thenComparingLong(Entry::eventTime);

    public static void checkLog(List<Entry> log) {
        for (int i = 1; i < log.size(); i++) {
            if (log.get(i).sequence() <= log.get(i - 1).sequence()) {
                throw new QfError("E_INPUT", "sequence not strictly increasing", "records");
            }
        }
        for (int i = 1; i < log.size(); i++) {
            if (log.get(i).knowledgeTime() < log.get(i - 1).knowledgeTime()) {
                throw new QfError("E_INPUT", "knowledge_time runs backwards", "records");
            }
        }
    }

    /** The view at {@code asOf}, ordered by series then event time. */
    public static List<Entry> view(List<Entry> log, long asOf) {
        Map<Key, Entry> latest = new LinkedHashMap<>();
        for (Entry e : log) {
            if (e.knowledgeTime() <= asOf) {
                latest.put(new Key(e.seriesId(), e.eventTime()), e); // The log is in sequence order.
            }
        }
        List<Entry> rows = new ArrayList<>();
        for (Entry e : latest.values()) {
            if (!e.deleted()) {
                rows.add(e);
            }
        }
        rows.sort(VIEW_ORDER);
        return rows;
    }

    /** A row as a JSON object, with instants in Z form. */
    public static Map<String, Object> row(Entry e) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("series_id", e.seriesId());
        m.put("event_time", TimeZones.formatInstant(e.eventTime()));
        m.put("knowledge_time", TimeZones.formatInstant(e.knowledgeTime()));
        m.put("sequence", new Json.Number(e.sequence(), Long.toString(e.sequence())));
        m.put("value", e.value());
        return m;
    }

    public static SnapshotHash.Result snapshot(List<Entry> log, long asOf) {
        Map<String, Object> doc = new LinkedHashMap<>();
        doc.put("as_of", TimeZones.formatInstant(asOf));
        doc.put("rows", view(log, asOf).stream().map(AsOfStore::row).toList());
        return SnapshotHash.ofDocument(doc);
    }

    public static Chain chain(List<Entry> log) {
        try {
            String h = ZERO_HASH;
            List<String> hashes = new ArrayList<>(log.size());
            for (Entry e : log) {
                MessageDigest d = MessageDigest.getInstance("SHA-256");
                d.update(h.getBytes(StandardCharsets.UTF_8));
                d.update(SnapshotHash.canonical(e.raw()).getBytes(StandardCharsets.UTF_8));
                h = HexFormat.of().formatHex(d.digest());
                hashes.add(h);
            }
            return new Chain(h, hashes);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
