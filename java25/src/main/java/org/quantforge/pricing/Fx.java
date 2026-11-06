package org.quantforge.pricing;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import org.quantforge.core.Calendars;
import org.quantforge.core.Conventions;
import org.quantforge.core.QfError;
import org.quantforge.curves.Curve;
import org.quantforge.pricing.Pricing.FxForward;
import org.quantforge.pricing.Pricing.FxMarket;
import org.quantforge.pricing.Pricing.FxResult;
import org.quantforge.pricing.Pricing.FxSide;
import org.quantforge.pricing.Pricing.FxSwap;
import org.quantforge.pricing.Pricing.Valuation;

/** FX forwards, swaps and quote-implied basis (fx.md). */
public final class Fx {
    private Fx() {}

    public record Point(String tenor, double points) {}

    public record Node(LocalDate valueDate, double impliedRatio, double basisBp) {}

    private static boolean jointBusinessDay(Conventions.FxPair p, LocalDate d) {
        for (Calendars.Id c : p.calendars()) {
            if (!Calendars.isBusinessDay(c, d)) {
                return false;
            }
        }
        return true;
    }

    public static LocalDate spotDate(Conventions.FxPair p, LocalDate tradeDate) {
        LocalDate d = tradeDate;
        int left = p.spotLag();
        while (left > 0) {
            d = d.plusDays(1);
            if (jointBusinessDay(p, d)) {
                left--;
            }
        }
        return d;
    }

    private static void checkMarket(FxMarket m) {
        if (m.spot() <= 0.0) {
            throw new QfError("E_DOMAIN", "spot must be positive", "spot");
        }
        if (!m.base().asOf().equals(m.asOf()) || !m.quote().asOf().equals(m.asOf())) {
            throw new QfError("E_INPUT", "a curve's as_of differs");
        }
    }

    private static void checkValueDate(FxMarket m, LocalDate d) {
        if (d.isBefore(spotDate(m.pair(), m.asOf()))) {
            throw new QfError("E_DATE_ORDER", "value date is before spot");
        }
    }

    private static double growth(Curve c, LocalDate t, LocalDate sp) {
        return c.discount(t) / c.discount(sp);
    }

    private static double forwardAt(FxMarket m, LocalDate t) {
        LocalDate sp = spotDate(m.pair(), m.asOf());
        return m.spot() * growth(m.base(), t, sp) / growth(m.quote(), t, sp);
    }

    public static Pricing.Forward outright(FxMarket m, LocalDate valueDate) {
        checkMarket(m);
        checkValueDate(m, valueDate);
        double f = forwardAt(m, valueDate);
        return new Pricing.Forward(f, (f - m.spot()) / m.pair().pip());
    }

    private static FxResult leg(FxMarket m, FxForward t, String model) {
        double sign = t.side() == FxSide.BUY ? 1.0 : -1.0;
        double f = forwardAt(m, t.valueDate());
        double dq = m.quote().discount(t.valueDate());
        double pv = sign * t.notionalBase() * (f - t.strike()) * dq;
        double delta = sign * t.notionalBase() * (f / m.spot()) * dq;
        return new FxResult(valuation(m, pv, model), delta);
    }

    private static Valuation valuation(FxMarket m, double pv, String model) {
        return new Valuation(pv, m.pair().quote(), model, m.snapshotId(), m.pair().id(), m.asOf());
    }

    public static FxResult forwardPv(FxMarket m, FxForward t) {
        checkMarket(m);
        checkValueDate(m, t.valueDate());
        return leg(m, t, "FX_FORWARD_DISCOUNTING");
    }

    public static FxResult swapPv(FxMarket m, FxSwap t) {
        checkMarket(m);
        checkValueDate(m, t.nearDate());
        checkValueDate(m, t.farDate());
        if (!t.nearDate().isBefore(t.farDate())) {
            throw new QfError("E_DATE_ORDER", "near_date is not before far_date");
        }
        FxSide near = t.farSide() == FxSide.BUY ? FxSide.SELL : FxSide.BUY;
        FxResult a = leg(m, new FxForward(t.notionalBase(), t.nearRate(), t.nearDate(), near), "");
        FxResult b = leg(m, new FxForward(t.notionalBase(), t.farRate(), t.farDate(), t.farSide()), "");
        return new FxResult(valuation(m, a.valuation().pv() + b.valuation().pv(), "FX_SWAP_DISCOUNTING"),
                a.fxDelta() + b.fxDelta());
    }

    public static List<Node> implied(FxMarket m, List<Point> points) {
        checkMarket(m);
        Conventions.FxPair p = m.pair();
        LocalDate sp = spotDate(p, m.asOf());
        List<Node> nodes = new ArrayList<>();
        for (Point q : points) {
            LocalDate t = valueDate(p, sp, q.tenor());
            if (!nodes.isEmpty() && !t.isAfter(nodes.getLast().valueDate())) {
                throw new QfError("E_INPUT", "points are not in tenor order", "points");
            }
            double f = m.spot() + q.points() * p.pip();
            double ratio = f / m.spot() * growth(m.quote(), t, sp);
            double tau = ChronoUnit.DAYS.between(sp, t) / 365.0;
            double basis = 10000.0 * (-Math.log(ratio) / tau + Math.log(growth(m.base(), t, sp)) / tau);
            nodes.add(new Node(t, ratio, basis));
        }
        return nodes;
    }

    private static LocalDate valueDate(Conventions.FxPair p, LocalDate sp, String tenor) {
        int n = Integer.parseInt(tenor.substring(0, tenor.length() - 1));
        LocalDate t = sp.plusMonths(tenor.endsWith("Y") ? 12L * n : n);
        t = Calendars.adjust(p.calendars().getFirst(), t, Calendars.Convention.MODIFIED_FOLLOWING);
        while (!jointBusinessDay(p, t)) {
            t = t.plusDays(1);
        }
        return t;
    }
}
