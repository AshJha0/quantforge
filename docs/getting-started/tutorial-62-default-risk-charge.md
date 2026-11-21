# Tutorial 62: the default risk charge, from jump to default to the bucket charge

<!-- tutorial:only python -->

The plain idea: the sensitivities charge prices small moves in credit spreads, but not the jump when an issuer defaults. The default risk charge (DRC) asks, for each position, "what would we lose if this issuer defaulted tomorrow with the standard recovery?" Longs and shorts on the same issuer cancel, but only when the short is at least as senior as the long. Shorts on other issuers in the same bucket hedge longs only partly, through a hedge benefit ratio. The result is weighted by a default risk weight that depends on the rating.

You will compute the DRC by hand on eight golden cases, one rule at a time: loss given default, the maturity weight, offsetting within an issuer, the seniority rule, the hedge benefit ratio when ratings differ, and the risk weights for unrated and defaulted issuers. Then you get the same lines from the library. Budget 15 minutes.

<p class="note">Stage K wave 2. <code>risk.frtb.drc_nonsec</code> is merged to <code>main</code> in all four builds (2026-11-20, merge 37292e4f; not in a tag; spec <code>specifications/06-risk/frtb-drc-rrao.md</code> 0.1.0; rulings KR-50 to KR-55 in <code>specifications/stage-k-rulings-w2.md</code>, most still PROPOSED). Outside share of <code>drc_k</code>: 15 of 18 value cases (83.3%; <code>oracle/OUTSIDE_SHARES.md</code>, read 2026-11-21). Every output carries the label "regulatory formula on caller inputs; not a regulatory return". Step 1 uses the standard library; Step 2 calls the library, and CI checks that it prints the lines shown under Step 1.</p>

Terms, defined here. **JTD** (jump to default) is the loss on a position if its issuer defaults: positive for a long, negative for a short. **LGD** (loss given default) is the share of notional lost: 100% for equity and non-senior debt, 75% for senior debt, 25% for covered bonds. A **bucket** is a group of issuers that may hedge each other (corporates, sovereigns, local governments). The **hedge benefit ratio** (HBR) is the share of net longs in all net positions of the bucket.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Step 1 uses the Python standard library only; it reads the inputs, never the expected values, from `datasets/golden/stage_k/drc_k.json`. Every case here is in the corporate bucket, so Step 1 does not split by bucket.

## Step 1: the eight cases by hand

```python
# FRTB DRC for non-securitisations (MAR22.9 to 22.26) restated with the standard library on golden inputs.
import json

LGD = {"EQUITY": 1.0, "NON_SENIOR": 1.0, "SENIOR": 0.75, "COVERED": 0.25}
RANK = {"COVERED": 4, "SENIOR": 3, "NON_SENIOR": 2, "EQUITY": 1}  # a short offsets longs of its rank or above
RW = {"AAA": 0.005, "AA": 0.02, "A": 0.03, "BBB": 0.06, "BB": 0.15, "B": 0.30, "CCC": 0.50, "UNRATED": 0.15,
      "DEFAULTED": 1.0}


def jtd(p):  # gross jump to default, then the maturity weight
    if p.get("cash_equity"):
        g = p["market_value"]
    else:
        g = LGD[p["seniority"]] * p["notional"] + (p["market_value"] - p["notional"])
        g = max(g, 0.0) if p["notional"] > 0 else min(g, 0.0)
    m = p["maturity_years"]
    return g * (1.0 if m >= 1 else max(m, 0.25))


def net(positions):  # per obligor: shorts by descending rank eat eligible longs in ascending rank
    longs = [[RANK[p["seniority"]], jtd(p)] for p in positions if jtd(p) > 0]
    shorts = sorted(([RANK[p["seniority"]], -jtd(p)] for p in positions if jtd(p) < 0), key=lambda s: -s[0])
    left = sorted(longs, key=lambda x: x[0])
    short_left = 0.0
    for rank, need in shorts:
        for x in left:
            if x[0] >= rank and need > 0:
                take = min(x[1], need)
                x[1] -= take
                need -= take
        short_left += need
    return sum(x[1] for x in left) + 0.0, -short_left + 0.0  # + 0.0 prints -0.0 as 0


def drc(case):
    obligors = {}
    for p in case["positions"]:
        obligors.setdefault(p["obligor"], []).append(p)
    nl, ns, wl, ws = 0.0, 0.0, 0.0, 0.0
    for name, ps in obligors.items():
        lo, sh = net(ps)
        nl, ns = nl + lo, ns + sh
        wl, ws = wl + RW[case["ratings"][name]] * lo, ws + RW[case["ratings"][name]] * -sh
    hbr = nl / (nl - ns) if nl - ns > 0 else None
    return nl, ns, hbr, max(wl - (hbr or 0) * ws, 0.0)


golden = {c["case_id"]: c["inputs"] for c in json.load(open("datasets/golden/stage_k/drc_k.json", encoding="utf-8"))["cases"]}
for cid in ("drc_k-0001", "drc_k-0002", "drc_k-0004", "drc_k-0003", "drc_k-0008", "drc_k-0005", "drc_k-0006", "drc_k-0011"):
    nl, ns, hbr, d = drc(golden[cid])
    print(f"{cid}: net long {nl:g}, net short {ns:g}, hbr {'n/a' if hbr is None else f'{hbr:.4f}'}, drc {d:.4f}")
```

