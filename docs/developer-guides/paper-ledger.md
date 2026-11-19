# Daily paper ledger

Plan 14.8 K-1 and K-2, 12.7 Q8k. Spec: `specifications/12-platform/paper-ledger-daily.md`. Rulings: `specifications/stage-k-rulings-paper.md` (KR-70 to KR-89).

Label on every row: "paper marks on a fitted curve; not tradable". Fills are simulated. Paper trading on free data; simulated fills; no evidence of tradable profitability. The trading rule is a fixed rotation that ignores the market, so the ledger is evidence that the plumbing works and nothing else. No performance claim is made from it.

## What runs, and when

`.github/workflows/paper-ledger.yml` runs at 00:40 UTC Tuesday to Saturday and at 15:10 UTC Monday to Friday, and can be started by hand with a `dry_run` box. Each run:

1. checks out `main` (code), `forward-log` (read only) and `paper-ledger`;
2. runs `tools/paper_daily/run_day.py`, which reads the Treasury par curve the recorder already wrote to `forward-log` and appends every row that is due to `ledger/ledger.jsonl`;
3. runs `tools/paper_daily/verify_ledger.py verify` on the whole ledger and against every anchor held, and writes `ledger/summary.json`;
4. pushes to `paper-ledger`, and nothing else; it never writes to `main` or `forward-log`;
5. stamps the new head with OpenTimestamps on `paper-ledger-anchors`.

The first evening run of a business day D happens at 00:40 UTC on D+1, after the recorder's 23:30 UTC run has taken Treasury's end-of-day curve (source: Treasury's methodology page says the curve is usually up by 18:00 Eastern; read 2026-11-19). The 15:10 UTC run is a second chance and is still before the 19:30 UTC on-time cut-off.

The job makes no market-data request. FedInvest prices are not used: their site's terms and robots file do not clearly permit recording (KR-70).

## What a row holds

One row per US business day (`USGS` calendar of the library). A `DAY` row holds the five recorded par yields, the marks of four hypothetical constant-maturity par bonds, the one order the fixed rule asked for, its pre-trade estimate, limit check, simulated fills and post-trade TCA, the cash and positions, and the P&L split into carry, roll-down, curve move and fills and costs with an unexplained term that must be exactly zero. A `GAP` row marks a business day with no recorded curve. A `DAY` row written after its cut-off says `"timing": "late"` and carries no order.

## Check it yourself

```bash
git fetch origin paper-ledger paper-ledger-anchors
git show origin/paper-ledger:ledger/ledger.jsonl > ledger.jsonl
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl            # full: needs `uv` and the Python CLI
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl --no-cli   # ledger alone: chain, holdout dates, exact replay
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl --require-days 20   # the v1.0.0 gate
```

`--no-cli` skips the calendar checks and the rebuild of each day through the CLI, and the output says so (`"calendar_checked": false, "recomputed": false`). To check the anchors, copy the `anchors/` folder of `paper-ledger-anchors` and add `--anchors DIR`; `ots verify` on a `.json.ots` file checks its Bitcoin attestation, as in `forward-log-anchors.md`.

## Dry run

```bash
git fetch origin forward-log
python tools/paper_daily/run_day.py --ledger-ref origin/paper-ledger --forward-log-ref origin/forward-log --dry-run
```

This prints the rows a run would add now and writes nothing. Before the branch exists the ledger is read as empty.

## When something goes wrong

- A run that refuses prints `REFUSED: <why>` and pushes nothing. The next run tries again; a day that passes its cut-off meanwhile is written as late.
- The push does not retry after a rejection: this job is the only writer, so a rejected push means the branch changed underneath it. Look before rerunning.
- Never edit, rebase or force-push `paper-ledger`. The anchors make a rewrite visible, and a repaired ledger is no longer evidence.
- A change to `tools/paper_daily/config.json` after the first row makes every run refuse (`CONFIG`). That is deliberate: a new configuration needs a new format string, a ruling and a new ledger.
