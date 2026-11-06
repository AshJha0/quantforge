package org.quantforge.pricing;

import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;
import org.quantforge.core.Conventions;
import org.quantforge.curves.Curve;
import org.quantforge.curves.Ois;
import org.quantforge.curves.Projection;

/**
 * Discounting pricing models (pricing-framework.md). Trades here are instruments: terms only. Product models live
 * in {@code curves}, market data arrives as curves, and each method returns a {@link Valuation}.
 */
public final class Pricing {
    private Pricing() {}

    public enum Side { PAY, RECEIVE }

    public enum FxSide { BUY, SELL }

    public record Valuation(double pv, String currency, String model, String dataVersion, String conventions,
                            LocalDate asOf) {
        public Map<String, Object> toJson() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("pv", pv);
            m.put("currency", currency);
            m.put("model", model);
            m.put("data_version", dataVersion);
            m.put("conventions", conventions);
            m.put("as_of", asOf.toString());
            return m;
        }
    }

    public record OisTrade(Conventions.RateIndex convention, String tenor, double fixedRate, double notional, Side side) {}

    public record SwapTrade(Conventions.RateIndex index, long tenorMonths, double fixedRate, double notional, Side side) {}

    public record FraTrade(Conventions.RateIndex index, LocalDate start, double fixedRate, double notional, Side side) {}

    public record FxForward(double notionalBase, double strike, LocalDate valueDate, FxSide side) {}

    public record FxSwap(double notionalBase, LocalDate nearDate, double nearRate, LocalDate farDate, double farRate,
                         FxSide farSide) {}

    public record OisResult(Valuation valuation, double parRate, double annuity) {}

    public record SwapResult(Valuation valuation, double parRate) {}

    public record FraResult(Valuation valuation, double forwardRate) {}

    public record FxResult(Valuation valuation, double fxDelta) {}

    public record Forward(double forward, double points) {}

    /** FX market data, frozen. */
    public record FxMarket(Conventions.FxPair pair, double spot, LocalDate asOf, Curve base, Curve quote,
                           String snapshotId) {}

    private static double sign(Side s) {
        return s == Side.PAY ? 1.0 : -1.0;
    }

    public static double oisPv(OisTrade t, Ois.Legs legs, Curve d) {
        return sign(t.side()) * t.notional() * (legs.floating(d) - t.fixedRate() * legs.annuity(d));
    }

    public static OisResult ois(OisTrade t, Curve d, String snapshotId) {
        Ois.Legs legs = Ois.legs(t.convention(), d.asOf(), t.tenor());
        Valuation v = new Valuation(oisPv(t, legs, d), t.convention().currency(), "OIS_DISCOUNTING", snapshotId,
                t.convention().id(), d.asOf());
        return new OisResult(v, legs.parRate(d), legs.annuity(d));
    }

    public static SwapResult swap(SwapTrade t, Curve d, Curve p, String snapshotId) {
        Projection.Swap s = Projection.swap(t.index(), d.asOf(), t.tenorMonths());
        double pv = sign(t.side()) * t.notional() * (s.floatingLeg(d, p) - t.fixedRate() * s.annuity(d));
        return new SwapResult(new Valuation(pv, t.index().currency(), "SWAP_DISCOUNTING", snapshotId, t.index().id(),
                d.asOf()), s.parRate(d, p));
    }

    public static FraResult fra(FraTrade t, Curve d, Curve p, String snapshotId) {
        Conventions.RateIndex ix = t.index();
        LocalDate e = Projection.plusMonths(ix, t.start(), ix.months());
        double f = Projection.forward(ix, p, t.start(), e);
        double alpha = Projection.accrual(ix, t.start(), e);
        double pv = sign(t.side()) * t.notional() * alpha * (f - t.fixedRate()) / (1.0 + alpha * f) * d.discount(t.start());
        return new FraResult(new Valuation(pv, ix.currency(), "FRA_DISCOUNTING", snapshotId, ix.id(), d.asOf()), f);
    }
}