Output (CI checks that Step 2 prints these lines; measured 2026-11-21 on branch `k-v1-docs-a`, Python 3.15.2 through `uv`, local laptop, not the acceptance machine):

<!-- tutorial:expect -->
```text
drc_k-0001: net long 75, net short 0, hbr 1.0000, drc 4.5000
drc_k-0002: net long 37.5, net short 0, hbr 1.0000, drc 2.2500
drc_k-0004: net long 56.25, net short 0, hbr 1.0000, drc 3.3750
drc_k-0003: net long 0, net short 0, hbr n/a, drc 0.0000
drc_k-0008: net long 0, net short -20, hbr 0.0000, drc 0.0000
drc_k-0005: net long 55, net short -55, hbr 0.5000, drc 0.0000
drc_k-0006: net long 55, net short -55, hbr 0.5000, drc 1.5125
drc_k-0011: net long 80, net short 0, hbr 1.0000, drc 16.2500
```

### Reading the numbers

- **One senior bond (drc_k-0001).** Long 100 of a BBB senior bond at par: `JTD = 0.75 x 100 + (100 - 100) = 75`. Nothing offsets it, so `HBR = 1` and `DRC = 0.06 x 75 = 4.5`, with 6% the BBB risk weight.
- **A short maturity (drc_k-0002).** The same bond with half a year left: positions under one year are weighted by their maturity, never below a quarter (MAR22.15): `0.5 x 75 = 37.5`, `DRC = 2.25`.
- **Offsetting across maturities (drc_k-0004).** Long the 5-year bond and short a 3-month bond of the same issuer and seniority. The short is weighted by 0.25 before it offsets: `75 - 0.25 x 75 = 56.25`, `DRC = 0.06 x 56.25 = 3.375`. A short that expires soon protects for a quarter of the year only.
- **The printed example (drc_k-0003).** Long 10,000,000 of an index basket in cash and short the same amount through a one-month future. The cash equity is weighted 0.25 by rule and the future's one month is floored at 0.25, so `0.25 x 10,000,000 - 0.25 x 10,000,000 = 0`: the MAR22.16 FAQ prints this answer. With nothing net long or net short, the HBR is undefined (`n/a`) and the charge is 0.
- **Seniority decides who offsets whom (drc_k-0008).** Long a senior bond of 40, short the same issuer's stock 50. A short equity may offset a long senior bond (it is junior), so `JTD 30 - 50` nets to a short of 20, and a net short alone gives `DRC = 0`. In the cookbook recipe for golden `drc_k-0007` the roles are reversed: a short senior bond cannot offset a long stock, and both stay in the bucket.
- **Hedging across issuers (drc_k-0005, drc_k-0006).** Long 100 of an A-rated senior bond priced at 80 and short 100 of another issuer's senior bond priced at 80. `JTD = 0.75 x 100 + (80 - 100) = 55` and `-55`, so `HBR = 55 / 110 = 0.5`. If the short issuer is BB (15%): `max(0.03 x 55 - 0.5 x 0.15 x 55, 0) = max(1.65 - 4.125, 0) = 0`. If it is AAA (0.5%): `1.65 - 0.5 x 0.275 = 1.5125`. Shorting a worse credit than you own wipes out the charge; shorting a better one leaves most of it.
- **Unrated and defaulted (drc_k-0011).** An unrated senior bond gets 15%: `0.15 x 75 = 11.25`. A defaulted issuer's stock gets 100%: `1 x 5 = 5`. Total 16.25.

### The formal statement, checked against the spec

From `specifications/06-risk/frtb-drc-rrao.md` 0.1.0 (MAR22.9 to 22.26 of the Basel Framework PDF of 11/11/2026, read by the spec lane 2026-11-19).

