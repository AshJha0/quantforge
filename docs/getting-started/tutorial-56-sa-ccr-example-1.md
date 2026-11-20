# Tutorial 56: SA-CCR by hand, Basel Example 1 step by step

<!-- tutorial:only python -->

The plain idea: if a counterparty defaults today, a bank loses what its derivatives with that counterparty are worth now, less the collateral it holds (the **replacement cost**), plus whatever they could grow to be worth before they can be replaced (the **potential future exposure**). SA-CCR is the regulator's fixed recipe for both: no model, only the trades' sizes, maturities, directions and option deltas, a table of supervisory factors, and netting rules that let opposite trades offset fully, partly or not at all. The answer, **exposure at default** (EAD), is 1.4 times the sum.

You will compute the first worked example of the Basel Framework (CRE99 Example 1: two interest rate swaps and a swaption) from the trades to the printed EAD of 569, one step at a time. Budget 15 minutes.

<p class="note">Stage K. The operation <code>risk.saccr.ead</code> is merged to <code>main</code> in all four builds (2026-11-19; not in a tag) and registered in the CLI contract 1.17.0 (spec <code>specifications/06-risk/sa-ccr.md</code> 0.1.0, rulings KR-30 to KR-39). The five published Basel examples reproduce (<code>oracle/python/gen_stage_k_w1b.py</code>, every line "published check MATCH"). Outside share 12 of 19 value cases, 63.2% (<code>oracle/OUTSIDE_SHARES.md</code>): 5 published examples, counted through the blind packet that re-derived them (<code>program/STAGE_K_BLIND_PUB.md</code>, ruling KR-250), plus 7 blind re-derivations; the three audit cases saccr_k-0040 to 0042 have no blind check; 4 further blind matches are excluded because of a process failure (<code>program/STAGE_K_BLIND_W1B.md</code>). Step 1 restates the rule with the standard library on the golden inputs; Step 2 calls the library, and CI checks that it prints the lines shown under Step 1.</p>

Terms, defined here. A **netting set** is the trades covered by one legally enforceable netting agreement. **V** is their total market value, **C** the collateral held (after haircuts). The **replacement cost** RC is `max(V - C, 0)` when unmargined. A **hedging set** is a group of trades allowed to offset each other (for interest rates, one currency). The **adjusted notional** `d` scales an interest rate notional by its **supervisory duration** SD. The **effective notional** `D` is `d x MF x delta`, with MF the **maturity factor**. The **add-on** is the supervisory factor SF times the hedging set's aggregated effective notional. The **PFE multiplier** lets over-collateralisation reduce the PFE; it is 1 when `V - C >= 0`.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Step 1 uses the Python standard library only.

## The portfolio

USD thousands (CRE99 Example 1; Basel Framework PDF of 11/11/2026, CRE99.20 to 99.40, pp.524 to 528, read by the k-w1b lane 2026-11-19):

| Trade | What | Notional | Market value | Start, end (years) |
|---|---|---|---|---|
| 1 | 10-year swap, pays fixed (long the floating rate) | 10,000 | 30 | 0, 10 |
| 2 | 4-year swap, receives fixed (short the floating rate) | 10,000 | -20 | 0, 4 |
| 3 | bought 1-year option into a 10-year EUR swap, forward rate 6%, strike 5%, short the floating rate | 5,000 | 50 | 1, 11 |

No margin agreement, no collateral.

## Step 1: from trades to EAD

