# Daily paper ledger

Plan 14.8 K-1 and K-2, 12.7 Q8k. Spec: `specifications/12-platform/paper-ledger-daily.md`. Rulings: `specifications/stage-k-rulings-paper.md` (KR-70 to KR-89, KR-108, and KR-200 to KR-214 from the different-model audit of 2026-11-19).

Label on every row: "paper marks on a fitted curve; not tradable". Fills are simulated. Paper trading on free data; simulated fills; no evidence of tradable profitability. The trading rule is a fixed rotation that ignores the market, so the ledger is evidence that the plumbing works and nothing else. No performance claim is made from it.

## What runs, and when

`.github/workflows/paper-ledger.yml` starts when the recorder workflow finishes, and again from two cron slots (03:00 and 06:00 UTC, Tuesday to Saturday); it can also be started by hand with a `dry_run` box. It runs only in this repository and only for `main`. Each run:

1. checks out `main` (code), `forward-log` (read only) and `paper-ledger`;
2. runs `tools/paper_daily/run_day.py`, which reads the Treasury par curve the recorder already wrote to `forward-log` and appends every row that is due to `ledger/ledger.jsonl`;
3. runs `tools/paper_daily/verify_ledger.py verify` on the whole ledger, against the recorder log (`SOURCE`) and against every anchor held; the result goes to the runner's temporary folder, not to the branch;
4. pushes `ledger/ledger.jsonl` to `paper-ledger`, and nothing else; it never writes to `main` or `forward-log`. A run with nothing due commits nothing;
5. stamps the head with OpenTimestamps on `paper-ledger-anchors` if it has no anchor yet, and upgrades older proofs so that their Bitcoin attestations reach the branch.

**Why it follows the recorder and not the clock.** The row for business day D has to exist, and be stamped, before 19:30 UTC on the next business day. GitHub starts this repository's scheduled runs hours late. Measured from the start times of the 24 scheduled runs of `recorder.yml` and `daily-workflows.yml` from 2026-11-09 to 2026-11-19 (`gh run list`, read 2026-11-19): the 23:30 UTC slot started 3.4 to 5.7 hours late, the 14:30 and 15:00 UTC slots 6.2 to 9.0 hours late; none was dropped. The recorder's evening run, which takes Treasury's end-of-day curve (usually up by 18:00 Eastern; Treasury's methodology page, read 2026-11-19), therefore lands between about 02:55 and 05:10 UTC, and this job starts when it finishes. The two cron slots start between 06:25 and 15:00 UTC under every delay measured. A slot in the afternoon (the first version had one at 15:10 UTC, called a second chance) would have started after the cut-off on every day measured, so there is none.

**On time is not taken from the row.** A row says `"timing": "on_time"` or `"late"` from the runner's own clock, and that decides whether the rule sends an order. Whether the day counts towards the 20 recorded trading days is decided from outside evidence: an anchor over the row must end in a Bitcoin block whose time, plus two hours, is before the day's cut-off (KR-200, KR-201).

The job makes no market-data request. FedInvest prices are not used: their site's terms and robots file do not clearly permit recording (KR-70).

## What a row holds

One row per US business day (`USGS` calendar of the library). A `DAY` row holds the five recorded par yields, the marks of four hypothetical constant-maturity par bonds, the one order the fixed rule asked for, its pre-trade estimate, limit check, simulated fills and post-trade TCA, the cash and positions, and the P&L split into carry, roll-down, curve move and fills and costs with an unexplained term that must be exactly zero. A `GAP` row closes a business day without a `DAY` row and says why in `cause`: `no_curve` (nothing recorded by the cut-off), `holdout` (the date is inside a preregistered study's holdout window; nothing is read for it) or `build_refused` (the row could not be built by the cut-off). A `DAY` row written after its cut-off says `"timing": "late"` and carries no order.

## Check it yourself

```bash
git fetch origin paper-ledger paper-ledger-anchors
git show origin/paper-ledger:ledger/ledger.jsonl > ledger.jsonl
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl            # full: needs `uv` and the Python CLI
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl --no-cli   # ledger alone: chain, holdout dates, exact replay
```

`--no-cli` skips the calendar checks and the rebuild of each day through the CLI, and the output says so (`"calendar_checked": false, "recomputed": false`).

The v1.0.0 gate needs three more things, and refuses to run without any of them (`GATE`): the anchors, the recorder log, and the Bitcoin block headers the anchors' proofs name.

```bash
git fetch origin paper-ledger paper-ledger-anchors forward-log
git show origin/forward-log:actions/log.jsonl > log.jsonl
git --work-tree=anchors-copy checkout origin/paper-ledger-anchors -- anchors          # a copy of the anchors folder
ots upgrade anchors-copy/anchors/*.json.ots                                           # adds Bitcoin attestations that are ready
python tools/paper_daily/verify_ledger.py heights --anchors anchors-copy/anchors      # the block heights needed, and what is still pending
# write headers.json: {"<height>": "<80-byte block header as 160 hex characters>", ...}, from a Bitcoin node or a public block explorer
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl --anchors anchors-copy/anchors \
    --forward-log log.jsonl --bitcoin-headers headers.json --require-days 20
```

The tool never fetches a header itself. It checks each one: the proof must end at the header's Merkle root, the header must meet its own proof-of-work target, and the target must be at least as hard as a fixed floor, so a made-up header fails. The output lists the days it could not prove and why (`not_proven`).

`--anchors DIR` alone checks that every anchor still matches the ledger line it names. `ots verify` on a `.json.ots` file is a second, independent check of its Bitcoin attestation, as in `forward-log-anchors.md`.

## Dry run

```bash
git fetch origin forward-log
python tools/paper_daily/run_day.py --ledger-ref origin/paper-ledger --forward-log-ref origin/forward-log --dry-run
```

This prints the rows a run would add now and writes nothing. Before the branch exists the ledger is read as empty.

## When something goes wrong

- A run that refuses prints `REFUSED: <why>`, exits 1 and pushes nothing. The next run tries again; a day that passes its cut-off meanwhile is written as late.
- A run that exits 2 did write and push rows, and turned red so that someone looks: a gap, a late day, or a day that could not be built. A day that cannot be built stops the run before its cut-off (`PROBLEM:` in the log) and becomes a `build_refused` gap after it, so one bad day never stops the ledger.
- If the anchor step fails, the rows are pushed but not stamped; the next run stamps the head. If that is after the day's cut-off, the day will not count.
- The push does not retry after a rejection: this job is the only writer, so a rejected push means the branch changed underneath it. Look before rerunning.
- Never edit, rebase or force-push `paper-ledger`. The anchors make a rewrite visible, and a repaired ledger is no longer evidence.
- A change to `tools/paper_daily/config.json` after the first row makes every run refuse (`CONFIG`). That is deliberate: a new configuration needs a new format string, a ruling and a new ledger.
