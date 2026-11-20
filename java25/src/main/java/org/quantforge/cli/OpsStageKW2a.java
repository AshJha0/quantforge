package org.quantforge.cli;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.regex.Pattern;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.risk.FrtbDrc;
import org.quantforge.risk.FrtbIma;

/**
 * Stage K wave 2 lane A verbs: FRTB DRC and RRAO (K-8a, frtb-drc-rrao.md) and FRTB IMA (K-8f, frtb-ima.md). A port of
 * python/quantforge_core/cli/ops_k_w2a.py and limits_k_w2a.py. Every input is read first (E_SCHEMA, enum values
 * included), then the gate raises a held E_LIMIT and then the finite rule, and the core checks structure (E_INPUT)
 * before domain (E_DOMAIN): error order KR-67 (= HR-122). Registered by the coordinator at integration
 * (program/STAGE_K_W2A_JAVA_HANDOVER.md).
 */
final class OpsStageKW2a {
    private OpsStageKW2a() {}

    /** The two verbs whose P&amp;L lists may hold 1,000,000 points (KR-67): the general per-array limit is skipped. */
    static final Set<String> PAGE_LIMITED = Set.of("risk.frtb.pla", "risk.frtb.ima.es_lh");

    private static final List<String> RATINGS = FrtbDrc.RATINGS;
    private static final List<String> ZONES = List.of("GREEN", "AMBER");
    private static final List<String> ROWS = List.of("A", "B", "C", "D");
    private static final Pattern FX = Pattern.compile("[A-Z]{3}/[A-Z]{3}");

    /** A string from a fixed list; a value outside the list is E_SCHEMA. */
    static String choice(In in, String key, List<String> allowed) {
        String s = in.string(key);
        if (!allowed.contains(s)) {
            throw new QfError("E_SCHEMA", key + ": " + s + " is not listed", key);
        }
        return s;
    }

    private static Map<String, Object> row(Object... keysAndValues) {
        return Operations.out(keysAndValues).outputs();
    }

    private static List<Object> buckets(List<FrtbDrc.BucketRow> rows, boolean hbr) {
        List<Object> out = new ArrayList<>();
        for (FrtbDrc.BucketRow b : rows) {
            out.add(hbr ? row("bucket", b.bucket(), "hbr", b.hbr(), "wtd_long", b.wtdLong(), "wtd_short",
                    b.wtdShort(), "drc", b.drc())
                    : row("bucket", b.bucket(), "wtd_long", b.wtdLong(), "wtd_short", b.wtdShort(), "drc", b.drc()));
        }
        return out;
    }

    private static List<Object> weightRows(List<FrtbDrc.WeightRow> rows) {
        List<Object> out = new ArrayList<>();
        for (FrtbDrc.WeightRow r : rows) {
            out.add(row("id", r.id(), "weight", r.weight(), "scaled_jtd", r.scaledJtd()));
        }
        return out;
    }

    static Out drcNonsec(In in) {
        List<FrtbDrc.Position> positions = new ArrayList<>();
        for (In p : in.objects("positions")) {
            positions.add(new FrtbDrc.Position(p.string("id"), p.string("obligor"),
                    choice(p, "bucket", FrtbDrc.BUCKETS), choice(p, "seniority", FrtbDrc.SENIORITIES),
                    p.real("notional"), p.real("market_value"), p.real("maturity_years"), p.bool("cash_equity", false),
                    p.bool("lgd_applies", true)));
        }
        In r = in.object("ratings");
        Map<String, String> ratings = new LinkedHashMap<>();
        for (String name : r.keys()) {
            ratings.put(name, choice(r, name, RATINGS));
        }
        in.gate();
        FrtbDrc.NonsecResult res = FrtbDrc.drcNonsec(positions, ratings);
        List<Object> rows = new ArrayList<>();
        for (FrtbDrc.JtdRow j : res.positions()) {
            rows.add(row("id", j.id(), "gross_jtd", j.grossJtd(), "weight", j.weight(), "scaled_jtd", j.scaledJtd()));
        }
        List<Object> obligors = new ArrayList<>();
        for (FrtbDrc.ObligorRow o : res.obligors()) {
            obligors.add(row("obligor", o.obligor(), "net_long", o.netLong(), "net_short", o.netShort(), "rw", o.rw()));
        }
        return Operations.out("positions", rows, "obligors", obligors, "buckets", buckets(res.buckets(), true), "drc",
                res.drc(), "label", FrtbDrc.LABEL);
    }

