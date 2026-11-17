# Stage H rulings, wave 1b (spec lane): DRAFT

DRAFT written 2026-11-17, after v0.9.0. Not normative until the stage H coordinator confirms it. Separate file from `stage-h-rulings-w1.md` (HR-1 to HR-10) so the branches merge without conflict; numbering continues. Covers `09-microstructure/order-book.md`, `09-microstructure/low-latency-book.md`, `10-execution/lit-matching.md`, `10-execution/dark-pool.md`, `10-execution/smart-order-router.md`. Append-only once confirmed.

| # | Point | Ruling (proposed) |
|---|---|---|
| HR-11 | Recorder input for H-2 and H-9 | **Owner decisions 2026-11-17.** First "yes, record raw": raw Kraken book messages were recorded from 20:29 UTC under `<SYMBOL>-raw/` (recorder commit 547e6690, branch `hedge-followups-0918`). Then **reversed for disk space**: about 0.5 GB a day against about 29 GB free, so raw recording is off from 20:43 UTC (a `NO_RAW` file in the data folder; the code can still record raw). Result: H-2 and H-9 run in form B on the per-second 100-level snapshots, labelled. The 14-minute raw sample (20:29 to 20:43 UTC, both symbols, about 5.7 MB) is kept and used only as a labelled form A demonstration, not pooled with form B and not counted as an H-2 day. Route to form A: re-enable raw recording with the data folder on a larger drive; raw days then run in form A and become the H-2 result |
| HR-12 | Number representation | Prices and quantities are decimal strings at the venue's precision in inputs and outputs; internally integer ticks and lots. Floats never touch the checksum path ([KR-CRC]) |
| HR-13 | Checksum | Kraken v2 book checksum exactly as [KR-CRC], CRC32 IEEE (`zlib.crc32`); the variant is inferred from recorded `ok = true` rows and from ob_h-0001 |
| HR-14 | Crossed and locked | Reported events, never errors; counted per day and published |
| HR-15 | Resync | No sequence numbers exist; a gap row or update-before-snapshot clears or ignores until the next snapshot; a checksum mismatch is counted and the next snapshot recorded as a resync. No invented recovery |
| HR-16 | MBO | Not available on any public, keyless crypto feed we may use (Kraken level3 needs a token); MBO only inside the simulated venues |
| HR-17 | `E_LIMIT` | `micro.book.rebuild` 50,000,000 messages; venue simulators 10,000,000 events; SOR 64 venues, 10^6 samples |
| HR-18 | H-9 scope | Same answers as `micro.book.rebuild`; speed is measured, never traded for correctness (H-9(d)) |
| HR-19 | Update complexity | O(L log N) worst case per message, O(L) expected near the touch; queries O(1) (`best_*`, `qty_at` expected) and O(n) (`top(n)`) |
| HR-20 | Hot-path units | Integer ticks and lots, pre-decoded fixed-size messages; parsing excluded from timing |
| HR-21 | Timing method | Per-message clock pairs, clock overhead published not subtracted; batch timing added if overhead exceeds half the p50; unpaced replay, so no coordinated-omission correction |
| HR-22 | Allocation gate | C++ and Rust: counting allocator, exactly 0 after warm-up. Java: JFR and GC logs, miss published with bytes per message. Python: reported only |
| HR-23 | Targets | L1 to L6 written to `benchmarks/targets.md` in their own commit before any H-9 run |
| HR-24 | CI threshold | p99 threshold = max(20%, 3 x CV of 10 runner baselines); median of 3 PR runs; baseline refreshed only by its own commit |
| HR-25 | Lit order types | LIMIT, MARKET, IOC, FOK, ICEBERG, POST_ONLY, PEG_MID, PEG_PRIMARY as in `lit-matching.md`; GTD and auctions out of wave 1b |
| HR-26 | Post-only crossing | Rejected (not repriced) |
| HR-27 | Hidden priority | Displayed first by seq, then pegged non-displayed, then iceberg hidden; FOK counts hidden quantity |
| HR-28 | Peg rounding | Mid pegs round away from crossing (bid down, ask up to the tick) |
| HR-29 | Determinism | Same event list gives byte-identical output in all four languages |
| HR-30 | Fees | Signed per unit notional: taker fee charged, maker rebate paid; venue schedules are inputs, no real venue's fees claimed |
| HR-31 | Outside checks for simulated venues | **Decided by the owner 2026-11-17 (option C).** No public reference engine publishes outputs, so value cases of the lit engine, dark pool and router count as outside-checked by blind re-derivation under DR-H2 (a second lane computes from the inputs alone, without seeing ours), or by a real outside tool where one exists (`lifelines` Kaplan-Meier; Monte Carlo of the same model for the Laplace inversion). Venue documentation backs each rule (cited per case) but is not itself counted as an outside check. Lit, dark and SOR stay in stage H; the section 15 rule of 60% applies per item as usual |
| HR-32 | Dark crossing price | Mid of the supplied lit book, on a half-tick grid; no crossing when the lit book is locked, crossed or one-sided |
| HR-33 | Minimum quantity | Per fill, not cumulative |
| HR-34 | Conditionals | Stylised: invitation, firm-up with probability p_firm after a delay, suspension on failure; no venue mechanics claimed |
| HR-35 | Laplace inversion | Gaver-Stehfest with 14 terms in double precision, checked by Monte Carlo; tolerance stated per case |
| HR-36 | Leakage model | Informed fraction alpha on the side of a planted jump J; markouts must recover alpha J within 3 SE |
| HR-37 | Effective rebate | r_k - as_k as in [CK] section 2.3; dark fills earn the half spread at mid |
| HR-38 | Integer sizes | Router outputs integer lots; continuous [CK] solution rounded by exhaustive search over the floor/ceiling neighbours |
| HR-39 | Golden method | `SAMPLE_AVERAGE` on stated samples is the golden definition; stochastic approximation is property-tested against it |
| HR-40 | Router scoring | Router vs best single venue reported with paired SE; a result, not a gate |
| HR-41 | Recorded-row golden | **Decided by the owner 2026-11-17.** `ob_h-0009` leaves the goldens: a transformed row loses Kraken's checksum, and raw rows may not be published. The check against Kraken's real checksums becomes a local-only test on the recorded files, with counts published and rows not |