```python
# SA-CCR, Basel CRE99 Example 1 (golden saccr_k-0001), step by step with the standard library (CRE52 steps 1 to 8).
import math


def sd(s, e):  # supervisory duration, CRE52.34, floored at 10 business days
    return max((math.exp(-0.05 * s) - math.exp(-0.05 * e)) / 0.05, 10 / 250)


def phi(x):
    return 0.5 * math.erfc(-x / math.sqrt(2))


SF_IR, ALPHA = 0.005, 1.4  # Table 2 (CRE52.72): interest rate 0.5 %; alpha (CRE52.1)
# USD thousands: 10y payer swap, 4y receiver swap, bought 1y-into-10y EUR swaption (a put on the rate)
d1 = (math.log(0.06 / 0.05) + 0.5 * 0.5**2 * 1) / (0.5 * math.sqrt(1))  # supervisory vol 50 % for IR options
trades = [  # id, notional, market value, start, end, delta, hedging set
    ("1", 10_000, 30, 0, 10, 1.0, "USD"),
    ("2", 10_000, -20, 0, 4, -1.0, "USD"),
    ("3", 5_000, 50, 1, 11, -phi(-d1), "EUR"),
]
buckets = {}
for tid, n, mv, s, e, delta, hs in trades:
    d = n * sd(s, e)  # step 1: adjusted notional
    mf = 1.0  # step 2: unmargined, every maturity above one year
    eff = d * mf * delta  # step 4: effective notional
    k = 0 if e < 1 else (1 if e <= 5 else 2)  # IR maturity buckets by end date (KR-32)
    buckets.setdefault(hs, [0.0, 0.0, 0.0])[k] += eff
    print(f"trade {tid}: SD {sd(s, e):.4f} d {d:,.0f} delta {delta:+.4f} D {eff:,.0f} bucket {k + 1}")
addon = 0.0
for hs, (b1, b2, b3) in sorted(buckets.items()):
    en = math.sqrt(b1 * b1 + b2 * b2 + b3 * b3 + 1.4 * b1 * b2 + 1.4 * b2 * b3 + 0.6 * b1 * b3)
    addon += SF_IR * en
    print(f"hedging set {hs}: effective notional {en:,.0f} add-on {SF_IR * en:,.3f}")
v, c = sum(t[2] for t in trades), 0.0
mult = 1.0 if v - c >= 0 else min(1.0, 0.05 + 0.95 * math.exp((v - c) / (2 * 0.95 * addon)))
rc, pfe = max(v - c, 0.0), mult * addon
ead = ALPHA * (rc + pfe)
assert abs(ead - 569.4701409373457) <= 1e-10 * ead  # golden saccr_k-0001
print(f"AddOn {addon:,.2f} multiplier {mult} RC {rc:.0f} PFE {pfe:,.2f} EAD = 1.4 x ({rc:.0f} + {pfe:.2f}) = {ead:.2f}; printed 569")
```

Output (CI checks that Step 2 prints these lines):

<!-- tutorial:expect -->
```text
trade 1: SD 7.8694 d 78,694 delta +1.0000 D 78,694 bucket 3
trade 2: SD 3.6254 d 36,254 delta -1.0000 D -36,254 bucket 2
trade 3: SD 7.4856 d 37,428 delta -0.2694 D -10,083 bucket 3
hedging set EUR: effective notional 10,083 add-on 50.415
hedging set USD: effective notional 59,270 add-on 296.350
AddOn 346.76 multiplier 1.0 RC 60 PFE 346.76 EAD = 1.4 x (60 + 346.76) = 569.47; printed 569
```

### Reading the numbers, step by step