- Gross JTD (MAR22.11, 22.12): `JTD = max(LGD x notional + PnL, 0)` for a long, `min(..., 0)` for a short, `PnL = market_value - notional`; cash equity has `JTD = market_value`.
- Maturity weight (MAR22.15, 22.18, KR-52): `w = 1` for a maturity of at least one year, else `max(maturity, 0.25)`.
- Offsetting within an obligor (MAR22.19 to 22.21, KR-53): a short offsets longs of the same or a more senior rank, using the weighted JTD; shorts are served in descending rank, each against eligible longs in ascending rank.
- Bucket (MAR22.22 to 22.25): `HBR = sum net_long / (sum net_long + sum |net_short|)`; `DRC_b = max(sum RW net_long - HBR sum RW |net_short|, 0)` with RW 0.5%, 2%, 3%, 6%, 15%, 30%, 50% for AAA to CCC, 15% unrated, 100% defaulted. Total (MAR22.26): `DRC = sum_b DRC_b`, with no hedging between buckets.
- Limits (spec): guarantee substitution, the national zero sovereign weight and fund mandates are not modelled; securitisations and the correlation trading portfolio are separate operations ([Cookbook](../../COOKBOOK.md#securitisation-drc-two-tranches-of-one-pool-do-not-offset-golden-sec_k-0001)).

## Step 2: the same cases through the library

<!-- tutorial:run python -->
```python
# The same eight golden inputs through risk.frtb.drc_nonsec.
import json

from quantforge_core.cli.main import run_case

golden = {c["case_id"]: c["inputs"] for c in json.load(open("datasets/golden/stage_k/drc_k.json", encoding="utf-8"))["cases"]}
for cid in ("drc_k-0001", "drc_k-0002", "drc_k-0004", "drc_k-0003", "drc_k-0008", "drc_k-0005", "drc_k-0006", "drc_k-0011"):
    o = run_case(json.dumps({"schema_version": "1.0", "case_id": cid, "operation": "risk.frtb.drc_nonsec",
                             "inputs": golden[cid]}))["outputs"]
    nl = sum(x["net_long"] for x in o["obligors"]) + 0.0
    ns = sum(x["net_short"] for x in o["obligors"]) + 0.0  # + 0.0 prints -0.0 as 0
    hbr = o["buckets"][0]["hbr"]
    print(f"{cid}: net long {nl:g}, net short {ns:g}, hbr {'n/a' if hbr is None else f'{hbr:.4f}'}, drc {o['drc']:.4f}")
```

## For practitioners

- **The charge is not additive across buckets.** A long corporate and a short sovereign never hedge each other in the DRC, however correlated they are.
- **Hedge with a worse credit, or with a longer short.** A short on another issuer reduces the bucket charge by `HBR x RW x |JTD|`, so a short on a worse-rated issuer (a larger RW) removes more charge than the same short on a better-rated one, as drc_k-0005 and drc_k-0006 show; a short that matures inside a year counts at its maturity, at least 0.25.
- **The library takes JTD inputs as you classify them.** Seniority, bucket, rating and whether a position is cash equity are the caller's; a wrong seniority changes who may offset whom.

## Common mistakes

- **Forgetting the PnL term.** A bond bought at 80 loses `0.75 x 100 - 20 = 55` on default, not 75: the mark-to-market loss is already taken.
- **Getting the seniority rule backwards.** A short offsets longs of its own rank or above. A short stock may offset a long senior bond (drc_k-0008); a short senior bond may not offset a long stock (drc_k-0007).

## What you just did

You computed the standardised default risk charge by hand for eight golden cases, including the one printed in MAR22.16, and saw how maturity, seniority and the ratings of the hedges change it.

## Try next

- Change the BB short in drc_k-0005 to BBB and work out the charge by hand before running it: `max(1.65 - 0.5 x 0.06 x 55, 0) = 0`.
- The IMA capital charge that takes the DRC as an input: [Tutorial 59](tutorial-59-frtb-ima-pla-to-capital.md).

## References and further reading

- This project: `specifications/06-risk/frtb-drc-rrao.md`, `specifications/tables/stage_k/mar22_drc.json`, goldens `datasets/golden/stage_k/drc_k.json`, `python/quantforge_core/frtb_drc.py`.
- Basel Committee on Banking Supervision, *The Basel Framework*, MAR22 (standardised approach: default risk capital requirement), consolidated PDF generated 11/11/2026 (read by the spec lane, 2026-11-19).
