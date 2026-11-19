package org.quantforge.cli;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Json;
import org.quantforge.core.QfError;
import org.quantforge.core.TimeZones;
import org.quantforge.risk.StageK;

/**
 * Stage K wave 1 verbs (PROPOSED rulings KR-1 to KR-14), as {@code python/quantforge_core/cli/ops_stage_k.py}.
 *
 * <p>Error order HR-66: reading the inputs is E_SCHEMA; the structural E_INPUT checks run here, before the held
 * non-finite read (F-2) is raised; the core then applies E_DOMAIN, value-dependent E_INPUT and E_LIMIT. The stage K
 * sizes are checked in the core, last, so the general per-array limit is skipped for these verbs.
 */
final class OpsStageK {
    private OpsStageK() {}

    static final Set<String> OPERATIONS = Set.of("core.store.bitemporal_query", "curve.bootstrap.par_annual",
            "curve.incremental.update", "calib.trigger.check", "risk.intraday.delta_gamma_bound",
            "num.richardson.check");

    static void register(Map<String, Function<In, Out>> table) {
        table.put("core.store.bitemporal_query", OpsStageK::bitemporal);
        table.put("curve.bootstrap.par_annual", OpsStageK::parAnnual);
        table.put("curve.incremental.update", OpsStageK::incremental);
        table.put("calib.trigger.check", OpsStageK::trigger);
        table.put("risk.intraday.delta_gamma_bound", OpsStageK::intraday);
        table.put("num.richardson.check", OpsStageK::richardson);
    }

    /** Runs a structural check; its E_INPUT outranks a held non-finite read (HR-66). Then raises that read. */
    private static void structural(In in, Runnable check) {
        try {
            check.run();
        } catch (QfError e) {
            throw in.structural(e);
        }
        in.gate();
    }

    private static QfError schema(String message) {
        return new QfError("E_SCHEMA", message, "records");
    }

    private static List<?> array(In in, String key) {
        if (in.anyValue(key) instanceof List<?> l) {
            return l;
        }
        throw new QfError("E_SCHEMA", key + ": expected an array", key);
    }

    private static StageK.BiRecord record(Object raw, In parent) {
        if (!(raw instanceof Map<?, ?> m)) {
            throw schema("a record is not an object");
        }
        if (!m.containsKey("value") || !m.containsKey("valid_to")) {
            throw schema("a record has no value or no valid_to");
        }
        In r = parent.wrap(m);
        long sequence = r.integer("sequence");
        String seriesId = r.string("series_id");
        if (sequence < 1 || seriesId.isEmpty() || Json.hasLoneSurrogate(m)) {
            throw schema("bad sequence, series_id or string in a record");
        }
        long validFrom = r.instant("valid_from");
        Long validTo = r.has("valid_to") ? r.instant("valid_to") : null;
        long knowledge = r.instant("knowledge_time");
        Object value = m.get("value");
        if (In.isNonFiniteToken(value)) {
            value = r.real("value"); // ruling F-38: a top-level token is a Real, held for the finite rule
        }
        return new StageK.BiRecord(sequence, seriesId, validFrom, validTo, knowledge, value,
                r.bool("deleted", false));
    }

    private static Out bitemporal(In in) {
        List<StageK.BiRecord> log = new ArrayList<>();
        for (Object raw : array(in, "records")) {
            log.add(record(raw, in));
        }
        String seriesId = in.string("series_id");
        long k = in.instant("knowledge_as_of");
        long v = in.instant("valid_at");
        structural(in, () -> StageK.checkLog(log));
        StageK.Answer a = StageK.bitemporalQuery(log, seriesId, k, v);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("status", a.status());
        if (a.row() == null) {
            out.put("row", null);
        } else {
            StageK.BiRecord w = a.row();
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("sequence", w.sequence());
            row.put("valid_from", TimeZones.formatInstant(w.validFrom()));
            row.put("valid_to", w.validTo() == null ? null : TimeZones.formatInstant(w.validTo()));
            row.put("knowledge_time", TimeZones.formatInstant(w.knowledgeTime()));
            row.put("value", w.value());
            out.put("row", row);
        }
        return new Out(out, Map.of());
    }

    private static Out parAnnual(In in) {
        double[] quotes = in.reals("quotes");
        structural(in, () -> StageK.checkQuotesShape(quotes.length));
        return Operations.out("discount_factors", StageK.parAnnual(quotes));
    }

    private static Out incremental(In in) {
        double[] pq = in.reals("previous_quotes");
        double[] pd = in.reals("previous_discount_factors");
        double[] nq = in.reals("new_quotes");
        structural(in, () -> StageK.checkUpdateShape(pq.length, pd.length, nq.length));
        StageK.Update u = StageK.incrementalUpdate(pq, pd, nq);
        return Operations.out("discount_factors", u.discountFactors(), "first_changed_index",
                u.firstChangedIndex(), "recomputed", u.recomputed());
    }

    private static Out trigger(In in) {
        double[] changes = in.reals("changes");
        double xRef = in.real("x_ref");
        double xNow = in.real("x_now");
        double d = in.real("days_since");
        double k = in.real("k");
        structural(in, () -> StageK.checkChangesShape(changes.length));
        StageK.Trigger t = StageK.triggerCheck(changes, xRef, xNow, d, k);
        return Operations.out("fire", t.fire(), "sigma", t.sigma(), "threshold", t.threshold(), "false_alarm_rate",
                t.falseAlarmRate());
    }

    private static Out intraday(In in) {
        List<StageK.ZeroPosition> positions = new ArrayList<>();
        for (In p : in.objects("positions")) {
            positions.add(new StageK.ZeroPosition(p.real("notional"), p.real("maturity"), p.real("yield")));
        }
        double shift = in.real("shift");
        structural(in, () -> StageK.checkPositionsShape(positions.size()));
        StageK.Intraday r = StageK.deltaGammaBound(positions, shift);
        return Operations.out("estimate_pnl", r.estimatePnl(), "bound", r.bound(), "label", r.label());
    }

    private static Out richardson(In in) {
        double[] values = in.reals("values");
        double ratio = in.real("ratio");
        double p = in.real("assumed_order");
        structural(in, () -> StageK.checkValuesShape(values.length));
        return new Out(StageK.richardsonCheck(values, ratio, p).toMap(), Map.of());
    }
}