    static Out drcSecNonctp(In in) {
        List<FrtbDrc.SecPosition> positions = new ArrayList<>();
        for (In p : in.objects("positions")) {
            positions.add(new FrtbDrc.SecPosition(p.string("id"), p.string("bucket"), p.string("pool"),
                    p.string("tranche"), p.real("market_value"), p.real("maturity_years"), p.real("rw")));
        }
        in.gate();
        FrtbDrc.SecResult res = FrtbDrc.drcSecNonctp(positions);
        return Operations.out("positions", weightRows(res.positions()), "buckets", buckets(res.buckets(), true), "drc",
                res.drc(), "label", FrtbDrc.LABEL, "rw_source", FrtbDrc.RW_SOURCE);
    }

    static Out drcCtp(In in) {
        List<FrtbDrc.CtpPosition> positions = null;
        if (in.has("positions")) {
            positions = new ArrayList<>();
            for (In p : in.objects("positions")) {
                positions.add(new FrtbDrc.CtpPosition(p.string("id"), p.string("index"), p.string("series"),
                        p.string("tranche"), p.real("market_value"), p.real("maturity_years"), p.real("rw")));
            }
        }
        double[] bucketDrc = in.has("bucket_drc") ? in.reals("bucket_drc") : null;
        in.gate();
        FrtbDrc.CtpResult res = FrtbDrc.drcCtp(positions, bucketDrc);
        if (res.positions() == null) {
            return Operations.out("drc", res.drc(), "label", FrtbDrc.LABEL, "rw_source", FrtbDrc.RW_SOURCE);
        }
        return Operations.out("positions", weightRows(res.positions()), "hbr_ctp", res.hbrCtp(), "buckets",
                buckets(res.buckets(), false), "drc", res.drc(), "label", FrtbDrc.LABEL, "rw_source",
                FrtbDrc.RW_SOURCE);
    }

    static Out rrao(In in) {
        List<FrtbDrc.Instrument> instruments = new ArrayList<>();
        for (In x : in.objects("instruments")) {
            instruments.add(new FrtbDrc.Instrument(x.string("id"), x.real("gross_notional"),
                    choice(x, "kind", FrtbDrc.KINDS), x.bool("listed_or_clearable"), x.bool("back_to_back")));
        }
        in.gate();
        FrtbDrc.RraoResult res = FrtbDrc.rrao(instruments);
        List<Object> rows = new ArrayList<>();
        for (FrtbDrc.RraoRow r : res.instruments()) {
            rows.add(row("id", r.id(), "weight", r.weight(), "excluded", r.excluded(), "addon", r.addon()));
        }
        return Operations.out("instruments", rows, "rrao", res.rrao(), "label", FrtbDrc.LABEL);
    }

    static Out pla(In in) {
        double[] hpl = in.reals("hpl");
        double[] rtpl = in.reals("rtpl");
        in.limit(hpl.length > FrtbIma.MAX_PNL, "hpl"); // KR-67
        in.limit(rtpl.length > FrtbIma.MAX_PNL, "rtpl");
        in.gate();
        FrtbIma.Pla p = FrtbIma.pla(hpl, rtpl);
        return Operations.out("n", p.n(), "spearman", p.spearman(), "ks", p.ks(), "ks_count", p.ksCount(), "zone",
                p.zone(), "ks_pvalue_asymptotic", p.ksPvalueAsymptotic(), "regulatory_window", p.regulatoryWindow(),
                "label", FrtbIma.LABEL);
    }

