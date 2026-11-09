"""Convention mapping table for stage E spec A outside-oracle checks (plan rule 11.2.5).

Same rule as qf_oracle/convmap.py (stage D), kept in its own file so the two stage E spec sessions never
edit one generated file. `outside_e_a.py` takes every QuantLib convention object from here; the reviewed
human-readable copy is `oracle/CONVENTION_MAP_E_A.md`, written by `outside_e_a.py --write-map`.

Review state "self-reviewed 2026-11-08": the spec session read the spec section and the QuantLib 1.44
source or documentation for the object and found them equal. It is not an outside review.
"""
import QuantLib as ql

LIBRARY = "QuantLib"
VERSION = ql.__version__
REVIEW = "self-reviewed 2026-11-08"

# id: (spec reference, library object factory, note)
ROWS = {
    # E1
    "SVI.RAW": ("05-volatility/arb-free-surfaces.md raw SVI w(k) = a + b(rho(k-m) + sqrt((k-m)^2 + sigma^2)), k = ln(K/F)",
                lambda T, F, p: ql.SviSmileSection(T, F, [p["a"], p["b"], p["sigma"], p["rho"], p["m"]]),
                "QuantLib parameter order is (a, b, sigma, rho, m); variance(K) is total variance w at k = ln(K/F)"),
    "SVI.DENSITY": ("05-volatility/arb-free-surfaces.md butterfly: g(k) < 0 iff the risk-neutral density is negative",
                    lambda sec, K: sec.density(K, 1.0, 1e-4),
                    "SmileSection::density: second difference of undiscounted calls in strike, gap 1e-4; only its sign is used, on cases guarded |g| > 1e-6 and away from the far tail"),
    "VOL.CURVE": ("05-volatility/local-and-forward-vol.md forward vol: total variance linear between expiries, time ACT/365F days/365",
                  lambda ref, dates, vols: ql.BlackVarianceCurve(ref, dates, vols, ql.Actual365Fixed(), False),
                  "forceMonotoneVariance off, so QuantLib does not hide a calendar break"),
    "DC.ACT_365F": ("01-core/daycount.md ACT_365F", lambda: ql.Actual365Fixed(), ""),
    "OPT.BLACK_FORMULA": ("05-volatility/black-models.md Black-76 on the forward F = S exp((r-q)T), discount exp(-rT)",
                          lambda ot, K, F, sd, D: ql.blackFormula(ql.Option.Call if ot == "CALL" else ql.Option.Put, K, F, sd, D), ""),
    "OPT.BLACK_CALC": ("05-volatility/local-and-forward-vol.md smile dynamics: spot delta and vega of Black-Scholes with dividend yield",
                       lambda ot, K, F, sd, D: ql.BlackCalculator(ql.PlainVanillaPayoff(ql.Option.Call if ot == "CALL" else ql.Option.Put, K), F, sd, D),
                       "delta(spot) is dV/dS at fixed vol; vega(T) per unit vol"),
    "STAT.SAMPLE": ("05-volatility/local-and-forward-vol.md vol of vol: sample standard deviation, divisor n-1",
                    lambda: ql.IncrementalStatistics(), "standardDeviation uses n-1"),
    # E3
    "FX.DELTA_TYPE": ("05-volatility/fx-smile.md delta types SPOT, FORWARD, SPOT_PA, FORWARD_PA",
                      lambda dt: {"SPOT": ql.DeltaVolQuote.Spot, "FORWARD": ql.DeltaVolQuote.Fwd, "SPOT_PA": ql.DeltaVolQuote.PaSpot, "FORWARD_PA": ql.DeltaVolQuote.PaFwd}[dt],
                      "QuantLib DeltaVolQuote::DeltaType; PA = premium in foreign currency included"),
    "FX.ATM_TYPE": ("05-volatility/fx-smile.md ATM SPOT, FORWARD, DNS",
                    lambda at: {"SPOT": ql.DeltaVolQuote.AtmSpot, "FORWARD": ql.DeltaVolQuote.AtmFwd, "DNS": ql.DeltaVolQuote.AtmDeltaNeutral}[at],
                    "QuantLib AtmDeltaNeutral depends on the delta type, as the spec"),
    "FX.DELTA_CALC": ("05-volatility/fx-smile.md deltas and strikes; discount factors exp(-r T), continuous",
                      lambda ot, dtq, S, Dd, Df, sd: ql.BlackDeltaCalculator(ql.Option.Call if ot == "CALL" else ql.Option.Put, dtq, S, Dd, Df, sd), ""),
    "FX.GK": ("05-volatility/fx-smile.md Garman-Kohlhagen: flat continuous rd, rf on ACT/365F, expiry days/365",
              lambda ref, S, rd, rf, v: ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(S)),
                                                                  ql.YieldTermStructureHandle(ql.FlatForward(ref, rf, ql.Actual365Fixed(), ql.Continuous)),
                                                                  ql.YieldTermStructureHandle(ql.FlatForward(ref, rd, ql.Actual365Fixed(), ql.Continuous)),
                                                                  ql.BlackVolTermStructureHandle(ql.BlackConstantVol(ref, ql.NullCalendar(), v, ql.Actual365Fixed()))),
              "Garman-Kohlhagen is BlackScholesMertonProcess with the foreign curve as dividend curve (the SWIG wheel has no GarmanKohlhagenProcess); engine AnalyticEuropeanEngine; vega per unit vol"),
    # E2
    "TS.FLAT_CONT": ("05-volatility/heston-family.md flat continuous r, q on ACT/365F; expiry days/365",
                     lambda ref, r: ql.YieldTermStructureHandle(ql.FlatForward(ref, r, ql.Actual365Fixed(), ql.Continuous)), ""),
    "HESTON.PROCESS": ("05-volatility/heston-family.md heston {v0, kappa, theta, xi, rho}",
                       lambda rt, qt, S, h: ql.HestonProcess(rt, qt, ql.QuoteHandle(ql.SimpleQuote(S)), h["v0"], h["kappa"], h["theta"], h["xi"], h["rho"]),
                       "QuantLib argument order (v0, kappa, theta, sigma, rho); sigma = xi"),
    "HESTON.ENGINE": ("05-volatility/heston-family.md Lewis price, target 1e-8", lambda m: ql.AnalyticHestonEngine(m, 1e-13, 1000000), "adaptive Gauss-Lobatto, relative 1e-13"),
    "BATES.PROCESS": ("05-volatility/heston-family.md jumps {intensity, mean_log_jump, log_jump_vol}, compensated",
                      lambda rt, qt, S, h, j: ql.BatesProcess(rt, qt, ql.QuoteHandle(ql.SimpleQuote(S)), h["v0"], h["kappa"], h["theta"], h["xi"], h["rho"], j["intensity"], j["mean_log_jump"], j["log_jump_vol"]),
                      "QuantLib (lambda, nu, delta): nu is the mean of ln(1+J)"),
    "BATES.ENGINE": ("05-volatility/heston-family.md Bates price", lambda m: ql.BatesEngine(m, 1e-13, 1000000), ""),
    # E5
    "BSM.PROCESS": ("04-pricing/exotics.md flat continuous r, q, vol on ACT/365F; expiry days/365",
                    lambda ref, S, r, q, v: ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(S)),
                                                                         ql.YieldTermStructureHandle(ql.FlatForward(ref, q, ql.Actual365Fixed(), ql.Continuous)),
                                                                         ql.YieldTermStructureHandle(ql.FlatForward(ref, r, ql.Actual365Fixed(), ql.Continuous)),
                                                                         ql.BlackVolTermStructureHandle(ql.BlackConstantVol(ref, ql.NullCalendar(), v, ql.Actual365Fixed()))), ""),
    "OPT.TYPE": ("04-pricing/exotics.md option_type CALL, PUT", lambda ot: ql.Option.Call if ot == "CALL" else ql.Option.Put, ""),
    "PAY.DIGITAL": ("04-pricing/exotics.md CASH_OR_NOTHING pays cash, ASSET_OR_NOTHING pays S_T",
                    lambda kind, t, K, cash: ql.CashOrNothingPayoff(t, K, cash) if kind == "CASH_OR_NOTHING" else ql.AssetOrNothingPayoff(t, K), ""),
    "BARRIER.TYPE": ("04-pricing/exotics.md barrier_type", lambda bt: {"DOWN_IN": ql.Barrier.DownIn, "DOWN_OUT": ql.Barrier.DownOut, "UP_IN": ql.Barrier.UpIn, "UP_OUT": ql.Barrier.UpOut}[bt],
                     "continuous monitoring; knock-in rebate paid at expiry, knock-out rebate at the hit, as QuantLib AnalyticBarrierEngine"),
    "ENG.BARRIER": ("04-pricing/exotics.md Reiner-Rubinstein", lambda pr: ql.AnalyticBarrierEngine(pr), ""),
    "ENG.ASIAN_GEO_CONT": ("04-pricing/exotics.md continuous geometric average price (Kemna-Vorst)", lambda pr: ql.AnalyticContinuousGeometricAveragePriceAsianEngine(pr), ""),
    "ENG.ASIAN_GEO_DISC": ("04-pricing/exotics.md discrete geometric average price, no past fixings",
                           lambda pr: ql.AnalyticDiscreteGeometricAveragePriceAsianEngine(pr), "fixing dates must be whole days"),
    "ENG.LOOKBACK_FLOAT": ("04-pricing/exotics.md floating-strike lookback, continuous monitoring", lambda pr: ql.AnalyticContinuousFloatingLookbackEngine(pr), ""),
    "ENG.QUANTO": ("04-pricing/exotics.md quanto: drift reduced by rho vol fx_vol, paid in domestic at a fixed rate of 1",
                   lambda pr, ref, rf, vx, rho: ql.QuantoEuropeanEngine(pr, ql.YieldTermStructureHandle(ql.FlatForward(ref, rf, ql.Actual365Fixed(), ql.Continuous)),
                                                                        ql.BlackVolTermStructureHandle(ql.BlackConstantVol(ref, ql.NullCalendar(), vx, ql.Actual365Fixed())),
                                                                        ql.QuoteHandle(ql.SimpleQuote(rho))),
                   "process risk-free curve is the domestic rate; correlation between the asset and the FX rate in domestic per foreign"),
    "ENG.CHOOSER": ("04-pricing/exotics.md simple chooser (Rubinstein)", lambda pr: ql.AnalyticSimpleChooserEngine(pr), ""),
    "ENG.KIRK": ("04-pricing/exotics.md Kirk spread on two forwards",
                 lambda ref, F1, F2, r, v1, v2, rho: ql.KirkEngine(*[ql.BlackProcess(ql.QuoteHandle(ql.SimpleQuote(F)), ql.YieldTermStructureHandle(ql.FlatForward(ref, r, ql.Actual365Fixed(), ql.Continuous)),
                                                                                      ql.BlackVolTermStructureHandle(ql.BlackConstantVol(ref, ql.NullCalendar(), v, ql.Actual365Fixed())))
                                                                     for F, v in ((F1, v1), (F2, v2))], rho),
                 "BlackProcess: the quote is the forward"),
    "ENG.BAW": ("04-pricing/exotics.md Barone-Adesi-Whaley", lambda pr: ql.BaroneAdesiWhaleyApproximationEngine(pr), "QuantLib solves the critical price to about 1e-6"),
}


def obj(row, *args):
    """The library object for a row. Raises KeyError for an unmapped row, so no mapping can be inline."""
    return ROWS[row][1](*args)
