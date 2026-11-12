# Tutorial 19: hedging credit and correlation

The plain idea: a credit default swap (CDS) position has two kinds of risk. Spreads can widen a little, which changes its value a little (CS01, per basis point), or the name can default, which changes it a lot at once (jump to default, JTD). One hedge contract cannot cancel both, but two contracts of different maturities can, the same way two options can cancel delta and gamma. The second half of the tutorial does the same for a book of exchange options, whose value depends on the correlation between two assets. There the lesson is the opposite one: some instruments look different but carry the same risk, and then no number of them will do.

You will hedge a sold 7-year CDS with 3-year and 10-year CDS so that CS01 and JTD are both zero, look at the curve risk left in the buckets, hedge an exchange-option book in correlation, both vegas and both deltas, and then show that exchange options alone cannot hedge correlation separately from vega while one vanilla call can. Python first, then Rust, Java and C++. All data is synthetic: `examples/hedge_credit_i.json` and `examples/hedge_correlation_i.json`, plus two variants built in the code. Budget 15 minutes. Every number shown is a real output.

Terms: CDS, hazard rate, survival probability and recovery are in the [glossary, tutorial terms](../../GLOSSARY.md#tutorial-terms) and [Tutorial 4](tutorial-4-credit.md). Defined here: **CS01** is the change in value for a one basis point rise in the credit spread; a **bucketed** CS01 bumps one section of the hazard curve at a time; **jump to default** is the change in value if the name defaults now; an **exchange option** pays `max(S1 - S2, 0)`, the right to swap asset 2 for asset 1 (Margrabe 1978).

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`.
- For step 2, the three builds made in [Tutorial 1](tutorial-1-swap.md).

## Step 1: Python

Save the next block as `hedge19.py` and run it from the repository root (or paste it into `uv run --project python python -`). It calls `quantforge_core.credit_correlation_hedges` directly.

<!-- tutorial:run python -->
```python
import json
from datetime import date

from quantforge_core import credit_correlation_hedges as cch
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError


def inputs(name):
    with open(f"examples/{name}.json", encoding="utf-8") as f:
        return json.load(f)["inputs"]


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(v, places) for v in values)


# 1. Credit: hedge a sold 7-year CDS with 3-year and 10-year CDS, flat in CS01 and jump to default.
c = inputs("hedge_credit_i")
day = date.fromisoformat
disc = c["discount"]
discount = CurveData(day(disc["as_of"]), disc["interpolation"],
                     tuple(day(p["date"]) for p in disc["pillars"]),
                     tuple(p["discount_factor"] for p in disc["pillars"]))
hz = c["hazard"]
book = [(day(t["maturity"]), t["coupon"], t["notional"], t["side"]) for t in c["book"]]
hedges = [(day(h["maturity"]), h["coupon"]) for h in c["hedges"]]
r = cch.credit_cds(day(c["trade_date"]), discount, day(hz["as_of"]),
                   [day(p["date"]) for p in hz["pillars"]], [p["survival"] for p in hz["pillars"]],
                   c["recovery"], book, hedges, c["targets"])
print(f"book CS01 {num(r['book']['cs01'], 2)}  JTD {num(r['book']['jtd'], 2)}")
print(f"buy protection 3y {num(r['notionals'][0], 2)}  10y {num(r['notionals'][1], 2)}")
print(f"after CS01 {num(r['after']['cs01'], 2)}  JTD {num(r['after']['jtd'], 2)}")
print(f"after buckets {nums(r['after']['buckets'], 2)}")

# 2. Correlation: a book of exchange options, hedged in correlation, both vegas and both deltas.
k = inputs("hedge_correlation_i")
market = [k[x] for x in ("spot1", "spot2", "rate", "yield1", "yield2", "vol1", "vol2", "correlation")]


def positions(items):
    return [(p["instrument"], {key: v for key, v in p.items() if key != "instrument"}) for p in items]


r = cch.correlation_neutralise(*market, positions(k["book"]), positions(k["hedges"]), k["targets"])
g = r["greeks_before"]
print(f"book correlation01 {num(g['correlation01'], 4)}  vega1 {num(g['vega_1'], 2)}  vega2 {num(g['vega_2'], 2)}")
print(f"hedge {nums(r['quantities'], 4)}")

# 3. Add 300 one-year 110 calls on asset 1 to the book. Exchange options alone cannot
#    separate correlation from vega (ruling I-17); a vanilla can.
mixed = k["book"] + [{"instrument": "CALL_1", "strike": 110.0, "expiry_years": 1.0, "quantity": 300.0}]
exch = [{"instrument": "EXCHANGE", "quantity1": 1.0, "quantity2": 1.0, "expiry_years": t} for t in (0.5, 1.5)]
call = {"instrument": "CALL_1", "strike": 100.0, "expiry_years": 1.0}
for label, hedge_set in (("two exchange options", exch), ("exchange option + call", [exch[0], call])):
    try:
        r = cch.correlation_neutralise(*market, positions(mixed), positions(hedge_set),
                                       ["CORRELATION", "VEGA_1"])
        print(f"{label}: {nums(r['quantities'], 4)}")
    except QfError as e:
        print(f"{label}: {e.code}")
