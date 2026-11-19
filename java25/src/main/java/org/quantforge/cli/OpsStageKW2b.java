package org.quantforge.cli;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.risk.Cva;
import org.quantforge.risk.Leverage;

/**
 * Stage K wave 2b verbs: CVA capital (K-8g, cva-capital.md) and leverage ratio and large exposures, simplified (K-8i,
 * leverage-large-exposures.md). Port of {@code python/quantforge_core/cli/ops_k_w2b.py}. Every input is read first
 * (E_SCHEMA, enum values and factor names included), then the gate (held E_LIMIT, then the finite rule), then the
 * core: structural E_INPUT before E_DOMAIN. Error order KR-67 (= HR-122). Registered by the coordinator at
 * integration (program/STAGE_K_W2B_JAVA_HANDOVER.md); until then this class is reached only by its tests.
 */
final class OpsStageKW2b {
    private OpsStageKW2b() {}

    /** An optional array of objects: absent means empty (KR-122, KR-128). */
    private static List<In> list(In in, String key) {
        return in.has(key) ? in.objects(key) : List.of();
    }

    private static String optString(In in, String key) {
        return in.has(key) ? in.string(key) : null;
    }

    private static String choice(In in, String key, List<String> allowed) {
        return OpsStageKW1b.choice(in, key, allowed);
    }

    // --- risk.cva.ba ---------------------------------------------------------------------------------------------

    static Out cvaBa(In in) {
        List<Cva.Counterparty> cps = new ArrayList<>();
        for (In c : in.objects("counterparties")) {
            String id = c.string("id");
            String sector = choice(c, "sector", Cva.SECTORS);
            String quality = choice(c, "quality", Cva.QUALITIES);
            List<Cva.NettingSet> sets = new ArrayList<>();
            for (In n : c.objects("netting_sets")) {
                sets.add(new Cva.NettingSet(n.real("ead"), n.real("m"), n.bool("imm", false)));
            }
            cps.add(new Cva.Counterparty(id, sector, quality, sets));
        }
        String version = choice(in, "version", Cva.VERSIONS);
        List<String> relations = new ArrayList<>(Cva.RELATIONS.keySet());
        List<Cva.SingleNameHedge> single = new ArrayList<>();
        for (In h : list(in, "single_name_hedges")) {
            single.add(new Cva.SingleNameHedge(h.string("counterparty"), choice(h, "relation", relations),
                    choice(h, "sector", Cva.SECTORS), choice(h, "quality", Cva.QUALITIES), h.real("m"),
                    h.real("notional")));
        }
        List<Cva.IndexHedge> index = new ArrayList<>();
        for (In h : list(in, "index_hedges")) {
            double m = h.real("m");
            double notional = h.real("notional");
            List<Cva.Constituent> ks = new ArrayList<>();
            for (In k : h.objects("constituents")) {
                ks.add(new Cva.Constituent(choice(k, "sector", Cva.SECTORS), choice(k, "quality", Cva.QUALITIES),
                        k.real("weight")));
            }
            index.add(new Cva.IndexHedge(m, notional, ks));
        }
        in.gate();
        return Operations.out(baOutputs(Cva.baCva(cps, version, single, index)).toArray());
    }

    static List<Object> baOutputs(Cva.BaResult r) {
        List<Object> rows = new ArrayList<>();
        for (Cva.CounterpartyRow c : r.counterparties()) {
            List<Object> sets = new ArrayList<>();
            for (double df : c.df()) {
                sets.add(Operations.out("df", df).outputs());
            }
            rows.add(Operations.out("id", c.id(), "scva", c.scva(), "snh", c.snh(), "hma", c.hma(), "netting_sets",
                    sets).outputs());
        }
        // Arrays.asList: the FULL-only fields are null for REDUCED (KR-122)
        return Arrays.asList("version", r.version(), "counterparties", rows, "ih", r.ih(), "k_reduced", r.kReduced(),
                "k_hedged", r.kHedged(), "k_full", r.kFull(), "capital", r.capital(), "rwa", r.rwa(), "label",
                r.label());
    }

    // --- risk.cva.sa ---------------------------------------------------------------------------------------------

