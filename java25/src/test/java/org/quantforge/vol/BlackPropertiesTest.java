package org.quantforge.vol;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import net.jqwik.api.Assume;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.constraints.DoubleRange;
import org.quantforge.core.Compounding;
import org.quantforge.vol.Black.Model;
import org.quantforge.vol.Black.Option;

/** G6 property suites: put-call parity, discount-factor monotonicity and the implied-vol round trip. */
class BlackPropertiesTest {

    private static Option option(Model m, double phi, double k, double t, double f, double d) {
        return new Option(m, phi, k, t, f, 0.0, 0.0, d, 0.0);
    }

    /** C - P = D (F - K) for Black-76 and Bachelier at any vol. */
    @Property(tries = 500)
    void putCallParity(@ForAll @DoubleRange(min = 1.0, max = 500.0) double f,
                       @ForAll @DoubleRange(min = 1.0, max = 500.0) double k,
                       @ForAll @DoubleRange(min = 0.01, max = 30.0) double t,
                       @ForAll @DoubleRange(min = 0.05, max = 1.0) double d,
                       @ForAll @DoubleRange(min = 0.0, max = 2.0) double v,
                       @ForAll boolean bachelier) {
        Model m = bachelier ? Model.BACHELIER : Model.BLACK_76;
        double vol = bachelier ? v * f : v;
        double c = Black.price(option(m, 1.0, k, t, f, d), vol);
        double p = Black.price(option(m, -1.0, k, t, f, d), vol);
        double scale = Math.max(f, k);
        assertEquals(d * (f - k), c - p, 1e-12 * scale + 1e-12);
    }

    /** Black-Scholes in spot terms: C - P = S e^{-qT} - K e^{-rT}. */
    @Property(tries = 300)
    void putCallParitySpot(@ForAll @DoubleRange(min = 1.0, max = 500.0) double s,
                           @ForAll @DoubleRange(min = 1.0, max = 500.0) double k,
                           @ForAll @DoubleRange(min = 0.01, max = 10.0) double t,
                           @ForAll @DoubleRange(min = -0.05, max = 0.15) double r,
                           @ForAll @DoubleRange(min = -0.05, max = 0.10) double q,
                           @ForAll @DoubleRange(min = 0.01, max = 1.5) double v) {
        Option call = new Option(Model.BLACK_SCHOLES, 1.0, k, t, s, r, q, 1.0, 0.0);
        Option put = new Option(Model.BLACK_SCHOLES, -1.0, k, t, s, r, q, 1.0, 0.0);
        double lhs = Black.price(call, v) - Black.price(put, v);
        double rhs = s * Math.exp(-q * t) - k * Math.exp(-r * t);
        assertEquals(rhs, lhs, 1e-11 * Math.max(s, k));
    }

    /** With a non-negative rate the discount factor is non-increasing in time, for every basis. */
    @Property(tries = 500)
    void discountFactorMonotone(@ForAll @DoubleRange(min = 0.0, max = 0.5) double r,
                                @ForAll @DoubleRange(min = 0.0, max = 50.0) double t1,
                                @ForAll @DoubleRange(min = 0.0, max = 50.0) double t2,
                                @ForAll("bases") Compounding.Basis b) {
        double lo = Math.min(t1, t2);
        double hi = Math.max(t1, t2);
        double dLo = Compounding.discountFactor(r, lo, b);
        double dHi = Compounding.discountFactor(r, hi, b);
        assertTrue(dHi <= dLo, () -> "DF rose from " + dLo + " to " + dHi);
        assertTrue(dHi > 0.0 && dLo <= 1.0);
    }

    private static Compounding.Basis basis(Compounding.Kind k, int n) {
        return new Compounding.Basis(k, n);
    }

    @net.jqwik.api.Provide
    net.jqwik.api.Arbitrary<Compounding.Basis> bases() {
        return net.jqwik.api.Arbitraries.of(basis(Compounding.Kind.SIMPLE, 0), basis(Compounding.Kind.CONTINUOUS, 0),
                basis(Compounding.Kind.PERIODIC, 1), basis(Compounding.Kind.PERIODIC, 2), basis(Compounding.Kind.PERIODIC, 12));
    }

    /** Price at a vol, invert, and recover the vol wherever vega is not negligible. */
    @Property(tries = 500)
    void impliedVolRoundTrip(@ForAll @DoubleRange(min = 20.0, max = 200.0) double f,
                             @ForAll @DoubleRange(min = -1.0, max = 1.0) double logMoneyness,
                             @ForAll @DoubleRange(min = 0.05, max = 10.0) double t,
                             @ForAll @DoubleRange(min = 0.03, max = 1.5) double v,
                             @ForAll boolean call,
                             @ForAll boolean bachelier) {
        double k = f * Math.exp(logMoneyness);
        Model m = bachelier ? Model.BACHELIER : Model.BLACK_76;
        double vol = bachelier ? v * f : v;
        // keep the option away from the flat ends where the price carries no vol information
        Assume.that(Math.abs(logMoneyness) <= 2.5 * v * Math.sqrt(t));
        Option o = option(m, call ? 1.0 : -1.0, k, t, f, 0.9);
        double price = Black.price(o, vol);
        double back = Black.implied(o, price);
        assertEquals(vol, back, 1e-7 * vol);
    }
}