```

```bash
uv run --project python python hedge19.py
```

Real output, 2026-11-12, Windows 11:

<!-- tutorial:expect -->
```text
book CS01 -5634.25  JTD -5793983.80
buy protection 3y 3574641.02  10y 6476350.56
after CS01 0.00  JTD 0.00
after buckets -0.18 -1.14 -573.32 -516.02 1090.66
book correlation01 38.7002  vega1 -10062.04  vega2 -3870.02
hedge 632.6016 0.0000 0.0000 -32.6875 32.0019
two exchange options: E_SINGULAR
exchange option + call: 631.6456 -301.6491
```

### Reading the numbers

- **The credit book.** Sold protection on 10 million to 20 December 2033 with a 1% coupon, recovery 40%. Selling protection is long credit, so a wider spread loses money (CS01 -5,634.25 per basis point) and a default loses a lot (JTD -5,793,983.80). Check the JTD by hand: on default the seller pays `(1 - R) N` = 6,000,000; before that, the position was worth -206,016.20 to the seller (the spread is above the 1% coupon), so the change is -6,000,000 + 206,016.20 = -5,793,983.80.
- **The hedge.** Buy protection on 3,574,641 of the 3-year (2029) contract and 6,476,351 of the 10-year (2036). Together that is 10.05 million, close to the book's notional, as it must be to cancel a jump to default worth about `(1 - R)` per unit on each contract. The split between them is what makes the CS01 cancel as well: the 10-year contract has more CS01 per unit than the 7-year, the 3-year less.
- **What is left: curve risk.** CS01 and JTD are zero to rounding, but the bucketed CS01s are not: -573 and -516 on the 2031 and 2033 sections, +1,091 on the 2036 section. The parallel hedge is long risk at the long end and short in the middle, and the two cancel only for a parallel move. A steepening of the credit curve would still cost money. To remove it, target buckets as well, which needs one more hedge contract per bucket.
- **The correlation book.** Short 1,000 one-year exchange options and long 400 two-year ones, all on 1 unit of asset 1 for 1 unit of asset 2. A long exchange option loses value when correlation rises (the spread `S1 - S2` moves less), so this net-short book gains 38.70 per 0.01 of correlation. Both vegas are negative: the book is short spread volatility.
- **The hedge buys 632.60 six-month exchange options, and nothing of the vanillas.** That is not a fluke. A book made only of exchange options has its vega and correlation risks in fixed proportions (ruling I-17, below), and one exchange option has them in the same proportions, so it cancels all three at once; the call and the put are left at zero. The two underlyings, -32.69 of asset 1 and +32.00 of asset 2, then remove the deltas.
- **With a vanilla in the book.** Add 300 one-year 110 calls on asset 1. Their vega has no correlation part, so the proportions are broken. Two exchange options against `CORRELATION` and `VEGA_1` now give `E_SINGULAR`: their rows of the risk matrix are proportional, so they cannot be told apart. Replace one with a call on asset 1 and the solve works: 631.65 exchange options for correlation, and 301.65 calls sold to cancel the extra vega of the book's 300 calls.

### Formal statement, checked against the spec

From [`08-hedging/credit-and-correlation-hedges.md`](../../specifications/08-hedging/credit-and-correlation-hedges.md) (rulings I-15 to I-19, I-42).

Credit (I-15), per unit notional of bought protection: `pv` is the ISDA standard model value of `credit.cds.price` [O'Kane]; section hazards `h_k = ln(Q_{k-1}/Q_k) / (t_k - t_{k-1})`; the bump `eps = 1e-4/(1 - R)`, about one basis point of spread by the credit triangle `s ~ (1 - R) h`; `CS01 = (pv(h + eps) - pv(h - eps))/2` with every `h_k` shifted, `BUCKET_k` the same with one; `JTD = (1 - R) - pv`. A trade of notional `N` and side `s` has `s N` times these. `notionals` solve `G n = -book` on the targets.

Correlation: for an exchange option, `F_k = Q_k S_k e^{-q_k T}`, `s = sqrt(vol1^2 + vol2^2 - 2 rho vol1 vol2)`, `d1 = (ln(F1/F2) + s^2 T/2)/(s sqrt T)`, price `F1 N(d1) - F2 N(d2)` [Margrabe]. With `dV/ds = F1 n(d1) sqrt T`: `VEGA_1 = dV/ds (vol1 - rho vol2)/s`, `VEGA_2 = dV/ds (vol2 - rho vol1)/s`, `CORRELATION = dV/ds (-vol1 vol2/s) x 0.01`. The factors after `dV/ds` are the same for every exchange option on the pair, which is ruling I-17: exchange options alone against two of `VEGA_1`, `VEGA_2`, `CORRELATION` are `E_SINGULAR`.

The outside check (I-2): QuantLib 1.44's `IsdaCdsEngine` on bumped hazard curves for the credit cases, and `AnalyticEuropeanMargrabeEngine` with `BlackCalculator.vega` for the exchange options.

## Step 2: the same in Rust, Java and C++

`examples/tutorial_hedge_19.py` sends the four cases, `hedge.credit.cds` once and `hedge.correlation.neutralise` three times (the example and the two variants of part 3, built the same way), to the CLI you name and prints the same eight lines. It uses only the Python standard library.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorial_hedge_19.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorial_hedge_19.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorial_hedge_19.py cpp26/build/quantforge
```