    static Out plaKsPvalue(In in) {
        double ks = in.real("ks");
        long n = in.integer("n");
        in.gate();
        return Operations.out("pvalue", FrtbIma.plaKsPvalue(ks, n), "label", FrtbIma.LABEL);
    }

    static Out lh(In in) {
        String category = in.has("category") ? choice(in, "category", FrtbIma.LH_CATEGORIES) : null;
        String fxPair = null;
        if (in.has("fx_pair")) {
            fxPair = in.string("fx_pair");
            if (!FX.matcher(fxPair).matches()) {
                throw new QfError("E_SCHEMA", "fx_pair: not of the form AAA/BBB", "fx_pair");
            }
        }
        List<FrtbIma.Constituent> constituents = null;
        if (in.has("constituents")) {
            constituents = new ArrayList<>();
            for (In c : in.objects("constituents")) {
                constituents.add(new FrtbIma.Constituent(c.real("weight"), c.integer("n")));
            }
        }
        Double maturity = in.realOrNull("maturity_days");
        in.gate();
        FrtbIma.Horizon h = FrtbIma.liquidityHorizon(category, fxPair, constituents, maturity);
        return Operations.out("n", h.n(), "table_n", h.tableN(), "rule", h.rule(), "label", FrtbIma.LABEL);
    }

    static Out esLh(In in) {
        double[] esT = in.has("es_t") ? in.reals("es_t") : null;
        double[] sigma = in.has("sigma") ? in.reals("sigma") : null;
        double[][] pnl = in.has("pnl") ? in.anyMatrix("pnl") : null;
        in.limit(esT != null && esT.length > FrtbIma.MAX_LIST, "es_t"); // KR-67, limits_k_w2a.py
        in.limit(sigma != null && sigma.length > FrtbIma.MAX_LIST, "sigma");
        if (pnl != null) {
            in.limit(pnl.length > FrtbIma.MAX_LIST, "pnl");
            for (int k = 0; k < pnl.length; k++) {
                in.limit(pnl[k].length > FrtbIma.MAX_PNL, "pnl/" + k);
            }
        }
        in.gate();
        FrtbIma.EsLh e = FrtbIma.esLh(esT, sigma, pnl);
        return Operations.out("mode", e.mode(), "es_by_horizon", e.esByHorizon(), "es", e.es(), "label",
                FrtbIma.LABEL);
    }

    private static double[] triple(In t) {
        return new double[] {t.real("es_rs"), t.real("es_fc"), t.real("es_rc")};
    }

    static Out esStressed(In in) {
        double[] t = triple(in);
        in.gate();
        FrtbIma.Stressed s = FrtbIma.esStressed(t[0], t[1], t[2]);
        return Operations.out("ratio", s.ratio(), "ratio_floored", s.ratioFloored(), "es", s.es(), "label",
                FrtbIma.LABEL);
    }

    static Out imcc(In in) {
        double[] portfolio = triple(in.object("portfolio"));
        In c = in.object("classes");
        for (String key : c.keys()) {
            if (!FrtbIma.IMCC_CLASSES.contains(key)) {
                throw new QfError("E_SCHEMA", "classes." + key + ": not a risk class (IR, EQ, FX, COM, CS)",
                        "classes." + key);
            }
        }
        Map<String, double[]> classes = new LinkedHashMap<>();
        for (String key : c.keys()) {
            classes.put(key, triple(c.object(key)));
        }
        in.gate();
        FrtbIma.Imcc r = FrtbIma.imcc(portfolio, classes);
        return Operations.out("imcc_c", r.imccC(), "portfolio_floored", r.portfolioFloored(), "classes",
                new LinkedHashMap<String, Object>(r.classes()), "classes_floored", r.classesFloored(), "imcc", r.imcc(),
                "label", FrtbIma.LABEL);
    }

