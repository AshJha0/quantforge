package org.quantforge.cli;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.regex.Pattern;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.pricing.Bonds;

/** Stage D wave 2, D2: bonds, repo and bond futures. */
final class StageD2 {
    private StageD2() {}

    private static final int MAX_BONDS = 100;
    private static final Pattern MONTH = Pattern.compile("\\d{4}-(0[1-9]|1[0-2])");

    static Bonds.Bond bond(In b) {
        LocalDate maturity = b.date("maturity");
        double coupon = b.real("coupon");
        long f = b.integer("frequency");
        if (f != 1 && f != 2 && f != 4) {
            throw new QfError("E_SCHEMA", "frequency must be 1, 2 or 4", "frequency");
        }
        return new Bonds.Bond(maturity, coupon, (int) f);
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("bond.price.from_yield", in -> {
            Bonds.Bond b = bond(in.object("bond"));
            LocalDate s = in.date("settlement");
            double y = in.real("yield");
            in.gate();
            Bonds.YieldPrice r = Bonds.fromYield(b, s, y);
            return Operations.out("dirty", r.dirty(), "accrued", r.accrued(), "clean", r.clean(),
                    "modified_duration", r.modified(), "macaulay_duration", r.macaulay(), "convexity", r.convexity());
        });
        table.put("bond.yield.from_price", in -> {
            Bonds.Bond b = bond(in.object("bond"));
            LocalDate s = in.date("settlement");
            double clean = in.real("clean_price");
            in.gate();
            double y = Bonds.yieldFromPrice(b, s, clean);
            double accrued = b.accrued(s);
            return Operations.out("yield", y, "dirty", clean + accrued, "accrued", accrued);
        });
        table.put("bond.price.from_curve", in -> {
            Bonds.Bond b = bond(in.object("bond"));
            LocalDate s = in.date("settlement");
            StageB.CurveInput c = StageB.curve(in, "curve");
            in.gate();
            double dirty = Bonds.curveDirty(b, s, c.build(), 0.0);
            double accrued = b.accrued(s);
            return Operations.out("dirty", dirty, "accrued", accrued, "clean", dirty - accrued);
        });
        table.put("bond.spread.z", in -> {
            Bonds.Bond b = bond(in.object("bond"));
            LocalDate s = in.date("settlement");
            StageB.CurveInput c = StageB.curve(in, "curve");
            double clean = in.real("clean_price");
            in.gate();
            Bonds.checkSettlement(b, s);
            return Operations.out("z_spread", Bonds.zSpread(b, s, c.build(), clean));
        });
        table.put("bond.spread.asset_swap", in -> {
            Bonds.Bond b = bond(in.object("bond"));
            LocalDate s = in.date("settlement");
            StageB.CurveInput c = StageB.curve(in, "curve");
            double dirty = in.real("dirty_price");
            in.gate();
            Bonds.AssetSwap r = Bonds.assetSwap(b, s, c.build(), dirty);
            return Operations.out("spread", r.spread(), "annuity", r.annuity());
        });
        table.put("bond.frn.price", in -> {
            LocalDate s = in.date("settlement");
            LocalDate m = in.date("maturity");
            long f = in.integer("frequency");
            if (f != 1 && f != 2 && f != 4) {
                throw new QfError("E_SCHEMA", "frequency must be 1, 2 or 4", "frequency");
            }
            double current = in.real("current_rate");
            double margin = in.real("margin");
            double dm = in.real("discount_margin");
            StageB.CurveInput d = StageB.curve(in, "discount");
            StageB.CurveInput p = StageB.curve(in, "projection");
            in.gate();
            Bonds.Frn r = Bonds.frn(s, m, (int) f, current, margin, dm, d.build(), p.build());
            return Operations.out("dirty", r.dirty(), "accrued", r.accrued(), "clean", r.clean());
        });
        table.put("repo.forward", in -> {
            Bonds.Bond b = bond(in.object("bond"));
            LocalDate start = in.date("start");
            LocalDate end = in.date("end");
            double clean = in.real("clean_price");
            double r = in.real("repo_rate");
            Double gc = in.nullableReal("gc_rate");
            in.gate();
            Bonds.Repo x = Bonds.repo(b, start, end, clean, r, gc);
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("dirty", x.dirty());
            out.put("forward_dirty", x.forwardDirty());
            out.put("forward_clean", x.forwardClean());
            out.put("interest", x.interest());
            out.put("special_spread", x.specialSpread());
            out.put("specialness_value", x.specialnessValue());
            return new Out(out, Map.of());
        });
        table.put("repo.implied_rate", in -> {
            Bonds.Bond b = bond(in.object("bond"));
            LocalDate start = in.date("start");
            LocalDate end = in.date("end");
            double clean = in.real("clean_price");
            double fwd = in.real("forward_clean");
            in.gate();
            return Operations.out("repo_rate", Bonds.impliedRepo(b, start, end, clean, fwd));
        });
        table.put("bond.futures.conversion_factor", in -> {
            Bonds.Bond b = bond(in.object("bond"));
            String month = in.string("delivery_month");
            if (!MONTH.matcher(month).matches()) {
                throw new QfError("E_SCHEMA", "delivery_month must be YYYY-MM", "delivery_month");
            }
            double notional = in.real("notional_coupon");
            Bonds.Contract contract = !in.has("contract") ? Bonds.Contract.TEN_YEAR
                    : in.choice("contract", Bonds.Contract.class);
            in.gate();
            return Operations.out("conversion_factor",
                    Bonds.conversionFactor(b, YearMonth.parse(month), notional, contract));
        });
        table.put("bond.futures.basis", in -> {
            double futures = in.real("futures_price");
            LocalDate s = in.date("settlement");
            LocalDate delivery = in.date("delivery");
            double r = in.real("repo_rate");
            List<In> list = in.objects("bonds");
            in.limit(list.size() > MAX_BONDS, "bonds");
            List<Bonds.Bond> bonds = new ArrayList<>();
            double[] clean = new double[list.size()];
            double[] cf = new double[clean.length];
            for (int i = 0; i < clean.length; i++) {
                bonds.add(bond(list.get(i)));
                clean[i] = list.get(i).real("clean_price");
                cf[i] = list.get(i).real("conversion_factor");
            }
            in.gate();
            if (bonds.isEmpty()) {
                throw new QfError("E_INPUT", "no bonds", "bonds");
            }
            List<Map<String, Object>> out = new ArrayList<>();
            int ctd = 0;
            double best = Double.NEGATIVE_INFINITY;
            for (int i = 0; i < clean.length; i++) {
                Bonds.Basis x = Bonds.basis(bonds.get(i), clean[i], cf[i], futures, s, delivery, r);
                out.add(Operations.out("invoice", x.invoice(), "gross_basis", x.grossBasis(), "net_basis", x.netBasis(),
                        "implied_repo", x.impliedRepo()).outputs());
                if (x.impliedRepo() > best) {
                    best = x.impliedRepo();
                    ctd = i;
                }
            }
            return Operations.out("bonds", out, "ctd", (long) ctd);
        });
        table.put("bond.fit.nelson_siegel", in -> {
            LocalDate s = in.date("settlement");
            double tau = in.real("tau");
            List<In> list = in.objects("bonds");
            in.limit(list.size() > MAX_BONDS, "bonds");
            List<Bonds.Bond> bonds = new ArrayList<>();
            double[] dirty = new double[list.size()];
            for (int i = 0; i < dirty.length; i++) {
                bonds.add(bond(list.get(i)));
                dirty[i] = list.get(i).real("dirty_price");
            }
            double[] w = in.hasKey("weights") ? in.reals("weights") : null;
            in.gate();
            if (w == null) {
                w = new double[dirty.length];
                java.util.Arrays.fill(w, 1.0);
            } else if (w.length != dirty.length) {
                throw new QfError("E_INPUT", "weights and bonds differ in length", "weights");
            }
            double[] beta = Bonds.nsBetas(bonds, dirty, w, s, tau);
            double[] res = new double[dirty.length];
            for (int i = 0; i < res.length; i++) {
                res[i] = Bonds.nsModel(bonds.get(i), s, tau, beta, null) - dirty[i];
            }
            return Operations.out("betas", beta, "residuals", res);
        });
    }
}
