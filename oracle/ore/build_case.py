"""Write an ORE 1.8.17 input set for one wave 4c case (ruling G-42).

A case is a dict: curve {times, discount_factors} (the stage G CURVE convention: ACT/365F times, log-linear discount
factors), mean_reversion, sigma, netting_sets {name: {trades: [swap...], csa: optional}}, samples, seed, grid (list of
times on the 365-day grid). A swap is {notional, fixed_rate, side PAY|RECEIVE, start_years, payment_times}. Dates are
2026-11-10 plus round(365 t) days, so every time is a whole number of days and ORE's A365 times equal the spec's times.

The floating leg uses the index QF-PAR-1Y defined here with zero fixing days, NullCalendar, A365 and no adjustment, and
ORE's par coupons, so it is the single-curve par floater of ruling G-12.

    python build_case.py <case.json> <out dir>
"""
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

ASOF = date(2026, 11, 10)


def d(t):
    return (ASOF + timedelta(days=round(t * 365))).isoformat()


def tenor_days(t):
    return f"{round(t * 365)}D"


def sim_tenors(case):
    """Dense simulation-market pillars (every 30 days to the last payment plus a year, then the curve pillars), so the
    log-linear re-interpolation of simulated curves does not bias the swap values (found on the first ORE run)."""
    last = max(t for ns in case["netting_sets"].values() for sw in ns["trades"] for t in sw["payment_times"])
    days = sorted(set(list(range(30, round((last + 1) * 365) + 1, 30)) + [round(t * 365) for t in case["curve"]["times"]]))
    return ",".join(f"{x}D" for x in days)


