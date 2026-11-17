# Order book rebuild from the Kraken L2 feed (DRAFT)

Spec version 0.1.0 (DRAFT, stage H wave 1b). Status: Specified, not implemented. Rulings HR-11 to HR-17 (`stage-h-rulings-w1b.md`). Plan items 14.7 H-2 (book equals the venue snapshot at every checkpoint; crossed or gapped sequences detected and counted), 11.4 (depth 100 from 2026-11-17 20:15 UTC), 14.7 H-9(d) (the same check runs on the latency replay).

**Plain idea.** Keep one price-to-quantity map per side. A snapshot replaces the book; an update sets a level's quantity, or removes it when the quantity is zero; after every message, drop the levels beyond the subscribed depth. At each checkpoint, compare our top levels with what the venue says the book is.

## Sources

- [KR-BOOK] Kraken, "Book (Level 2)", WebSocket v2 API docs, https://docs.kraken.com/api/docs/websocket-v2/book, read 2026-11-17. Evidence class: venue documentation, read. Verified: subscribe `depth` is one of 10, 25, 100, 500, 1000 (default 10); messages carry `type` `snapshot` or `update`, `data[]` with `symbol`, `bids[]`, `asks[]` (`price`, `qty`), `checksum` (CRC32 of the top 10 bids and asks) and `timestamp` (RFC 3339); the page says one update message can change the same price level more than once, and that updates must be processed in order. **No sequence number is documented**; the channel has no `seq` field.
- [KR-CRC] Kraken, "Book checksum (WebSocket v2)", https://docs.kraken.com/api/docs/guides/spot-ws-book-v2, read 2026-11-17. Evidence class: venue documentation, read. Verified: `qty` 0 removes the level; after each update the client truncates its book to the subscribed depth, because the venue sends no zero for levels that fall out of scope; the checksum covers the top 10 levels each side whatever the subscription depth, asks ascending then bids descending, each price and quantity with the decimal point and leading zeros removed, concatenated and passed to CRC32 as an unsigned 32-bit integer; worked example result 3310070434; prices and quantities must be parsed as decimal or string, not float; all level updates in a message are applied before the checksum is computed. Not stated: the CRC32 polynomial (the recorder uses `zlib.crc32`, the IEEE 802.3 variant, and its `ok` flag has been true on recorded data, so the variant is inferred, evidence class "inferred from our recordings"); what to do on a mismatch; what happens when a truncated level re-enters the top N.
- [KR-L3] Kraken, "Orders (Level 3)", https://docs.kraken.com/api/docs/websocket-v2/level3, read 2026-11-17. Verified: the order-by-order channel "is authenticated", needing an API token. The plan forbids accounts and keys (11.4), so **QuantForge has no MBO feed**; MBO is specified only for the simulated venues (`10-execution/lit-matching.md`).
- [REC] `tools/recorder/crypto_l2.py` on `main` at v0.9.0 (DEPTH 25, KEEP 20) and at commit 4d0c8142 on branch `hedge-followups-0918` (DEPTH 100, KEEP 100, owner 2026-11-17, not yet on `main`). Read 2026-11-17. Evidence class: our code, read.

## What the recording holds (important limit)

The recorder applies every websocket message to an in-memory book but **writes only a once-a-second top-N snapshot** (`k = "book"`), the trades as received, and a `gap` row per reconnect. Raw update messages are not stored. So on today's files:

- the H-2 "book equals the venue snapshot at every checkpoint" check cannot be run from recorded files, because there is no independent feed to rebuild from: the snapshot rows are the recorder's own book;
- the `ok` flag is the only venue-side evidence: it says the recorder's book matched Kraken's checksum at the last update before the snapshot row.

This spec therefore defines two inputs, and ruling HR-11 asks the owner to approve a recorder change (record raw messages) so that the full H-2 check and the H-9 replay are possible. Until then, H-2 runs in **form B** below and the report says so.

| Form | Input | Checkpoint | Availability |
|---|---|---|---|
| A (target) | raw `book` messages (`snapshot`, `update`) as received, each with receive time and venue checksum, one file per symbol-hour | every message carrying a checksum: CRC32 of our top 10 against the venue's; every once-a-second recorder snapshot: full top-N equality | needs the HR-11 recorder change; days from the change onward |
| B (now) | once-a-second snapshot rows | each row: our checksum of the row's top 10 recomputed and the `ok` flag counted; consecutive rows used only for a differenced stream (below) | all recorded days; 20 levels before 2026-11-17 20:15 UTC, 100 after |

**Differenced stream (form B, for H-9 only).** Between consecutive snapshot rows, the set of level changes (new, changed, removed price levels, with a removal also implied for a price that left the top N) is a synthetic update message whose application to the earlier row must give the later row exactly. It is labelled "snapshot-differenced stream; not the venue's message sequence": it under-counts updates (many venue messages per second collapse into one) and cannot show intra-second crossing.

## `micro.book.rebuild`

Inputs:
- `messages`: list of `{"type": "snapshot" | "update", "bids": [[price, qty], ...], "asks": [...], "checksum": u32 | null, "t": RFC3339}`; prices and quantities as decimal strings (HR-12).
- `depth`: one of 10, 25, 100, 500, 1000 (the subscribed depth, so the truncation rule is exact).
- `price_decimals`, `qty_decimals`: the pair's precision from Kraken's public AssetPairs call, recorded with the day (needed for the checksum string).
- `checkpoints`: optional list of `{"t": ..., "bids": [...], "asks": [...]}` snapshots to compare against (form A, recorder rows).

