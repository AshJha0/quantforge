# Tutorial 50: an opening auction, an FX dealer venue and a Treasury futures venue

<!-- tutorial:only python -->

The plain idea: three simulated venues for three asset classes. An equity auction collects orders and picks one price that trades the most shares. An FX dealer streams a bid and an ask and, under last look, may reject a request if the market moved. A Treasury futures venue is the existing lit matching engine run in integer ticks, with prices shown in 32nds.

You will uncross two auctions, take a quote and send three requests to the dealer, convert, close out and mark ZN and ZB futures, and run four orders through the simulated futures venue to get a P&L per trader. Budget 15 minutes.

<p class="note">Available from v0.10.0. The operations are implemented in all four builds (Python, Java, C++ and Rust); this page drives the Python build in process. Every venue output carries its label, for example "simulated venue; not a real exchange; no real FX data" (HR-94, HR-111). Nothing here is a real exchange or dealer.</p>

Terms, defined here. **Uncrossing** is choosing the auction price. **Imbalance** is buy minus sell quantity at that price (positive means buyers are left over). **Last look** is the dealer's short hold before filling; `LL_PRICE` is a reject because the mid moved past the threshold, `LL_RANDOM` a reject drawn at the stated random rate. **Variation margin** is the daily cash move from marking a futures position to the settlement price.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`.

## Step 1: run the venue goldens

<!-- tutorial:run python -->
```python
# An opening auction, an FX dealer venue with last look and a Treasury futures venue, goldens auc_h, fxv_h, fut_h.
import json

from quantforge_core.cli.main import run_case


def load(suite):
    return {c["case_id"]: c for c in json.load(open(f"datasets/golden/stage_h/{suite}.json", encoding="utf-8"))["cases"]}


cases = load("auc_h") | load("fxv_h") | load("fut_h")


def run(case_id):
    c = cases[case_id]
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": case_id, "operation": c["operation"], "inputs": c["inputs"]}))
    assert r["outputs"] == c["expected"]["outputs"], case_id
    return r["outputs"]


out = run("auc_h-0001")
print(f"auc_h-0001 uncross: price {out['price']} volume {out['volume']} imbalance {out['imbalance']}")
out = run("auc_h-0007")
print("auc_h-0007 market orders only: price", out["price"], "cancelled", out["cancelled"])
q = run("fxv_h-0001")
print("fxv_h-0001 quote around 1.08512:", q["quotes"][0]["bid"], "/", q["quotes"][0]["ask"], "|", q["label"])
for cid in ("fxv_h-0004", "fxv_h-0003", "fxv_h-0005"):
    o = run(cid)
    print(f"{cid} mid moved {o['move_pips']} pips: {o['outcome']} at {o['price']}")
print("fut_h-0001 ZN 110-16+ in ticks:", run("fut_h-0001")["ticks"])
o = run("fut_h-0005")
print(f"fut_h-0005 ZN round trip, 3 lots: pnl {o['pnl']} after fees {o['fees']}")
print("fut_h-0006 ZB variation margin:", run("fut_h-0006")["variation_margin"])
o = run("fut_h-0011")
print("fut_h-0011 venue run, fills:", [(f["taker_id"], f["maker_id"], f["price"], f["qty"]) for f in o["fills"]])
for trader in sorted(o["pnl"]):
    print(f"fut_h-0011 trader {trader}: pnl {o['pnl'][trader]} fees {o['fees'][trader]}")
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
auc_h-0001 uncross: price 10.01 volume 300 imbalance -100
auc_h-0007 market orders only: price None cancelled ['b1', 'a1']
fxv_h-0001 quote around 1.08512: 1.08502 / 1.08522 | simulated venue; not a real exchange; no real FX data
fxv_h-0004 mid moved 1 pips: FILL at 1.0852
fxv_h-0003 mid moved 4 pips: LL_PRICE at None
fxv_h-0005 mid moved 1 pips: LL_RANDOM at None
fut_h-0001 ZN 110-16+ in ticks: 7073
fut_h-0005 ZN round trip, 3 lots: pnl 134.625 after fees 6
fut_h-0006 ZB variation margin: ['-31.25']
fut_h-0011 venue run, fills: [('B1', 'S1', '110.5', '3'), ('B2', 'S2', '110.546875', '3')]
fut_h-0011 trader M: pnl -143.625 fees 3
fut_h-0011 trader N: pnl -3 fees 3
fut_h-0011 trader P: pnl 134.625 fees 6
```

### Reading the numbers

- **One price, most volume.** The auction picks 10.01, where 300 shares trade; 100 shares of sell interest at 10.01 are left over, so the imbalance is -100 (`auc_h-0001`). With only market orders there is no limit price to choose, so there is no auction and every order is cancelled (`auc_h-0007`).
- **Quotes round outward.** Around a mid of 1.08512 with a 1-pip half spread, the bid rounds down and the ask up to the 0.00001 tick (`fxv_h-0001`).
- **Last look.** A 1-pip move fills at the quoted price; a 4-pip move against the dealer is rejected (`LL_PRICE`); a supplied draw below the random reject rate is rejected even after a small move (`LL_RANDOM`). Without `u` the draw comes from `core.rng` stream `request_index`, so a run repeats exactly (HR-97).
- **Futures in ticks.** 110-16+ on ZN (tick 1/64) is 7073 ticks. Three lots bought at 110-16 and sold at 110-17+ make 140.625 before fees and 134.625 after 1.00 per contract per side (`fut_h-0004`, `0005`). A long ZB lot marked from 120-00 to 119-31 pays 31.25 (`fut_h-0006`).

