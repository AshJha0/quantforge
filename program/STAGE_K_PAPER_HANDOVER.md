# Stage K round 1: paper-ledger lane handover (2026-11-19)

Branch `k-paper`. Plan 14.8 K-1, K-2; 12.7 Q8k; 14.10 rules 1 and 6. Reviewer: none: self-assessment; no second review (owner decision 2026-11-18).

Label on every row: "paper marks on a fitted curve; not tradable". Fills are simulated; the pre-trade estimate uses placeholder weights. The trading rule is a fixed rotation that ignores the market: the ledger is plumbing evidence and no performance claim is made from it.

## What is built

| Item | Where | Evidence |
|---|---|---|
| Spec, fixed before any scheduled run | `specifications/12-platform/paper-ledger-daily.md` | acceptance table P1 to P11 in the spec |
| Rulings KR-70 to KR-89 (proposed) | `specifications/stage-k-rulings-paper.md` | need the coordinator's confirmation |
| Daily job | `tools/paper_daily/core.py`, `run_day.py`, `config.json` | `python/tests/test_paper_daily.py`, 40 tests, measured 2026-11-19 on the local laptop (Windows, Python 3.15), not on CI |
| Verifier and anchor tool | `tools/paper_daily/verify_ledger.py` | same test file; planted faults listed under P7 |
| Workflow | `.github/workflows/paper-ledger.yml` | not triggered; `tools/check_job_names.py` passes (59 jobs, 0 problems) |
| Guide | `docs/developer-guides/paper-ledger.md` | |

## Data decision (KR-70)

FedInvest end-of-day prices are **not** used. Read 2026-11-19 (web-fetch agent, URLs in the spec): the TreasuryDirect robots file disallows every agent except `usasearch`; the site terms allow viewing, downloading and printing "for non-commercial personal use only" and reserve reproduction to written consent; no page found permits automated fetching, storing or republishing. So the plan's stated K-1 fallback is used: constant-maturity exposures marked on a curve through the five Treasury par yields the recorder already keeps on `forward-log`. The job makes no market-data request of its own. A DAY row repeats that day's five par yields, which the forward-log rows already publish, and names the source row by hash.

The coordinator may want to confirm one thing: lane rule "never publish raw recorded market data rows" against these five parsed values per day. They are the recorder's own published parsed values for a series it treats as public domain (`sources.json`: "believed yes, unconfirmed"), not a raw file. If that is not acceptable, the alternative is to keep only the forward-log row hash in the ledger; the exact replay would still work (it reads marks, not yields) but the rebuild of the marks would then need the forward log beside the ledger.

Decided at integration (2026-11-19, ruling KR-108): `origin/forward-log` publishes the five parsed values themselves (for example row 346, 2026-11-18), as `docs/developer-guides/recorder-actions.md` states for public-domain sources, so the DAY rows keep the values; the spec cites the precedent. No code, test or format change.

## What runs when

- `paper-ledger.yml`: 00:40 UTC Tuesday to Saturday and 15:10 UTC Monday to Friday, plus `workflow_dispatch` with a `dry_run` input. It starts by itself once the workflow file is on `main`. **It has not been triggered and no branch has been pushed.**
- The recorder's 23:30 UTC run must have written the day's curve first. If it has not, the 00:40 run writes nothing and the 15:10 run picks the day up, still on time (cut-off 19:30 UTC on the next business day).
- Ledger: branch `paper-ledger`, file `ledger/ledger.jsonl`, with `ledger/summary.json` beside it. Anchors: branch `paper-ledger-anchors`, folder `anchors/`.
- Calendar: the library's `USGS` calendar decides which dates get a row.

## Dry run for the coordinator

```bash
git fetch origin forward-log
python tools/paper_daily/run_day.py --ledger-ref origin/paper-ledger --forward-log-ref origin/forward-log --dry-run
```

Run in this worktree on 2026-11-19 at 12:10 UTC it printed the label line, the statement line, then

```
2026-11-18: DAY on_time pnl -293.75 nav 9999706.25 orders 1 recorded_trading_days 1
{"dry_run": true, "gaps": 0, "head": "40dff9a5...", "last_date": "2026-11-18", "late_days": 0, "now": "2026-11-19T12:10:30Z", "recorded_trading_days": 1, "records": 2, "rows_added": 2}
```

and the two rows (genesis, and the day row for 2026-11-18: a BUY of 26,500 units of `UST-CM-2Y`, partly filled). The head hash and the fill differ from run to run before the ledger exists, because the genesis row holds the run time and the book seed depends on the previous row's hash. A real write to a temporary file, a full verify, a `--require-days 20` check (failed with `DAYS`, as it should with 1 day) and a second run (nothing due) were also done locally.

## How to verify the real ledger later

`docs/developer-guides/paper-ledger.md` has the three commands. The v1.0.0 gate is `verify_ledger.py verify --ledger ledger.jsonl --anchors DIR --require-days 20`.

## Not done, not verified