    static Out ses(In in) {
        double[] a = in.reals("idio_credit");
        double[] b = in.reals("idio_equity");
        double[] o = in.reals("other");
        in.gate();
        FrtbIma.Ses s = FrtbIma.ses(a, b, o);
        return Operations.out("idio_credit", s.idioCredit(), "idio_equity", s.idioEquity(), "other", s.other(), "ses",
                s.ses(), "label", FrtbIma.LABEL);
    }

    static Out capital(In in) {
        List<FrtbIma.Desk> desks = new ArrayList<>();
        for (In d : in.objects("desks")) {
            desks.add(new FrtbIma.Desk(choice(d, "zone", ZONES), d.real("sa")));
        }
        double imccPrev = in.real("imcc_prev");
        double sesPrev = in.real("ses_prev");
        double imccAvg = in.real("imcc_avg");
        double sesAvg = in.real("ses_avg");
        long exceptions = in.integer("exceptions");
        double drc = in.real("drc");
        double cU = in.real("c_u");
        double saAll = in.real("sa_all");
        double addon = in.real("qualitative_addon", 0.0);
        in.gate();
        FrtbIma.Capital c = FrtbIma.capital(imccPrev, sesPrev, imccAvg, sesAvg, exceptions, drc, desks, cU, saAll,
                addon);
        return Operations.out("m_c", c.mC(), "c_a", c.cA(), "ima_ga", c.imaGa(), "sa_ga", c.saGa(), "k", c.k(),
                "surcharge", c.surcharge(), "acr_total", c.acrTotal(), "label", FrtbIma.LABEL);
    }

    private static String iso(Object d) {
        return d == null ? null : d.toString();
    }

    static Out rfet(In in) {
        var asOf = in.date("as_of");
        var observations = in.dates("observations");
        in.gate();
        FrtbIma.Rfet r = FrtbIma.rfet(asOf, observations);
        return Operations.out("window_start", iso(r.windowStart()), "distinct_days", r.distinctDays(),
                "min_window_count", r.minWindowCount(), "first_failing_window_start", iso(r.firstFailingWindowStart()),
                "first_failing_window_count", r.firstFailingWindowCount(), "crit1", r.crit1(), "crit2", r.crit2(),
                "pass", r.pass(), "label", FrtbIma.LABEL);
    }

    static Out rfetBucket(In in) {
        String row = choice(in, "row", ROWS);
        Double t = in.realOrNull("t");
        Double delta = in.realOrNull("delta");
        in.gate();
        FrtbIma.Bucket b = FrtbIma.rfetBucket(row, t, delta);
        return Operations.out("bucket", b.bucket(), "lower", b.lower(), "upper", b.upper(), "label", FrtbIma.LABEL);
    }

    /** Adds the 14 verbs. Called from Operations.MODULES once the coordinator registers the module. */
    static void register(Map<String, Function<In, Out>> table) {
        table.put("risk.frtb.drc_nonsec", OpsStageKW2a::drcNonsec);
        table.put("risk.frtb.drc_sec_nonctp", OpsStageKW2a::drcSecNonctp);
        table.put("risk.frtb.drc_ctp", OpsStageKW2a::drcCtp);
        table.put("risk.frtb.rrao", OpsStageKW2a::rrao);
        table.put("risk.frtb.pla", OpsStageKW2a::pla);
        table.put("risk.frtb.pla.ks_pvalue", OpsStageKW2a::plaKsPvalue);
        table.put("risk.frtb.ima.lh", OpsStageKW2a::lh);
        table.put("risk.frtb.ima.es_lh", OpsStageKW2a::esLh);
        table.put("risk.frtb.ima.es_stressed", OpsStageKW2a::esStressed);
        table.put("risk.frtb.ima.imcc", OpsStageKW2a::imcc);
        table.put("risk.frtb.ima.ses", OpsStageKW2a::ses);
        table.put("risk.frtb.ima.capital", OpsStageKW2a::capital);
        table.put("risk.frtb.rfet", OpsStageKW2a::rfet);
        table.put("risk.frtb.rfet.bucket", OpsStageKW2a::rfetBucket);
    }
}