    private static Cva.Sensitivity sensitivity(String cls, String kind, In s) {
        String factor = null;
        Cva.CreditFactor credit = null;
        if (cls.equals("CCS")) {
            In f = s.object("factor");
            credit = new Cva.CreditFactor(f.string("name"), choice(f, "tenor", Cva.CCS_TENORS),
                    choice(f, "quality", Cva.QUALITIES), optString(f, "legal_group"), optString(f, "index"),
                    optString(f, "series"));
        } else if (cls.equals("IR")) {
            factor = choice(s, "factor", kind.equals("DELTA") ? Cva.IR_DELTA_FACTORS : Cva.IR_VEGA_FACTORS);
        } else {
            factor = s.string("factor");
        }
        return new Cva.Sensitivity(s.string("bucket"), factor, credit, s.real("s_cva"), s.real("s_hdg"));
    }

    static Out cvaSa(In in) {
        // CCS.VEGA is read here and refused by the core as E_INPUT (cva-capital.md, Errors)
        List<String> keys = new ArrayList<>();
        for (String c : Cva.RISK_CLASSES) {
            for (String k : Cva.KINDS) {
                keys.add(c + "." + k);
            }
        }
        In c = in.object("classes");
        Map<String, List<Cva.Sensitivity>> classes = new LinkedHashMap<>();
        for (String key : c.keys()) {
            if (!keys.contains(key)) {
                throw new QfError("E_SCHEMA", "classes: " + key + " is not listed", "classes");
            }
            int dot = key.indexOf('.');
            List<Cva.Sensitivity> items = new ArrayList<>();
            for (In s : c.objects(key)) {
                items.add(sensitivity(key.substring(0, dot), key.substring(dot + 1), s));
            }
            classes.put(key, items);
        }
        String rep = in.string("reporting_currency");
        double mCva = in.real("m_cva", Cva.M_CVA);
        in.gate();
        return Operations.out(saOutputs(Cva.saCva(classes, rep, mCva)).toArray());
    }

    static List<Object> saOutputs(Cva.SaResult r) {
        Map<String, Object> classes = new LinkedHashMap<>();
        for (Map.Entry<String, Cva.ClassResult> e : r.classes().entrySet()) {
            List<Object> rows = new ArrayList<>();
            for (Cva.BucketRow b : e.getValue().buckets()) {
                rows.add(Operations.out("bucket", b.bucket(), "k_b", b.kB(), "s_b", b.sB(), "sum_ws", b.sumWs(),
                        "floored", b.floored()).outputs());
            }
            classes.put(e.getKey(), Operations.out("buckets", rows, "k", e.getValue().k()).outputs());
        }
        return List.of("classes", classes, "m_cva", r.mCva(), "total", r.total(), "rwa", r.rwa(), "label", r.label());
    }

    // --- risk.capital.leverage -----------------------------------------------------------------------------------

    static Out leverage(In in) {
        double tier1 = in.real("tier1");
        double[] on = in.has("on_balance") ? in.reals("on_balance") : new double[0];
        List<Leverage.DerivativeSet> derivs = new ArrayList<>();
        for (In d : list(in, "derivatives")) {
            derivs.add(new Leverage.DerivativeSet(d.real("v"), d.real("pfe"), d.real("cvm_received", 0.0),
                    d.real("cvm_provided", 0.0)));
        }
        List<Leverage.WrittenCreditDerivative> written = new ArrayList<>();
        for (In w : list(in, "written_credit_derivatives")) {
            written.add(new Leverage.WrittenCreditDerivative(w.real("notional"), w.real("fair_value"),
                    w.real("purchased_offset", 0.0)));
        }
        List<Leverage.Sft> sfts = new ArrayList<>();
        for (In s : list(in, "sfts")) {
            sfts.add(new Leverage.Sft(s.real("gross_assets"), s.bool("mna"), s.reals("exposures"),
                    s.reals("collateral")));
        }
        List<String> categories = new ArrayList<>(Leverage.CCF_CATEGORIES.keySet());
        List<Leverage.OffBalance> obs = new ArrayList<>();
        for (In o : list(in, "off_balance")) {
            obs.add(new Leverage.OffBalance(o.real("notional"), choice(o, "ccf_category", categories)));
        }
        in.gate();
        Leverage.LeverageResult r = Leverage.leverage(tier1, on, derivs, written, sfts, obs);
        return Operations.out("on_balance", r.onBalance(), "derivatives", r.derivatives(), "derivative_netting_sets",
                r.derivativeNettingSets(), "written_credit_derivatives", r.writtenCreditDerivatives(), "sfts",
                r.sfts(), "off_balance", r.offBalance(), "exposure", r.exposure(), "ratio", r.ratio(),
                "meets_minimum", r.meetsMinimum(), "label", r.label());
    }

