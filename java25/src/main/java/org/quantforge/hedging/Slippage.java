package org.quantforge.hedging;

import java.util.ArrayList;
import java.util.List;
import org.quantforge.core.QfError;

/**
 * {@code hedge.slippage.report} ({@code 08-hedging/hedge-slippage.md}): implementation shortfall of hedge orders
 * against their decision prices, split into execution and opportunity cost, and compared with the wave 4a cost model
 * (rulings I-36, I-37). Signs make a positive cost a cost for buys and sells alike.
 */
public final class Slippage {
    private Slippage() {}

    /**
     * One fill.
     *
     * @param quantity signed filled quantity, the order's sign
     * @param price fill price
     */
    public record Fill(double quantity, double price) {}

    /**
     * One order.
     *
     * @param quantity signed order quantity (positive buys)
     * @param decisionPrice the price when the hedge was decided
     * @param finalPrice the price that values the unfilled rest
     * @param halfSpread model cost per unit filled
     * @param impact model linear-impact coefficient
     * @param fills the fills, possibly none
     */
    public record Order(double quantity, double decisionPrice, double finalPrice, double halfSpread, double impact,
            List<Fill> fills) {}

    /**
     * Costs of one order, or totals over orders.
     *
     * @param filledQuantity sum of fill quantities (0 for totals)
     * @param averagePrice volume-weighted fill price, null with no fills or for totals
     * @param executionCost {@code sum q (p - d)}
     * @param opportunityCost {@code (Q - q_f)(final - d)}
     * @param shortfall execution plus opportunity cost
     * @param modelCost {@code half_spread |q_f| + impact q_f^2}
     * @param slippage execution cost minus model cost
     */
    public record Costs(double filledQuantity, Double averagePrice, double executionCost, double opportunityCost,
            double shortfall, double modelCost, double slippage) {}

    /**
     * The report.
     *
     * @param orders per-order costs, in input order
     * @param total the sums over orders
     */
    public record Report(List<Costs> orders, Costs total) {}

    /**
     * Computes the report.
     *
     * @param orders one or more orders
     * @return per-order costs and totals
     * @throws QfError {@code E_INPUT}, then {@code E_DOMAIN}, in the specification's order
     */
    public static Report report(List<Order> orders) {
        if (orders.isEmpty()) {
            throw new QfError("E_INPUT", "no orders", "orders");
        }
        for (Order o : orders) {
            if (o.quantity() == 0.0) {
                throw new QfError("E_INPUT", "an order quantity of 0", "orders");
            }
            double filled = 0.0;
            for (Fill f : o.fills()) {
                if (f.quantity() == 0.0 || Math.signum(f.quantity()) != Math.signum(o.quantity())) {
                    throw new QfError("E_INPUT", "a fill of 0 or of the other sign", "fills");
                }
                filled += f.quantity();
            }
            if (Math.abs(filled) > Math.abs(o.quantity())) {
                throw new QfError("E_INPUT", "fills add up to more than the order", "fills");
            }
        }
        for (Order o : orders) {
            if (!(o.decisionPrice() > 0.0) || !(o.finalPrice() > 0.0)) {
                throw new QfError("E_DOMAIN", "a price at or below 0", "orders");
            }
            for (Fill f : o.fills()) {
                if (!(f.price() > 0.0)) {
                    throw new QfError("E_DOMAIN", "a fill price at or below 0", "fills");
                }
            }
            if (!(o.halfSpread() >= 0.0) || !(o.impact() >= 0.0)) {
                throw new QfError("E_DOMAIN", "a negative half_spread or impact", "orders");
            }
        }
        List<Costs> out = new ArrayList<>();
        double[] total = new double[5];
        for (Order o : orders) {
            double qf = 0.0;
            double notional = 0.0;
            double exec = 0.0;
            for (Fill f : o.fills()) {
                qf += f.quantity();
                notional += f.quantity() * f.price();
                exec += f.quantity() * (f.price() - o.decisionPrice());
            }
            double opp = (o.quantity() - qf) * (o.finalPrice() - o.decisionPrice());
            double model = o.halfSpread() * Math.abs(qf) + o.impact() * qf * qf;
            Costs c = new Costs(qf + 0.0, o.fills().isEmpty() ? null : notional / qf, exec + 0.0, opp + 0.0,
                    exec + opp + 0.0, model + 0.0, exec - model + 0.0);
            out.add(c);
            total[0] += c.executionCost();
            total[1] += c.opportunityCost();
            total[2] += c.shortfall();
            total[3] += c.modelCost();
            total[4] += c.slippage();
        }
        return new Report(out, new Costs(0.0, null, total[0], total[1], total[2], total[3], total[4]));
    }
}
