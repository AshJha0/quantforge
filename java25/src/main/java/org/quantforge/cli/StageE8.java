package org.quantforge.cli;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;
import org.quantforge.core.QfError;
import org.quantforge.pricing.CreditOptions;

/** Stage E8: CDS options, copulas, large homogeneous pool (credit-options-and-copulas.md). */
final class StageE8 {
    private StageE8() {}

    private record Option(LocalDate asOf, LocalDate expiry, LocalDate maturity, double r, double h, double rec,
                          boolean payer, double k, double n, double x, boolean knockOut) {}

    private static Option option(In in, String last) {
        LocalDate a = in.date("as_of");
        LocalDate e = in.date("expiry");
        LocalDate m = in.date("maturity");
        double r = in.real("rate");
        double h = in.real("hazard_rate");
        double rec = in.real("recovery");
        String type = in.string("type");
        boolean payer = switch (type) {
            case "PAYER" -> true;
            case "RECEIVER" -> false;
            default -> throw new QfError("E_SCHEMA", "type must be PAYER or RECEIVER", "type");
        };
        double k = in.real("strike");
        double n = in.real("notional");
        double x = in.real(last);
        boolean ko = in.gate(in.bool("knock_out"));
        CreditOptions.checkOption(a, e, m, h, rec, k);
        return new Option(a, e, m, r, h, rec, payer, k, n, x, ko);
    }

    private static void probability(double p) {
        if (!(p > 0.0 && p < 1.0)) {
            throw new QfError("E_DOMAIN", "a probability must be in (0, 1)", "default_probabilities");
        }
    }

    static void register(Map<String, Function<In, Out>> table) {
        table.put("credit.cdsoption.price", in -> {
            Option o = option(in, "vol");
            if (!(o.x() >= 0.0)) {
                throw new QfError("E_DOMAIN", "vol must not be negative", "vol");
            }
            CreditOptions.OptionPrice p = CreditOptions.price(o.asOf(), o.expiry(), o.maturity(), o.r(), o.h(),
                    o.rec(), o.payer(), o.k(), o.n(), o.x(), o.knockOut());
            return Operations.out("price", p.price(), "forward_spread", p.forward(), "risky_annuity", p.annuity(),
                    "front_end_protection", p.frontEnd());
        });
        table.put("credit.cdsoption.implied_vol", in -> {
            Option o = option(in, "premium");
            if (!o.knockOut()) {
                throw new QfError("E_INPUT", "implied vol is for knock-out options only (ruling E-B23)", "knock_out");
            }
            return Operations.out("vol", CreditOptions.impliedVol(o.asOf(), o.expiry(), o.maturity(), o.r(), o.h(),
                    o.rec(), o.payer(), o.k(), o.n(), o.x()));
        });
        table.put("credit.copula.joint_default", in -> {
            CreditOptions.Copula c = in.choice("copula", CreditOptions.Copula.class);
            double[] p = in.reals("default_probabilities");
            double rho = in.real("correlation");
            Double nu = in.realOrNull("degrees_of_freedom");
            in.gate();
            if (p.length != 2) {
                throw new QfError("E_INPUT", "need two default probabilities", "default_probabilities");
            }
            if (c == CreditOptions.Copula.STUDENT_T && nu == null) {
                throw new QfError("E_INPUT", "STUDENT_T needs degrees_of_freedom", "degrees_of_freedom");
            }
            probability(p[0]);
            probability(p[1]);
            if (!(Math.abs(rho) < 1.0)) {
                throw new QfError("E_DOMAIN", "correlation must be in (-1, 1)", "correlation");
            }
            if (nu != null && !(nu > 0.0)) {
                throw new QfError("E_DOMAIN", "degrees_of_freedom must be above 0", "degrees_of_freedom");
            }
            double[] r = CreditOptions.jointDefault(c, p[0], p[1], rho, nu == null ? 0.0 : nu);
            return Operations.out("joint_default_probability", r[0], "default_correlation", r[1]);
        });
        table.put("credit.lhp.tranche_loss", in -> {
            double p = in.real("default_probability");
            double rho = in.real("correlation");
            double rec = in.real("recovery");
            double a = in.real("attachment");
            double d = in.gate(in.real("detachment"));
            if (!(d > a) || a < 0.0 || d > 1.0) {
                throw new QfError("E_INPUT", "need 0 <= attachment < detachment <= 1", "attachment");
            }
            CreditOptions.checkPool(p, rho, rec);
            return Operations.out("expected_loss_fraction", CreditOptions.trancheLoss(p, rho, rec, a, d));
        });
        table.put("credit.lhp.loss_cdf", in -> {
            double p = in.real("default_probability");
            double rho = in.real("correlation");
            double rec = in.real("recovery");
            double[] x = in.gate(in.reals("losses"));
            CreditOptions.checkPool(p, rho, rec);
            List<Object> out = new ArrayList<>();
            for (double v : x) {
                if (!(v > 0.0 && v < 1 - rec)) {
                    throw new QfError("E_DOMAIN", "a loss must be in (0, 1 - R)", "losses");
                }
            }
            for (double v : x) {
                out.add(CreditOptions.lossCdf(p, rho, rec, v));
            }
            return Operations.out("cdf", out);
        });
    }
}
