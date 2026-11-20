# End-of-day rehearsal checklist (K-6)

The plain idea: take one recorded date and run everything the daily jobs do for it, from the recorder's log to the static dashboard pages, as a dry run in a temporary folder. Each step leaves one line of evidence. The run passes only when all eight lines pass, and each step has a planted fault that must make it fail.

The script is `tools/eod/rehearse.py`; this page is its human-readable form. The steps follow the proposed spec `specifications/12-platform/soak-eod-capacity.md` section 3 (branch `k-w3-spec`; read). Where the repository has no code for a proposed step, the script uses the nearest real one; the list "Deviations from the proposed spec" in the script's docstring says where and why.

## How to run

```bash
export PYTHONUTF8=1
uv run --project python python tools/eod/rehearse.py --date YYYY-MM-DD --source synthetic
uv run --project python python tools/eod/rehearse.py --date YYYY-MM-DD --source forward-log
uv run --project python python tools/eod/rehearse.py --date YYYY-MM-DD --source synthetic --plant GAP
uv run --project python python tools/eod/test_rehearse.py
```

The output goes to `benchmarks/results/k6/eod-<date>-<source>[-plant-<FAULT>].json` unless `--out` names a file. Exit 0 means all eight steps passed.

Rules the script keeps:

- It reads the recorder log with `git show` and never fetches from a source, so a rerun on the same date reads the same rows (the copy of the log is cut at the paper ledger's on-time cut-off for the date).
- It writes nothing to `forward-log`, `curve-daily` or `paper-ledger` and starts no workflow.
- The JSON holds hashes, counts and aggregates only: no recorded row and no recorded value.
- The host label is "local laptop, not the acceptance machine" unless the environment variable `QF_HOST_LABEL` names the runner.
- The date must be after every prereg holdout window; E2 fails otherwise.
- `--source synthetic` builds an invented recorded day in the same row format as the real log. Its JSON and pages carry the label "synthetic recorded day: invented values, no market data".

## The steps

| Step | What it does | Pass rule | Planted fault (`--plant`) | Evidence written |
|---|---|---|---|---|
| E1 | Reads the log (or builds the synthetic one), cuts it at the date's cut-off, verifies the hash chain, replays every `state_sha256`, finds the date's Treasury par-yield row and rebuilds a source file from the recorded values | chain verifies, no state mismatch, the date's row present with all five tenors | `GAP`: the date's par-yield row removed from the copy; fails `CHAIN` | rows read, chain head, sha256 of the log copy and of the rebuilt source file, par row hash, count of source dates |
| E2 | Holdout check: the date against the prereg windows, and `research/holdout_scan.py` `scan_log` on the rows that carry the date | no window holds the date, no row hit | `HOLDOUT`: the date checked is the last day of a holdout window (that date is not written to the output); fails `HOLDOUT` | number of windows, studies hit, rows scanned, row hits |
| E3 | Daily curve run, dry run: `curve_core.run` on an empty ledger copy with the source file in place of the fetch, then `curve_core.verify`, then a refit of the date from the file | DAY row `ok`, every row carries the curve label, the extended copy verifies, the refit equals the row | `HASH`: one byte of the source file changed after E1; fails `INPUT_HASH` | rows built, verifier result, chain head, tau, fit RMSE and largest error (bp), sha256 of the ledger copy and summary |
| E4 | Paper ledger run, dry run: `paper_core.run` for the previous business day and then the date, then `paper_core.verify` (exact replay and a rebuild through the CLI) | DAY row for the date, the five explain terms plus unexplained sum to the day's P&L, the verifier passes | `EXPLAIN`: one explain term of the date's row off by one cent, chain rebuilt; fails `EXPLAIN` | row kinds, verifier result, explain sum check, unexplained, on-time count, sha256 of the ledger copy |
| E5 | Intraday risk on the day's book (the paper positions at the date): `risk.intraday.delta_gamma_bound` with a 1 bp shift, and `risk.curve.key_rate` per position on a curve of the E3 zero rates | every case returns `ok`; the delta-gamma output carries its label | `DOMAIN`: a position with a non-finite yield; the CLI contract refuses it (`E_PARSE`) and the step fails | positions, estimate and bound, label, key-rate cases, summed zero DV01 |
| E6 | Renders the curve page (`tools/curve_daily/site_page.py`) and the paper page into a temporary site with the site's own template and CSS | every required label verbatim, the counter equals the verifier's count, no forbidden claim word, no holdout date | `LABEL`: the paper row label removed from its page; fails `LABEL` | labels checked, counter from rows and from the verifier, claim lint result, holdout hits, sha256 of every page |
| E7 | Site checks on the rendered pages: internal links, a viewport meta on every page, and a static phone-width check (no CSS or inline width above 375 px) | no broken internal link, no page wider than 375 px | `WIDTH`: a 600 px fixed-width element on the curve page; fails `WIDTH` | pages, internal links, external links counted (not fetched), widths found |
| E8 | Archive: the checklist JSON with the sha256 of every input and output file | the file is written | none (bookkeeping) | count of inputs and outputs hashed |

A failing step stops the run; the steps after it are recorded as "not run". The JSON is written in every case, so a failed run is archived too.

## Limits

- The forward log keeps five Treasury tenors (3 Mo, 2 Yr, 5 Yr, 10 Yr, 30 Yr). The rehearsal fits those five; the scheduled curve run fits thirteen from the Treasury file. A pass here is a pass of the plumbing on the recorded data, not of the scheduled run's fit.
- No Federal Reserve file is recorded, so the curve consistency check stays pending.
- The phone-width check reads the HTML and CSS; it is not a browser render, and it does not check dark mode.
- External links are not fetched (`tools/check_links.py` needs the network).
- Timings in the JSON come from the machine named in its `host` field and are not acceptance figures.
