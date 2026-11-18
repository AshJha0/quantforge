# Recorded feeds

QuantForge records two kinds of public data on its own machines: daily public-rate files for the forward log, and a crypto venue's order book for the stage H studies. This page says where each comes from, what is kept, what may be published, and which dates are usable for which study. Raw recorded data is never committed to git.

## Crypto venue: Kraken spot L2 book and trades

<p class="note">Crypto venue; not equities or rates. Only aggregates and derived statistics are published.</p>

**Plain idea.** A crypto exchange publishes its order book over a free websocket that needs no account. Recording it gives a real, if unusual, limit order book: one venue, trading around the clock, in a market with its own structure. Stage H uses it for the impact proxy, walk-the-book cost curves and the book-rebuild check, and labels every result as crypto.

| Item | Value | Source |
|---|---|---|
| Venue and endpoint | Kraken spot websocket v2, public endpoint `wss://ws.kraken.com/v2`, channels `book` and `trade` | `tools/recorder/crypto_l2.py` docstring |
| Account, key, card | None. The order-by-order (L3) channel needs an API token, so QuantForge has no MBO feed | plan 11.4; [KR-L3] in `specifications/09-microstructure/order-book.md` |
| Symbols | BTC/USD, ETH/USD | `crypto_l2.py` defaults |
| Book depth | Subscribed at 100 levels per side and all 100 kept from 2026-11-17 20:15 UTC; before that, 25 subscribed and the top 20 kept | plan 11.4 (owner 2026-11-17); `crypto_l2.py` `DEPTH`, `KEEP` |
| What is written | Per symbol per UTC hour, gzip JSON lines: a 100-level snapshot once a second with the venue checksum result `ok`, trades as received, and a `gap` row on every reconnect | `crypto_l2.py` docstring; `order-book.md` "What the recording holds" |
| Raw book messages | One sample only, 2026-11-17 20:29 to 20:43 UTC (about 14 minutes, both symbols), then switched off for disk space by a `NO_RAW` file (ruling HR-11) | `order-book.md`; plan 11.4 |
| Where | `C:/Work/Claude/qf-crypto-data/kraken` by default, on the recording machine only | `crypto_l2.py` |
| Terms | Read 2026-11-12: use is for the project's own benefit, so raw data stays local and only aggregates or derived statistics are published, each labelled "crypto venue; not equities or rates" | `crypto_l2.py` docstring; plan folder `STAGE_H_DATA_SURVEY.md` |

**What the snapshot rows are.** The per-second rows are the recorder's own rebuilt book, not an independent copy of the venue's. Their link to the venue is the `ok` flag: whether the recorder's top 10 levels matched Kraken's CRC32 checksum at the last update before the row. So the stage H book check (H-2) reports "the recorder's book agreed with the venue checksum on X % of seconds", with X stated, not "the book equals the venue" (`order-book.md`, "H-2 acceptance").

**Days usable for each study.** Days before 2026-11-17 20:15 UTC hold 20 levels; a 100-level study (walk-the-book curves, the H-9 latency replay) uses only later days. The H-9 replay day is the first complete UTC day at 100 levels with no gap row (`low-latency-book.md`). The market-making study (H-18) has no signed prereg yet; when it is signed, its holdout window is checked against the recorded dates before any data is read (plan 14.10 rule 6), and this page gets the dates.

**Integrity.** The crypto files carry no hash chain today: gaps are visible as `gap` rows, and the checksum flag is per row. The daily public-data recorder below does hash every fetch into the forward log. Adding per-file hashes for the crypto data to the same log is an open item for stage H.

**To refresh or restart the recording.** `python tools/recorder/crypto_l2.py [--symbols BTC/USD ETH/USD] [--out DIR]`; it needs the `websockets` package and reconnects with backoff. To record raw messages again, remove `NO_RAW` from the data folder on a drive with about 0.5 GB a day free for two symbols (`order-book.md`, "Route to form A").

## Daily public-rate files (forward log)

`tools/recorder/record.py` fetches each enabled source in `tools/recorder/sources.json` once a day, keeps the raw bytes and the source's notice under `data/recorder/` (ignored by git), and writes the hash, size and time of each fetch to the forward log. Each source entry records its licence, the date its terms were read, what may be redistributed, and the notice that must travel with any published data. That file is the provenance record; this page does not repeat it. The sources include US Treasury par yields (US federal government work) and the Federal Reserve Bank of New York reference rates; see `sources.json` for the full list and each source's terms reading.

## Related

[Walk-the-book cost curves](../curves/walk-the-book.md), [simulators](../simulators/README.md), [order-book rebuild spec](../../specifications/09-microstructure/order-book.md), diagram H-D6 in [Diagrams](../diagrams/README.md#crypto-data-path-recorder-to-aggregate).