Outputs:
- `book`: final `bids` (descending), `asks` (ascending), each at most `depth` levels, decimal strings.
- `stats`: `messages`, `snapshots`, `updates`, `level_changes`, `deletes_of_absent_level`, `truncated_levels`, `checksum_checked`, `checksum_failed`, `checkpoint_checked`, `checkpoint_failed`, `crossed`, `locked`, `gaps`, `resyncs`.
- `events`: list of `{"i": message index, "kind": "CHECKSUM_FAIL" | "CHECKPOINT_FAIL" | "CROSSED" | "LOCKED" | "GAP" | "UPDATE_BEFORE_SNAPSHOT", "detail": ...}`, capped at 10,000 with a count of the rest.

Algorithm (normative):
1. `snapshot`: clear both sides, insert every non-zero level, truncate, then check.
2. `update`: for each level in message order, `qty == 0` removes the price (a missing price counts in `deletes_of_absent_level` and is not an error; [KR-CRC] says nothing about it and the venue's truncation makes it legitimate), else sets the price's quantity (replace, not add). After all levels of the message: truncate each side to `depth` (count in `truncated_levels`), then check.
3. Check, after the whole message: if `checksum` is present, compute it per [KR-CRC] on our top 10 and compare (HR-13); best bid >= best ask is `CROSSED`, equal is `LOCKED` (HR-14).
4. `update` before any `snapshot`, or after a gap row, is `UPDATE_BEFORE_SNAPSHOT`: ignored and counted, until the next snapshot (HR-15).
5. A `gap` row (reconnect) clears the book and counts in `gaps`; a checksum failure sets `resyncs += 1` only if the caller marks the next snapshot as a resubscribe. The rebuild never invents a recovery the venue does not document.

Errors: malformed message or non-decimal price `E_SCHEMA`; negative quantity, non-positive price or `depth` not in the list `E_DOMAIN`; more than 50,000,000 messages `E_LIMIT` (HR-17). Checksum failures and crossed books are **reported, not errors**: a replay over a day must count them, not stop.

## H-2 acceptance (as fixed here, before any run)

On every recorded day used for H-1 (at least 20 at the tag), per symbol:
- Form A days: `checksum_failed == 0` and `checkpoint_failed == 0`; any failure is listed with its message index and the day fails.
- Form B days: the recomputed checksum of every row's top 10 equals the result implied by its `ok` flag for rows with `ok = true`; the count of `ok = false` rows, crossed rows and gap rows is published per day. Pass means "the recorder's book agreed with the venue checksum on X% of seconds", with X stated, not "the book equals the venue".
- Crossed and locked counts are published; they are a property of the feed or of our rebuild, and form A separates the two (a crossed book with a passing checksum is the venue's).

## Limit cases
- Depth 10 subscription: the checksum covers the whole book.
- Days before 2026-11-17 20:15 UTC hold 20 levels; a 100-level replay uses only later days (11.4).
- A level re-entering the top N after truncation arrives as an ordinary update; if the venue never resends it, our book has a hole below the top 10 that the checksum cannot see. Form A's once-a-second full top-N checkpoint is the only detector; the count of such mismatches below level 10 is published separately from top-10 failures.
- Timestamps are the venue's; the recorder's receive time is kept for latency-free ordering checks only. Message order is file order; out-of-order timestamps are counted, not reordered.

## Golden plan (no goldens yet)
| Case | Content | Expected | Check |
|---|---|---|---|
| ob_h-0001 | [KR-CRC] worked example levels | checksum 3310070434 | OUTSIDE-CHECKED: venue's printed value |
| ob_h-0002 | snapshot then update with `qty` 0 on a present level | level removed | hand |
| ob_h-0003 | update inserting a 26th bid at depth 25 | worst bid dropped, `truncated_levels = 1` | hand, [KR-CRC] rule |
| ob_h-0004 | same price twice in one update | last value wins | [KR-BOOK] statement |
| ob_h-0005 | update before snapshot | ignored, counted | HR-15 |
| ob_h-0006 | best bid = best ask, then bid > ask | `LOCKED`, then `CROSSED`, both counted, no error | HR-14 |
| ob_h-0007 | delete of an absent price | counted, book unchanged | hand |
| ob_h-0008 | gap row mid-stream | book cleared, `gaps = 1` | HR-15 |
| ob_h-0009 | 5 recorder rows (anonymised: prices shifted, quantities scaled, only the transform published) with `ok = true` | recomputed checksum equal for all | OUTSIDE-CHECKED: Kraken's live checksum at recording time |
| ob_h-0010 | price string "0.00012300" at 8 decimals | checksum component "12300" | [KR-CRC] formatting rule |

Outside checks: 0001 and 0009 (venue checksum), 0010 (venue rule). Case 0009 needs a terms check: raw rows are not published (11.4), so the golden is a transformed, non-reversible derivative; if that is not allowed, it moves to a local-only test and the outside share is recomputed.

## Limitations
MBP only; Kraken's MBO channel needs a key and is out of scope. No sequence number, so a dropped websocket message is detected only by the checksum. Crypto venue; not equities or rates.