def write(out, case):
    inp = Path(out) / "Input"
    inp.mkdir(parents=True, exist_ok=True)
    (Path(out) / "Output").mkdir(exist_ok=True)
    cv = case["curve"]
    quotes = [(d(t), -math.log(df) / (round(t * 365) / 365)) for t, df in zip(cv["times"], cv["discount_factors"])]
    m = [f"20261110 ZERO/RATE/EUR/EUR1D/A365/{dd} {z:.15f}" for dd, z in quotes]
    m += [f"20261110 SWAPTION/RATE_NVOL/EUR/{o}/{s}/ATM 0.0100" for o in ("1Y", "5Y") for s in ("1Y", "5Y")]
    (inp / "market.txt").write_text("\n".join(m) + "\n")
    (inp / "fixings.txt").write_text("")
    q = "".join(f"<Quote>ZERO/RATE/EUR/EUR1D/A365/{dd}</Quote>" for dd, _ in quotes)
    (inp / "curveconfig.xml").write_text(f"""<CurveConfiguration><YieldCurves><YieldCurve><CurveId>EUR1D</CurveId><CurveDescription>QF</CurveDescription>
<Currency>EUR</Currency><DiscountCurve>EUR1D</DiscountCurve><Segments><Direct><Type>Zero</Type><Quotes>{q}</Quotes>
<Conventions>EUR-ZERO-CONVENTIONS</Conventions></Direct></Segments><InterpolationVariable>Discount</InterpolationVariable>
<InterpolationMethod>LogLinear</InterpolationMethod><YieldCurveDayCounter>A365</YieldCurveDayCounter><Extrapolation>true</Extrapolation></YieldCurve></YieldCurves>
<SwaptionVolatilities><SwaptionVolatility><CurveId>EUR</CurveId><CurveDescription>flat</CurveDescription><Dimension>ATM</Dimension><VolatilityType>Normal</VolatilityType>
<Extrapolation>Flat</Extrapolation><DayCounter>A365</DayCounter><Calendar>TARGET</Calendar><BusinessDayConvention>Following</BusinessDayConvention>
<OptionTenors>1Y,5Y</OptionTenors><SwapTenors>1Y,5Y</SwapTenors><ShortSwapIndexBase>EUR-CMS-1Y</ShortSwapIndexBase><SwapIndexBase>EUR-CMS-30Y</SwapIndexBase></SwaptionVolatility></SwaptionVolatilities>
</CurveConfiguration>
""")
    (inp / "conventions.xml").write_text("""<Conventions>
<Zero><Id>EUR-ZERO-CONVENTIONS</Id><TenorBased>false</TenorBased><DayCounter>A365</DayCounter><Compounding>Continuous</Compounding></Zero>
<IborIndex><Id>EUR-QFPAR-1Y</Id><FixingCalendar>NullCalendar</FixingCalendar><DayCounter>A365</DayCounter><SettlementDays>0</SettlementDays><BusinessDayConvention>Unadjusted</BusinessDayConvention><EndOfMonth>false</EndOfMonth></IborIndex>
<Swap><Id>EUR-SWAP-CONVENTIONS</Id><FixedCalendar>TARGET</FixedCalendar><FixedFrequency>Annual</FixedFrequency><FixedConvention>MF</FixedConvention><FixedDayCounter>30/360</FixedDayCounter><Index>EUR-QFPAR-1Y</Index></Swap>
<SwapIndex><Id>EUR-CMS-1Y</Id><Conventions>EUR-SWAP-CONVENTIONS</Conventions></SwapIndex>
<SwapIndex><Id>EUR-CMS-30Y</Id><Conventions>EUR-SWAP-CONVENTIONS</Conventions></SwapIndex>
</Conventions>
""")
    (inp / "todaysmarket.xml").write_text("""<TodaysMarket>
<Configuration id="default"><DiscountingCurvesId>default</DiscountingCurvesId><IndexForwardingCurvesId>default</IndexForwardingCurvesId><YieldCurvesId>default</YieldCurvesId><SwapIndexCurvesId>default</SwapIndexCurvesId><SwaptionVolatilitiesId>default</SwaptionVolatilitiesId></Configuration>
<DiscountingCurves id="default"><DiscountingCurve currency="EUR">Yield/EUR/EUR1D</DiscountingCurve></DiscountingCurves>
<IndexForwardingCurves id="default"><Index name="EUR-QFPAR-1Y">Yield/EUR/EUR1D</Index></IndexForwardingCurves>
<YieldCurves id="default"><YieldCurve name="EUR1D">Yield/EUR/EUR1D</YieldCurve></YieldCurves>
<SwapIndexCurves id="default"><SwapIndex name="EUR-CMS-1Y"><Discounting>EUR1D</Discounting></SwapIndex><SwapIndex name="EUR-CMS-30Y"><Discounting>EUR1D</Discounting></SwapIndex></SwapIndexCurves>
<SwaptionVolatilities id="default"><SwaptionVolatility key="EUR">SwaptionVolatility/EUR/EUR</SwaptionVolatility></SwaptionVolatilities>
</TodaysMarket>
""")
    (inp / "pricingengine.xml").write_text("""<PricingEngines><Product type="Swap"><Model>DiscountedCashflows</Model><ModelParameters/><Engine>DiscountingSwapEngine</Engine><EngineParameters/></Product></PricingEngines>
""")
    trades, nets = [], []
    k = 0
    for ns, spec in case["netting_sets"].items():
        for sw in spec["trades"]:
            k += 1
            dates = "".join(f"<Date>{d(t)}</Date>" for t in [sw["start_years"]] + sw["payment_times"])
            sched = f"<ScheduleData><Dates><Calendar>NullCalendar</Calendar><Convention>Unadjusted</Convention><Dates>{dates}</Dates></Dates></ScheduleData>"
            leg = lambda typ, payer, extra: (f"<LegData><LegType>{typ}</LegType><Payer>{payer}</Payer><Currency>EUR</Currency><Notionals><Notional>{sw['notional']}</Notional></Notionals>"  # noqa: E731
                                             f"<DayCounter>A365</DayCounter><PaymentConvention>Unadjusted</PaymentConvention>{sched}{extra}</LegData>")
            pay = "true" if sw["side"] == "PAY" else "false"
            rec = "false" if sw["side"] == "PAY" else "true"
            trades.append(f"""<Trade id="T{k}"><TradeType>Swap</TradeType><Envelope><CounterParty>CPTY</CounterParty><NettingSetId>{ns}</NettingSetId><AdditionalFields/></Envelope><SwapData>
{leg("Fixed", pay, f"<FixedLegData><Rates><Rate>{sw['fixed_rate']}</Rate></Rates></FixedLegData>")}
{leg("Floating", rec, "<FloatingLegData><Index>EUR-QFPAR-1Y</Index><Spreads><Spread>0.0</Spread></Spreads><IsInArrears>false</IsInArrears><FixingDays>0</FixingDays></FloatingLegData>")}
</SwapData></Trade>""")
        csa = spec.get("csa")
        if csa:
            nets.append(f"""<NettingSet><NettingSetId>{ns}</NettingSetId><ActiveCSAFlag>true</ActiveCSAFlag><CSADetails><Bilateral>Bilateral</Bilateral><CSACurrency>EUR</CSACurrency><Index>EUR-QFPAR-1Y</Index>
<ThresholdPay>{csa['threshold']}</ThresholdPay><ThresholdReceive>{csa['threshold']}</ThresholdReceive><MinimumTransferAmountPay>{csa['mta']}</MinimumTransferAmountPay><MinimumTransferAmountReceive>{csa['mta']}</MinimumTransferAmountReceive>
<IndependentAmount><IndependentAmountHeld>0</IndependentAmountHeld><IndependentAmountType>FIXED</IndependentAmountType></IndependentAmount>
<MarginingFrequency><CallFrequency>1D</CallFrequency><PostFrequency>1D</PostFrequency></MarginingFrequency><MarginPeriodOfRisk>{csa['mpor']}</MarginPeriodOfRisk><CollateralCompoundingSpreadReceive>0.00</CollateralCompoundingSpreadReceive><CollateralCompoundingSpreadPay>0.00</CollateralCompoundingSpreadPay>
<EligibleCollaterals><Currencies><Currency>EUR</Currency></Currencies></EligibleCollaterals></CSADetails></NettingSet>""")
        else:
            nets.append(f"<NettingSet><NettingSetId>{ns}</NettingSetId><ActiveCSAFlag>false</ActiveCSAFlag></NettingSet>")
    (inp / "portfolio.xml").write_text("<Portfolio>\n" + "\n".join(trades) + "\n</Portfolio>\n")
    (inp / "netting.xml").write_text("<NettingSetDefinitions>" + "".join(nets) + "</NettingSetDefinitions>\n")
    grid = ",".join(tenor_days(t) for t in case["grid"])
    (inp / "simulation.xml").write_text(f"""<Simulation><Parameters><Discretization>Exact</Discretization><Grid>{grid}</Grid><Calendar>NullCalendar</Calendar>
<Sequence>MersenneTwister</Sequence><Scenario>Simple</Scenario><Seed>{case['seed']}</Seed><Samples>{case['samples']}</Samples>{"<CloseOutLag>" + case['close_out_lag'] + "</CloseOutLag><MporMode>StickyDate</MporMode>" if case.get('close_out_lag') else ""}</Parameters>
<CrossAssetModel><DomesticCcy>EUR</DomesticCcy><Currencies><Currency>EUR</Currency></Currencies><BootstrapTolerance>0.0001</BootstrapTolerance><Measure>LGM</Measure>
<InterestRateModels><LGM ccy="default"><CalibrationType>Bootstrap</CalibrationType>
<Volatility><Calibrate>N</Calibrate><VolatilityType>HullWhite</VolatilityType><ParamType>Constant</ParamType><TimeGrid/><InitialValue>{case['sigma']}</InitialValue></Volatility>
<Reversion><Calibrate>N</Calibrate><ReversionType>HullWhite</ReversionType><ParamType>Constant</ParamType><TimeGrid/><InitialValue>{case['mean_reversion']}</InitialValue></Reversion>
<CalibrationSwaptions><Expiries>1Y</Expiries><Terms>1Y</Terms><Strikes/></CalibrationSwaptions><ParameterTransformation><ShiftHorizon>0.0</ShiftHorizon><Scaling>1.0</Scaling></ParameterTransformation></LGM></InterestRateModels>
<ForeignExchangeModels/><InstantaneousCorrelations/></CrossAssetModel>
<Market><BaseCurrency>EUR</BaseCurrency><Currencies><Currency>EUR</Currency></Currencies>
<YieldCurves><Configuration><Tenors>{sim_tenors(case)}</Tenors><Interpolation>LogLinear</Interpolation><Extrapolation>Y</Extrapolation></Configuration></YieldCurves>
<Indices><Index>EUR-QFPAR-1Y</Index></Indices><SwapIndices/><DefaultCurves><Names/><Tenors>1Y</Tenors></DefaultCurves></Market></Simulation>
""")
    (Path(out) / "ore.xml").write_text("""<ORE><Setup><Parameter name="asofDate">2026-11-10</Parameter><Parameter name="inputPath">Input</Parameter><Parameter name="outputPath">Output</Parameter>
<Parameter name="logFile">log.txt</Parameter><Parameter name="logMask">15</Parameter><Parameter name="marketDataFile">market.txt</Parameter><Parameter name="fixingDataFile">fixings.txt</Parameter>
<Parameter name="implyTodaysFixings">Y</Parameter><Parameter name="curveConfigFile">curveconfig.xml</Parameter><Parameter name="conventionsFile">conventions.xml</Parameter>
<Parameter name="marketConfigFile">todaysmarket.xml</Parameter><Parameter name="pricingEnginesFile">pricingengine.xml</Parameter><Parameter name="portfolioFile">portfolio.xml</Parameter>
<Parameter name="observationModel">None</Parameter><Parameter name="continueOnError">false</Parameter></Setup>
<Markets><Parameter name="lgmcalibration">default</Parameter><Parameter name="pricing">default</Parameter><Parameter name="simulation">default</Parameter></Markets>
<Analytics><Analytic type="npv"><Parameter name="active">Y</Parameter><Parameter name="baseCurrency">EUR</Parameter><Parameter name="outputFileName">npv.csv</Parameter></Analytic>
<Analytic type="simulation"><Parameter name="active">Y</Parameter><Parameter name="simulationConfigFile">simulation.xml</Parameter><Parameter name="pricingEnginesFile">pricingengine.xml</Parameter><Parameter name="baseCurrency">EUR</Parameter><Parameter name="storeFlows">N</Parameter><Parameter name="cubeFile">cube.csv.gz</Parameter><Parameter name="aggregationScenarioDataFileName">scenariodata.csv.gz</Parameter></Analytic>
<Analytic type="xva"><Parameter name="active">Y</Parameter><Parameter name="csaFile">netting.xml</Parameter><Parameter name="cubeFile">cube.csv.gz</Parameter><Parameter name="scenarioFile">scenariodata.csv.gz</Parameter><Parameter name="baseCurrency">EUR</Parameter><Parameter name="exposureProfiles">Y</Parameter><Parameter name="exposureProfilesByTrade">N</Parameter><Parameter name="quantile">0.95</Parameter><Parameter name="calculationType">Symmetric</Parameter><Parameter name="allocationMethod">None</Parameter><Parameter name="marginalAllocationLimit">1.0</Parameter><Parameter name="exerciseNextBreak">N</Parameter><Parameter name="cva">N</Parameter><Parameter name="dva">N</Parameter><Parameter name="fva">N</Parameter><Parameter name="colva">N</Parameter><Parameter name="collateralFloor">N</Parameter><Parameter name="rawCubeOutputFile">rawcube.csv</Parameter><Parameter name="netCubeOutputFile">netcube.csv</Parameter></Analytic></Analytics></ORE>
""")


if __name__ == "__main__":
    write(sys.argv[2], json.loads(Path(sys.argv[1]).read_text()))
