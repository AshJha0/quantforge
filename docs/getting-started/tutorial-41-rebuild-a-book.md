# Tutorial 41: rebuild an order book from a feed

<!-- tutorial:only python -->

The plain idea: a crypto venue's level-2 feed sends one snapshot of the book and then a stream of updates, each a price and the new total quantity resting there. Quantity zero means the level is gone. Replaying the messages in order rebuilds the book, and a checksum over the top levels lets you prove your copy equals the venue's.

You will replay two of the spec's golden feeds through `micro.book.rebuild`: a snapshot followed by a deletion, and a snapshot deeper than the requested depth. Budget 10 minutes.

<p class="note">Available from v0.10.0. The operation is implemented in all four builds; this page drives the Python build in process. Every number below is a spec golden from <code>datasets/golden/stage_h/ob_h.json</code>, and the script stops if the build disagrees with it.</p>

Terms, defined here. A **level** is one price on one side with the total quantity resting there; the feed never shows single orders. **Depth** is how many levels per side you keep (the venue's subscription depth: 10, 25, 100, 500 or 1000). The **checksum** is a CRC32 over the top ten levels written as digit strings, as the venue defines it ([KR-CRC]). Prices and quantities are **decimal strings** at the venue's precision (ruling HR-12), never floats.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.

## Step 1: replay two feeds

The script reads two golden cases, sends each to the operation through the same entry point as the `quantforge` command, checks the result equals the golden key for key, and prints the parts worth reading. CI runs this block and checks the printed lines.

<!-- tutorial:run python -->
```python
# Rebuild a level-2 book from a snapshot and updates (micro.book.rebuild), against goldens ob_h-0002 and 0003.
import json

from quantforge_core.cli.main import run_case

cases = {c["case_id"]: c for c in json.load(open("datasets/golden/stage_h/ob_h.json", encoding="utf-8"))["cases"]}


def rebuild(case_id):
    c = cases[case_id]
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": case_id, "operation": c["operation"], "inputs": c["inputs"]}))
    assert r["outputs"] == c["expected"]["outputs"], case_id  # the build equals the golden, key for key
    return c["inputs"], r["outputs"]


inp, out = rebuild("ob_h-0002")
print("ob_h-0002 update:", inp["messages"][1]["bids"], "(quantity 0 deletes the level)")
print("  bids", out["book"]["bids"], " asks", out["book"]["asks"])
print("  crc32", out["crc32"], " level changes", out["stats"]["level_changes"])
inp, out = rebuild("ob_h-0003")
print("ob_h-0003 depth", inp["depth"], ": bids kept", len(out["book"]["bids"]), " best bid", out["book"]["bids"][0],
      " truncated", out["stats"]["truncated_levels"])
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
ob_h-0002 update: [['99.0', '0.00000000']] (quantity 0 deletes the level)
  bids [['100.0', '1.00000000']]  asks [['101.0', '1.00000000'], ['102.0', '2.00000000']]
  crc32 3791984124  level changes 1
ob_h-0003 depth 25 : bids kept 25  best bid ['100.5', '3.00000000']  truncated 1
```

### Reading the numbers

- **A deletion.** The snapshot has bids at 100.0 and 99.0; the update sends 99.0 with quantity zero, so only 100.0 is left (`ob_h-0002`). One level changed, and the asks are untouched.
- **The checksum** 3791984124 is computed over the rebuilt top ten levels. On a live feed you compare it with the venue's; a mismatch means your copy has drifted and you must resubscribe.
- **Depth.** With depth 25, a new bid at 100.5 pushes the lowest of the 25 bids off the bottom of the book. The book keeps 25 levels and counts one truncation (`ob_h-0003`). The venue does not send a delete for a level that falls out of the subscribed depth; you drop it yourself.

### The formal statement, checked against the spec

From [`09-microstructure/order-book.md`](../../specifications/09-microstructure/order-book.md), rulings HR-11 to HR-17 and HR-57/HR-58.

- An update replaces the quantity at its price; zero removes the level; a delete of an absent level is counted, not an error.
- After each message each side is truncated to `depth`; the CRC32 covers the top ten levels as the venue prints them (HR-13).
- Inputs are exact decimals; a value outside the 36-digit exact range is `E_LIMIT`, never a rounded number (HR-57, HR-58).

Evidence: `ob_h-0002` to `0008` and `0010` were re-derived blind from the spec alone (DR-H2, `program/STAGE_H_BLIND_WAVE2.md`); `ob_h-0001` matches the checksum printed in the venue's documentation.

## For practitioners

- **This is a replay, not a connection.** The operation takes recorded messages; it opens no socket and holds no state between calls.
- **Gaps.** A `gap` row (a reconnect in the recording) clears the book and counts in `stats.gaps`; updates after it are ignored and counted until the next snapshot (HR-15). The rebuild never guesses the missing levels.
- **Crossed or locked books** are counted in `stats`, not repaired: they are what the feed said.

## Common mistakes

- **Parsing prices as floats.** `"100.10"` and `100.1` print differently, and the checksum is over the printed digits.
- **Keeping levels past the depth.** They stop receiving updates and go stale.

## What you just did

You rebuilt two books from a snapshot and updates, saw a deletion and a depth truncation, and read the checksum that proves a copy matches the venue.

## Try next

- [Tutorial 42](tutorial-42-match-orders.md) runs orders against a simulated lit book.

## References and further reading

- This project: [`09-microstructure/order-book.md`](../../specifications/09-microstructure/order-book.md); all sources in [References](../references.md).
