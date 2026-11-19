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
 * <p>Error order HR-122 (ruling KR-230): reading the inputs is E_SCHEMA; the gate then raises a held size limit
 * (limits.md, KR-231: the generic 100,000 per array, 200 for the quote lists here) and then a held non-finite read
 * (F-2); the core applies structural E_INPUT, E_DOMAIN and, for the incremental update, the stale-cache E_INPUT.
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
        in.gate();
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
        in.limit(quotes.length > StageK.MAX_QUOTES, "quotes");
        in.gate();
        return Operations.out("discount_factors", StageK.parAnnual(quotes));
    }

    private static Out incremental(In in) {
        double[] pq = in.reals("previous_quotes");
        double[] pd = in.reals("previous_discount_factors");
        double[] nq = in.reals("new_quotes");
        in.limit(pq.length > StageK.MAX_QUOTES, "previous_quotes");
        in.limit(pd.length > StageK.MAX_QUOTES, "previous_discount_factors");
        in.limit(nq.length > StageK.MAX_QUOTES, "new_quotes");
        in.gate();
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
        in.gate();
        StageK.Trigger t = StageK.triggerCheck(changes, xRef, xNow, d, k);
        return Operations.out("fire", t.fire(), "sigma", t.sigma(), "threshold", t.threshold(), "false_alarm_rate",
                t.falseAlarmRate(), "nominal_rate", t.nominalRate());
    }

    private static Out intraday(In in) {
        List<StageK.ZeroPosition> positions = new ArrayList<>();
        for (In p : in.objects("positions")) {
            positions.add(new StageK.ZeroPosition(p.real("notional"), p.real("maturity"), p.real("yield")));
        }
        double shift = in.real("shift");
        in.gate();
        StageK.Intraday r = StageK.deltaGammaBound(positions, shift);
        return Operations.out("estimate_pnl", r.estimatePnl(), "bound", r.bound(), "label", r.label());
    }

    private static Out richardson(In in) {
        double[] values = in.reals("values");
        double ratio = in.real("ratio");
        double p = in.real("assumed_order");
        in.gate();
        return new Out(StageK.richardsonCheck(values, ratio, p).toMap(), Map.of());
    }
}