## Step 2: a venue run with a P&L per trader

The plain idea: `exec.sim.fut.pnl` answers for one round trip. `exec.sim.fut.run` takes a list of orders from several traders, matches them on the simulated lit engine and says what each trader made.

The formal statement ([`rates-futures-venue.md`](../../specifications/10-execution/rates-futures-venue.md)). Each event's price is read as 32nds or a decimal and turned into ticks; a price off the contract grid is `E_DOMAIN`. Matching is `exec.sim.lit.run`, first in first out at each price. `fee_per_contract` is charged to both sides of every fill. `pnl` per trader is the sum of signed ticks x quantity x tick value, less fees, with any open position marked at the last trade price.

The worked example (`fut_h-0011`, the last four lines of the output above). On ZN, M offers 3 at 110-16 and P lifts them; P then offers 3 at 110-17+ and N lifts those. The fee is 1.00 a contract a side.

- **P** bought 3 at 110-16 and sold 3 at 110-17+, 3 ticks of 15.625 on 3 lots: 140.625 less 6 in fees is 134.625. That is the `fut_h-0005` answer, reached through the matching engine.
- **M** is short 3 from 110-16. The last trade is 110-17+, 3 ticks against M: -140.625 less 3 in fees is -143.625.
- **N** is long 3 from 110-17+, the last trade itself: 0 less 3 in fees.
- The three figures add to -12, the total fees. Trading P&L sums to zero across the traders, so only the fees are left.

Evidence: `fut_h-0011` to `0016` were added on 2026-11-19. Until then the operation had unit tests in each language and no shared golden, so agreement across the four builds was not checked. All four builds now pass them; two of the three value cases were re-derived blind (packet 3, `program/STAGE_H_BLIND_AUDIT.md`).

### The formal statement, checked against the spec

From [`10-execution/auction.md`](../../specifications/10-execution/auction.md) (HR-84), [`10-execution/fx-rfq-venue.md`](../../specifications/10-execution/fx-rfq-venue.md) (HR-87 to HR-89, HR-97) and [`10-execution/rates-futures-venue.md`](../../specifications/10-execution/rates-futures-venue.md) (HR-90 to HR-92, HR-102, HR-103).

- Auction: maximise volume over the candidate ticks, then break ties by the rules in the spec (HR-84). If the largest matched volume is 0 there is no auction: price null, volume 0, every order left as it was (HR-127). A limit off the tick grid is `E_DOMAIN`.
- Last look: reject if the mid moved by more than `threshold_pips` against the dealer (both ways when `symmetric`); otherwise reject if u < `p_random_reject`; else fill at the quote.
- Futures: ticks = price / tick on the contract grid, off-grid `E_DOMAIN`; P&L = ticks x tick value x quantity minus fees per side.
- `seed` within 0..2^53-1 and `request_index` within 0..2^32-1; outside is `E_LIMIT` in all four builds (HR-116; goldens `fxv_h-0015` to `0020`).

Evidence: the blind lane re-derived the value cases per item as listed in [`oracle/OUTSIDE_SHARES.md`](../../oracle/OUTSIDE_SHARES.md) (H-22 67 %, H-23 71 %, H-24 95 % (18 of 19) after the second rates packet, HR-114, and blind packet 3 of 2026-11-19).

## For practitioners

- **A stated toy.** The last-look thresholds and the random reject are the spec's own model, not taken from the FX Global Code or from any dealer's practice; `LL_RANDOM` stands in for validity and credit rejects (HR-119). The auction follows published call-auction rules, not one exchange's rule book: two tie-break steps of the default (the imbalance side and the final higher price) are the simulator's own (HR-119).
- **The mark is the last trade.** `exec.sim.fut.run` marks open positions at the last trade in the run, not at an exchange settlement price. For a settlement series use `exec.sim.fut.variation`.
- **Contracts.** ZN and ZB defaults only. Contracts that tick in eighths of a 32nd (2-year and 3-year notes) are not supported (HR-118).
- **Asset classes.** A dark-pool request for an asset class with no dark venue is `E_INPUT` (HR-113).

## Common mistakes

- **Reading the imbalance sign backwards.** Positive is a buy surplus.
- **Forgetting fees are per side.** A round trip of 3 lots at 1.00 per contract per side costs 6.

## What you just did

You uncrossed an auction, saw last look fill and reject, turned 32nds into ticks, P&L and variation margin, and ran a simulated futures venue to a P&L per trader.

## Try next

- Set `p_random_reject` to 0 in `fxv_h-0005` and predict the outcome.
- Run a whole session with `PHASE` events through `exec.sim.lit.run` (`datasets/golden/stage_h/ses_h.json`, HR-112).

## References and further reading

- This project: the three specs above and `09-microstructure/asset-conventions.md`; all sources in [References](../references.md).