Each prints the eight lines of step 1, digit for digit. The full checks are the conformance suites `hedgecredit_i` and `hedgecorr_i`.

## For practitioners

- **Hazard bump, not quote bump.** The CS01 here bumps the hazard curve by `1e-4/(1 - R)` (I-15). A desk CS01 usually re-bootstraps from quotes bumped by 1bp; the two differ by second-order terms. The input carries survival probabilities, not quotes, so a quote CS01 would be a new target.
- **Recovery is held fixed.** Neither hedged nor bumped. A recovery-rate sensitivity matters most for deep distressed names.
- **Index and basis hedges.** Only single-name CDS are hedge instruments. Hedging a single name with an index leaves the basis between them.
- **Correlation is not traded directly.** In practice correlation exposure is managed with dispersion trades or quanto and basket products; the point of part 3 holds for all of them: an instrument whose correlation and vega risks come in the same proportions as the book's cannot separate them.
- **JTD includes the accrued premium** (I-16), because `pv` does.

## Common mistakes

- **Stopping at a parallel CS01 hedge.** The buckets show what is left; a parallel hedge with mismatched maturities is a curve trade.
- **Expecting JTD and CS01 to need one contract.** Two targets need two instruments with different ratios of CS01 to JTD.
- **Reading `correlation01` per unit of correlation.** It is per 0.01.
- **Hedging correlation with exchange options alone.** It gives `E_SINGULAR` against a vega target; add a vanilla.
- **A discount curve with other interpolation.** The credit hedge needs `LOG_LINEAR_DF`, else `E_INPUT`.

## What you just did

You hedged a sold CDS in both CS01 and jump to default with two contracts, found the curve risk that a parallel hedge leaves in the buckets, hedged an exchange-option book in correlation, vega and delta, and saw from the risk matrix why exchange options alone cannot separate correlation from vega while a vanilla can. Python, Rust, Java and C++ gave the same digits.

## Try next

- Change the targets to `["BUCKET_4", "BUCKET_5"]` and see what the CS01 and JTD become.
- Hedge the 7-year book with a 7-year contract and target `CS01` only: the notional equals the book's (golden `hedgecredit_i-0002`).
- Set `correlation` to 0.9 and watch `correlation01` and the spread volatility change.
- Read [LEARN, stage I: hedging](../../LEARN.md#stage-i-hedging), then go on to [Tutorial 20](tutorial-20-cross-asset.md).

## References and further reading

The spec lists these as sources; "not opened" there means the spec authors cited them from memory.

- D. O'Kane, *Modelling Single-name and Multi-name Credit Derivatives*, Wiley, 2008, chapters 6, 8 and 9: CDS pricing, risk and hedging. Not opened per the spec; no link given.
- W. Margrabe, "The value of an option to exchange one asset for another", *Journal of Finance* 33(1), 1978, 177-186, [doi:10.1111/j.1540-6261.1978.tb03397.x](https://doi.org/10.1111/j.1540-6261.1978.tb03397.x) (paywalled).
- J. C. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter 26, exchange options. Not opened per the spec; no link given.
- ISDA, [CDS Standard Model](https://www.cdsmodel.com/): the reference implementation of the CDS pricing that `credit.cds.price` follows.
- QuantLib, [`IsdaCdsEngine`](https://www.quantlib.org/reference/class_quant_lib_1_1_isda_cds_engine.html) and [`AnalyticEuropeanMargrabeEngine`](https://www.quantlib.org/reference/class_quant_lib_1_1_analytic_european_margrabe_engine.html), the outside oracles.
- This project: [`08-hedging/credit-and-correlation-hedges.md`](../../specifications/08-hedging/credit-and-correlation-hedges.md), [`04-pricing/credit.md`](../../specifications/04-pricing/credit.md), rulings in [`stage-i-rulings.md`](../../specifications/stage-i-rulings.md).

Links checked 2026-11-12: cdsmodel.com and the two quantlib.org pages returned HTTP 200; the Wiley DOI for Margrabe returned 403 to a scripted request and its title, journal, volume and pages were confirmed through the Crossref API.