1. **Adjusted notional.** For interest rate trades `d = N x SD`, `SD = (exp(-0.05 S) - exp(-0.05 E)) / 0.05`. Trade 1: `(1 - exp(-0.5)) / 0.05 = 7.8694`, so `d = 78,694`. Trade 3 starts in a year: `(exp(-0.05) - exp(-0.55)) / 0.05 = 7.4856` (CRE52.34).
2. **Maturity factor.** Unmargined, `MF = sqrt(min(M, 1 year) / 1 year)`; every trade here runs beyond a year, so `MF = 1` (CRE52.48).
3. **Delta.** The payer swap is long the floating rate, +1; the receiver swap short, -1. The swaption is short the floating rate (the spec's worked example): exercised, it pays floating and receives fixed, so it is a bought put on the rate: `delta = -Phi(-d1)`, `d1 = (ln(0.06/0.05) + 0.5 x 0.5^2 x 1) / (0.5 x 1) = 0.6146`, so `delta = -0.2694` with the supervisory volatility of 50% for interest rate options (CRE52.40, Table 2).
4. **Effective notional per trade.** `D = d x MF x delta`: 78,694, -36,254 and -10,083.
5. **Hedging sets and buckets.** One hedging set per currency. Inside it, three maturity buckets by end date: under 1 year, 1 to 5 years, over 5. USD has -36,254 in bucket 2 and 78,694 in bucket 3. The offset formula `sqrt(D1^2 + D2^2 + D3^2 + 1.4 D1 D2 + 1.4 D2 D3 + 0.6 D1 D3)` lets adjacent buckets offset 70%: `sqrt(36,254^2 + 78,694^2 - 1.4 x 36,254 x 78,694) = 59,270`. EUR has only the swaption: 10,083 (CRE52.57).
6. **Add-on.** `SF = 0.5%` for interest rates: USD 296.35, EUR 50.415, total 346.76 (CRE52.72).
7. **Multiplier and PFE.** `V = 30 - 20 + 50 = 60 >= 0`, so the multiplier is 1 and `PFE = 346.76` (CRE52.23).
8. **RC and EAD.** `RC = max(60 - 0, 0) = 60`. `EAD = 1.4 x (60 + 346.76) = 569.47`. The Framework prints 569 (CRE99.40, p.528).

The paper writes `1.4 x (60 + 347) = 569`. That line carries 569.47 and prints the rounded inputs: `1.4 x 407 = 569.8` would print 570. Ruling KR-30 compares every figure at full precision, rounded to the printed digits.

### The formal statement, checked against the spec

From `specifications/06-risk/sa-ccr.md` 0.1.0 (CRE52 pp.434 to 462 read 2026-11-19 by that lane).

- `EAD = alpha (RC + PFE)`, `alpha = 1.4`; margined `EAD` capped at the unmargined `EAD` of the same trades (KR-37).
- `PFE = m x AddOn_aggregate`, `m = 1` if `V - C >= 0`, else `min{1; 0.05 + 0.95 exp((V - C) / (2 x 0.95 x AddOn))}`; 0.05 when the add-on is 0 (KR-36).
- `AddOn_aggregate` sums the five asset classes. Interest rates: per currency, buckets by end date with the middle bucket inclusive, `1 <= E <= 5` (KR-32, a reading of ambiguous text, pinned by goldens and flagged inferred). FX: per pair, `SF |sum D|`. Credit and equity: single-factor aggregation with correlation `rho` per entity. Commodities: four hedging sets.
- Scope limits (KR-39): no multiple margin agreements in one netting set, no shared margin agreements, no haircut computation (C is the caller's figure), no central counterparty floors.

### Evidence

- **Published.** `saccr_k-0001` to `0005` are CRE99 Examples 1 to 5 (printed EADs 569, 381, 5,406, 936, 1,879), with every printed intermediate asserted by the generator. One printed intermediate, CRE99.90's -7,100 for a Brent forward, is -7,099.30 at full precision; it is accepted within one unit as a source rounding and recorded as such (KR-31), not hidden.
- **Blind.** `saccr_k-0006` to `0016` were re-derived by a blind lane (a different model, packet only, results frozen with their hash before the compare): 11 of 11 MATCH. Four of them (0006, 0013, 0015, 0016) are excluded from the count because the lane had read the unstripped spec once before the packet was built, which showed output facts for those cases. The five published examples count only through a later blind packet that re-derived them, because a printed figure checks some outputs at print precision only (ruling KR-250, `program/STAGE_K_BLIND_PUB.md`). Three cases added by the audit, saccr_k-0040 to 0042, have no blind check. So the counted share is 5 + 7 = 12 of 19 value cases, 63.2%, against the 60% floor (`oracle/OUTSIDE_SHARES.md`). Counting the leaked four would give 16 of 19; the record does not claim that.
- **Recorded.** The goldens' `verified_by` and the spec's acceptance line show the counted share, 12 of 19 (the 12 of 16 line of 2026-11-19 and the earlier 31% line, written before the blind lane ran, is superseded).

## Step 2: the same example through the library

This block calls the library on the goldens in `datasets/golden/stage_k/`. It was turned on at integration (2026-11-19) and printed the same lines as Step 1; CI now checks them.

<!-- tutorial:run python -->
```python
# Golden saccr_k-0001 through risk.saccr.ead, printed in the order of Step 1.
import json

from quantforge_core.cli.main import run_case

c = {c["case_id"]: c for c in json.load(open("datasets/golden/stage_k/saccr_k.json", encoding="utf-8"))["cases"]}["saccr_k-0001"]
r = run_case(json.dumps({"schema_version": "1.0", "case_id": c["case_id"], "operation": c["operation"], "inputs": c["inputs"]}))
out = r["outputs"]
assert abs(out["ead"] - c["expected"]["outputs"]["ead"]) <= 1e-10 * out["ead"]
for t, i in zip(out["trades"], c["inputs"]["trades"]):
    e = i["end"]
    k = 0 if e < 1 else (1 if e <= 5 else 2)
    print(f"trade {t['id']}: SD {t['supervisory_duration']:.4f} d {t['adjusted_notional']:,.0f} delta {t['delta']:+.4f} "
          f"D {t['effective_notional']:,.0f} bucket {k + 1}")
for hs in out["hedging_sets"]:
    print(f"hedging set {hs['key']}: effective notional {hs['addon'] / 0.005:,.0f} add-on {hs['addon']:,.3f}")
print(f"AddOn {out['addon_aggregate']:,.2f} multiplier {out['multiplier']} RC {out['rc']:.0f} PFE {out['pfe']:,.2f} "
      f"EAD = 1.4 x ({out['rc']:.0f} + {out['pfe']:.2f}) = {out['ead']:.2f}; printed 569")
```

## For practitioners

- **Netting is where the number is decided.** Trades 1 and 2 net from 114,948 of gross effective notional to 59,270 inside USD, because they sit in adjacent buckets. In separate currencies they would not offset at all.
- **The option's delta is supervisory.** It uses a fixed 50% volatility, not the market's; two banks with the same trade get the same delta.
- **Collateral and the multiplier.** With enough excess collateral `V - C` goes negative and the multiplier falls towards 0.05; it never reaches 0, so the PFE never vanishes (`saccr_k-0016`, exactly offsetting FX, multiplier 0.05).

## Common mistakes

- **Bucketing by maturity instead of end date.** For interest rates the bucket is by the end date `E` of the underlying, so the 1-into-10 swaption goes to "over 5 years", not "under 1 year".
- **Rounding before the end.** CRE99.20 says intermediates are not rounded; rounding the add-on to 347 first gives 570, not 569.

## What you just did

You computed Basel's first SA-CCR example from three trades to an EAD of 569.47, saw where netting removes half the swap exposure, and read what the published and blind checks cover and what they do not.

## Try next

- Set `ir_offset` to false (golden `saccr_k-0006`): the USD effective notional becomes `|D1| + |D2| + |D3| = 114,948`. Predict the EAD before computing it.

## References and further reading

- This project: `specifications/06-risk/sa-ccr.md`, `specifications/06-risk/sa-ccr-parameters.json`, `specifications/stage-k-rulings-w1b.md`, `program/STAGE_K_W1B_HANDOVER.md`, `program/STAGE_K_BLIND_W1B.md`.
- Basel Committee on Banking Supervision, *The Basel Framework*, CRE52 (standardised approach to counterparty credit risk) and CRE99 (application guidance, Examples 1 to 5), consolidated PDF generated 11/11/2026 (read by the k-w1b lane, 2026-11-19).
- Basel Committee on Banking Supervision, *The standardised approach for measuring counterparty credit risk exposures*, BCBS 279, March 2014, Annex 4a (read in a browser by an earlier lane, 2026-11-15; not on disk).
