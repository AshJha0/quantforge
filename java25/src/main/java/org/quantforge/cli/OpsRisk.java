package org.quantforge.cli;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.function.ToDoubleFunction;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.Conventions;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.curves.Ois;
import org.quantforge.pricing.Bonds;
import org.quantforge.pricing.Pricing;
import org.quantforge.risk.CurveRisk;

/** Phase R2.1: par, key-rate and Jacobian curve risk (06-risk/par-and-key-rate.md). */
final class OpsRisk {
    private OpsRisk() {}

    /** A parsed product: its OIS convention (null for a bond), notional rule, and a value on a given curve. */
    private record Product(Conventions.RateIndex convention, Double notional, Pricing.OisTrade trade, Bonds.Bond bond,
                           LocalDate settlement) {
        void checkNotional() {
            if (notional != null && !(notional > 0.0)) {
                throw new QfError("E_DOMAIN", "notional must be positive", "notional");
            }
        }

        /** The product's notional: the OIS trade's, or the bond's face. */
        double size() {
            return trade != null ? trade.notional() : notional;
        }

        /** The pricer for this product; an OIS keeps the periods of the curve's own as_of. */
        ToDoubleFunction<Curve> pricer(LocalDate asOf) {
            if (trade != null) {
                Ois.Legs legs = Ois.legs(trade.convention(), asOf, trade.tenor());
                return c -> Pricing.oisPv(trade, legs, c);
            }
            return c -> notional * Bonds.curveDirty(bond, settlement, c, 0.0) / 100.0;
        }
    }

    private static Product product(In in) {
        In p = in.object("product");
        String kind = p.string("kind");
        return switch (kind) {
            case "OIS" -> {
                Pricing.OisTrade t = StageB.oisTrade(p.object("trade"));
                yield new Product(t.convention(), null, t, null, null);
            }
            case "BOND" -> new Product(null, p.real("notional"), null, StageD2.bond(p.object("bond")),
                    p.date("settlement"));
            default -> throw new QfError("E_SCHEMA", "unknown product kind", "kind");
        };
    }

    private static double bumpBp(In in) {
        return in.real("bump_bp", 1.0);
    }

    private static CurveRisk.Scheme scheme(In in) {
        return in.has("scheme") ? in.choice("scheme", CurveRisk.Scheme.class) : CurveRisk.Scheme.CENTRAL;
    }

    private static void checkConvention(Product p, Conventions.RateIndex c) {
        if (p.convention() != null && p.convention() != c) {
            throw new QfError("E_INPUT", "trade convention differs from the curve's", "convention");
        }
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("risk.curve.par", in -> {
            LocalDate asOf = in.date("as_of");
            Conventions.RateIndex c = Conventions.overnight(in.string("convention"));
            List<Ois.Quote> quotes = StageB.quotes(in);
            Curve.Interpolation interp = in.choice("interpolation", Curve.Interpolation.class);
            Product p = product(in);
            double bump = bumpBp(in);
            CurveRisk.Scheme scheme = scheme(in);
            in.gate();
            CurveRisk.checkBump(bump);
            p.checkNotional();
            checkConvention(p, c);
            CurveRisk.Par r = CurveRisk.par(c, asOf, quotes, interp, p.pricer(asOf), bump, scheme);
            return Operations.out("value", r.value(), "par_dv01", r.parDv01(), "par_buckets", r.parBuckets());
        });
        table.put("risk.curve.key_rate", in -> {
            StageB.CurveInput ci = StageB.curve(in, "curve");
            CurveRisk.Mode mode = in.choice("mode", CurveRisk.Mode.class);
            LocalDate[] keys = in.has("key_dates") ? in.dates("key_dates").toArray(LocalDate[]::new) : null;
            Product p = product(in);
            double bump = bumpBp(in);
            CurveRisk.Scheme scheme = scheme(in);
            in.gate();
            CurveRisk.checkBump(bump);
            p.checkNotional();
            Curve curve = ci.build();
            CurveRisk.checkKeyDates(curve, mode, keys);
            CurveRisk.KeyRate r = CurveRisk.keyRate(curve, mode, keys, p.pricer(curve.asOf()), bump, scheme);
            return Operations.out("value", r.value(), "key_rates", r.keyRates(), "zero_dv01", r.zeroDv01());
        });
        table.put("risk.pnl.explain", in -> {
            LocalDate asOf = in.date("as_of");
            Conventions.RateIndex c = Conventions.overnight(in.string("convention"));
            Curve.Interpolation interp = in.choice("interpolation", Curve.Interpolation.class);
            List<Ois.Quote> start = StageB.quotes(in, "quotes_start");
            List<Ois.Quote> end = StageB.quotes(in, "quotes_end");
            Product p = product(in);
            double bump = bumpBp(in);
            in.gate();
            CurveRisk.checkBump(bump);
            p.checkNotional();
            checkConvention(p, c);
            CurveRisk.checkSameTenors(start, end);
            CurveRisk.Explain e = CurveRisk.explain(c, asOf, interp, start, end, p.pricer(asOf), bump, p.size());
            return Operations.out("value_start", e.valueStart(), "value_end", e.valueEnd(), "full_pnl", e.fullPnl(),
                    "par_buckets", e.parBuckets(), "risk_pnl", e.riskPnl(), "gross_risk_pnl", e.grossRiskPnl(), "unexplained", e.unexplained(),
                    "threshold", e.threshold(), "explained", e.explained());
        });
        table.put("risk.curve.jacobian", in -> {
            LocalDate asOf = in.date("as_of");
            Conventions.RateIndex c = Conventions.overnight(in.string("convention"));
            List<Ois.Quote> quotes = StageB.quotes(in);
            Curve.Interpolation interp = in.choice("interpolation", Curve.Interpolation.class);
            double bump = bumpBp(in);
            in.gate();
            CurveRisk.checkBump(bump);
            CurveRisk.Jacobian j = CurveRisk.jacobian(c, asOf, quotes, interp, bump);
            List<String> dates = new ArrayList<>();
            for (LocalDate d : j.pillarDates()) {
                dates.add(d.toString());
            }
            return Operations.out("pillar_dates", dates, "zero_rates", j.zeroRates(), "jacobian", j.jacobian());
        });
    }
}