- **0 of the 20 trading days are recorded.** The earliest the 20th on-time day can be written is 20 US business days after the workflow reaches `main`; every late day or gap pushes that out by one.
- The workflow has never run on a GitHub runner. Its shell steps follow `recorder.yml` but are untested there; the first `workflow_dispatch` with `dry_run` ticked is the test, and it pushes nothing.
- The golden hashes (`pl_k-0001` to `0003`) were computed on Windows. They pass through binary64 `pow` rounded to 6 and 10 decimals; agreement on the Linux CI runner is expected but not verified. If they differ there, that is a finding to report, not a tolerance to loosen.
- The rebuild of each day has been run on the Python CLI only, not on the Java, C++ or Rust CLI.
- No outside tool has checked the marks. The bond operation they use has its own goldens; the composition here has only the hand-checked worked example in the spec.
- The spec's reading of the Treasury terms is a reading, not legal advice.

## Library changes needed: none made, three asked for

No library operation was added or changed. The job composes `core.calendar.is_business_day`, `core.interp.evaluate`, `bond.price.from_yield`, `exec.tca.pretrade`, `paper.pretrade.check`, `exec.sim.lit.run`, `exec.tca.attribution` and `paper.book.end_of_day`. For another lane to consider (four-language parity is theirs):

1. `paper.ledger.append` and `paper.ledger.verify` hard-code the label "crypto venue; simulated" (HR-43). A `label` input would let this ledger use them; today the tool computes the same HR-45 bytes itself and a test compares them with `quantforge_core.paper.canonical`.
2. `paper.book.end_of_day`, `paper.pretrade.check` return that crypto label in their outputs. Harmless here (the job does not copy it), but wrong for a Treasury book. Same `label` input would fix it.
3. `paper.book.end_of_day` takes one symbol. The job calls it once per instrument and leg and adds the decimal results. A multi-symbol form would remove that adding from the tool.

## Registrations needed (not edited by this lane)

- `specifications/cli-contract.md`: nothing (no new operation).
- `specifications/name-map.json`, reference pages, checklists: the new spec `12-platform/paper-ledger-daily.md` and the rulings file `stage-k-rulings-paper.md` may need listing; see the gate results below.
- `specifications/12-platform/README.md` and `specifications/README.md` do not list individual specs for this folder yet; add `paper-ledger-daily.md` when the folder gets its index.
- `python/pyproject.toml`: nothing (the new test is fully typed and needs no mypy override).
- `tools/README.md`, `docs/diagrams/README.md` ("the ledger lives in the forward-log branch", HR-46) and `CHANGELOG.md`: a line for the daily ledger and its own branch, for the docs lane.
- Branch protection: `paper-ledger` and `paper-ledger-anchors` should be writable only by the workflow, as `forward-log` is. Owner setting.
- Whether `paper-ledger` commits are signed with `FORWARD_LOG_SIGNING_KEY` (the workflow uses it if present): owner's call.

## What the dashboard lane will need

- `ledger/summary.json` on `paper-ledger`: `ok`, `records`, `recorded_trading_days`, `late_days`, `gaps`, `head`, `last_date`, `nav`, `pnl`, `label`. It is rewritten by every run that adds rows.
- Per day, from each DAY row body: `date`, `timing`, `pnl`, `nav_close`, `explain.*` (five terms), `positions_close`, `orders[].status`, `orders[].tca.total_bps`, `orders[].tca_pretrade.expected_cost_bps`, `cumulative.*`.
- Every chart or table built from it must show the row label, "simulated" for fills, "placeholder weights" beside the pre-trade estimate, and the sentence that no performance claim is made. A cumulative P&L line without those would read as a track record, which it is not.
- Days: count only `timing == "on_time"` rows; show late days and gaps as what they are.
- Dates: run `python research/test_preregs.py` on any page that prints ledger dates (plan 14.10 rule 6). Ledger dates start after every holdout window, and the verifier enforces it.

## Gate results on this branch (2026-11-19, local laptop, not the acceptance machine)

| Command | Result |
|---|---|
| `uv run pytest tests/test_paper_daily.py` | 40 passed |
| `uv run ruff check` and `ruff format --check` on the test; `uv run mypy .` | clean; 227 source files, no issues |
| `python research/test_preregs.py` | 10 tests OK |
| `python tools/test_tools.py` | passed (exit 0) |
| `tools/build_references.py --check`, `tools/validation/build_checklists.py --check`, `tools/gen_name_map.py --check`, `tools/case_figures.py --check`, `tools/outside_shares.py --check` | up to date; nothing regenerated, no generated file changed |
| `tools/quality_gate.py --check-register --check-specs --check-docs` | 0 new gaps (10 baseline) |
| `tools/check_job_names.py`, `tools/check_hygiene.py` | 59 jobs, 0 problems; 0 problems |
| `git grep -i` for the banned word on the diff | none |

Not run: the full Python test suite, the Java, C++ and Rust builds (no change there), and the workflow itself.