    // --- risk.capital.large_exposures ----------------------------------------------------------------------------

    static Out largeExposures(In in) {
        double tier1 = in.real("tier1");
        boolean bankGsib = in.bool("bank_gsib", false);
        List<Leverage.LeCounterparty> cps = new ArrayList<>();
        for (In c : in.objects("counterparties")) {
            cps.add(new Leverage.LeCounterparty(c.string("id"), optString(c, "group"), c.bool("gsib", false),
                    c.bool("exempt", false)));
        }
        List<Leverage.BankingBookExposure> bb = new ArrayList<>();
        for (In b : list(in, "banking_book")) {
            bb.add(new Leverage.BankingBookExposure(b.string("counterparty"), b.real("value")));
        }
        List<Leverage.OffBalanceExposure> obs = new ArrayList<>();
        for (In o : list(in, "off_balance")) {
            obs.add(new Leverage.OffBalanceExposure(o.string("counterparty"), o.real("notional"), o.real("ccf")));
        }
        List<Leverage.Protection> crm = new ArrayList<>();
        for (In p : list(in, "crm")) {
            crm.add(new Leverage.Protection(p.string("counterparty"), p.string("provider"), p.real("protected")));
        }
        List<String> seniorities = new ArrayList<>(Leverage.RANKS.keySet());
        List<Leverage.TradingPosition> tb = new ArrayList<>();
        for (In t : list(in, "trading_book")) {
            String id = t.string("id");
            String cp = t.string("counterparty");
            String seniority = choice(t, "seniority", seniorities);
            double notional = t.real("notional");
            double mv = t.real("market_value");
            t.realOrNull("maturity_years"); // read for its type and the finite rule only (KR-131)
            t.bool("cash_equity", false);
            t.bool("lgd_applies", true);
            tb.add(new Leverage.TradingPosition(id, cp, seniority, notional, mv));
        }
        in.gate();
        Leverage.LargeExposuresResult r = Leverage.largeExposures(tier1, cps, bb, obs, crm, tb, bankGsib);
        List<Object> rows = new ArrayList<>();
        for (Leverage.CounterpartyRow c : r.counterparties()) {
            rows.add(Operations.out("id", c.id(), "banking_book", c.bankingBook(), "off_balance", c.offBalance(),
                    "trading_book_net_long", c.tradingBookNetLong(), "trading_book_net_short",
                    c.tradingBookNetShort(), "protected", c.protectedAmount(), "received", c.received(), "exposure",
                    c.exposure()).outputs());
        }
        List<Object> groups = new ArrayList<>();
        for (Leverage.GroupRow g : r.groups()) {
            groups.add(Operations.out("group", g.group(), "members", g.members(), "exposure", g.exposure(), "share",
                    g.share(), "large", g.large(), "limit", g.limit(), "breach", g.breach(), "exempt", g.exempt())
                    .outputs());
        }
        return Operations.out("counterparties", rows, "groups", groups, "report", r.report(), "label", r.label());
    }

    /** Adds the four verbs. Called from Operations.MODULES once the coordinator registers the module. */
    static void register(Map<String, Function<In, Out>> table) {
        table.put("risk.cva.ba", OpsStageKW2b::cvaBa);
        table.put("risk.cva.sa", OpsStageKW2b::cvaSa);
        table.put("risk.capital.leverage", OpsStageKW2b::leverage);
        table.put("risk.capital.large_exposures", OpsStageKW2b::largeExposures);
    }
}
