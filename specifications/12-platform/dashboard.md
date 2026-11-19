# Docs-site dashboards: paper ledger, daily curve, model reserve (K-1, K-2, Q8k, K-11, K-8j page)

Spec version 0.1.0-proposed (stage K wave 3, lane k-w3-spec, 2026-11-19). Status: PROPOSED; nothing here is built or run. Rulings KR-211 to KR-216 (`stage-k-rulings-w3.md`). Plan items: 14.8 K-1, K-2; 12.7 Q8k; 15.2 model risk ("a model-reserve dashboard on the docs site"); 14.10 rules 1 and 6. Data come from `12-platform/paper-ledger-daily.md` (branch `paper-ledger`), `12-platform/daily-curve-run.md` (branch `curve-daily`) and `06-risk/model-reserve.md` (operation `risk.model_reserve.dispersion`). Requirements copied from the two handovers' "what the dashboard lane will need" (`program/STAGE_K_PAPER_HANDOVER.md`, `program/STAGE_K_CURVE_DAILY_HANDOVER.md`).

**Plain idea.** The daily jobs already write verified, hash-chained ledgers on their own branches. The dashboard is only a reader: at site-build time it checks each ledger, then prints what is there as plain static pages, with every label the ledgers carry. It never computes a performance figure, because the paper book follows a fixed rotation that ignores the market and its P&L is plumbing evidence, not a track record.

## 1. How the pages are built (KR-211)

- New script `tools/dashboard/render.py`, called by `tools/build_site.py` through a `--dashboards` flag (default on in `docs.yml`), after the Markdown pages. It writes three pages with the site's own template and CSS: `dashboard/paper.html`, `dashboard/curve.html`, `dashboard/model-reserve.html`, and a link from the site bar. No JavaScript is needed; tables are plain HTML; any chart is inline SVG with a text alternative (plan 13.2 E6).
- Inputs read at build time with `git show`: `origin/paper-ledger:ledger/ledger.jsonl` and `ledger/summary.json`; `origin/curve-daily:ledger/curves.jsonl` and `ledger/summary.json`; anchors from the two `-anchors` branches. In `docs.yml` this is one `git fetch` of those four branches. Nothing is committed to `main` by the dashboard: the pages exist only in the built site.
- **Verify first.** Before rendering, `render.py` runs `tools/paper_daily/verify_ledger.py verify --ledger ... --anchors ...` and `tools/curve_daily/verify_chain.py verify ...`. If one fails, that page prints only: the label, "The ledger did not verify at site build on <build date>: <reason code>. No figures are shown.", and the head hash; the build itself still succeeds so the docs are not blocked by a data fault, and the step prints a `::warning::`. A page never shows a number from an unverified ledger.
- If a branch does not exist yet (true on 2026-11-19), the page says "No recorded days yet" with the label and the 0-of-20 counter.

## 2. Paper ledger page (K-1, K-2, Q8k; KR-212, KR-213)

Required labels (from the paper handover and spec; all must appear, verbatim, above the first table):
- "paper marks on a fitted curve; not tradable" (row label);
- "Paper trading on free data; simulated fills; no evidence of tradable profitability." (11.6 sentence);
- "This is plumbing evidence, not a strategy. The trading rule is a fixed rotation that never looks at the market. No performance claim is made from this ledger.";
- "simulated" on every fill column header; "placeholder weights" beside every pre-trade estimate column header.

Content:
| Block | Fields (from the ledger rows) |
|---|---|
| Counter | "**N of 20** recorded trading days (on time)" where N counts only rows with `timing == "on_time"` (KR-213); then late days and gaps, as counts and as a list of dates with their kind. The counter is recomputed from the rows and must equal `summary.json` `recorded_trading_days`; a difference fails the build (`COUNTER`) |
| Chain | head hash, last date, last anchor time, verifier result |
| Per day table, newest first | `date`, `timing`, `pnl`, the five `explain` terms, `unexplained`, `nav_close`, `positions_close` |
| Orders table | per order: date, symbol, side, quantity asked and filled, `status`, pre-trade `expected_cost_bps` (placeholder weights), post-trade `tca.total_bps` and its parts (Q8k) |

Forbidden on this page (KR-212): any return, Sharpe, volatility of P&L, annualised figure, drawdown, hit rate, comparison with a benchmark, or a cumulative P&L chart. Plain daily tables only. A lint in `render.py` refuses to write a dashboard page containing any of the words `return`, `Sharpe`, `annualised`, `annualized`, `drawdown`, `outperform`, `alpha`, `profitab` (except inside the fixed 11.6 sentence, which is matched exactly and removed before the lint).

## 3. Daily curve page (K-11; KR-214)

Calls `tools/curve_daily/site_page.render(summary)` (KR-106 of the curve lane), which already prints the label "fitted to public US Treasury par yields with a library Nelson-Siegel fit; not an official curve", the consistency label "consistency check, not proof", and the recorded miss note of 2026-11-13 (RMSE 17.36 bp against the 15 bp tolerance). Adds a table of the last 20 rows (date, timing, tau, fit RMSE, six zero rates, consistency status: `ok`, `outside`, `pending`), late days and gaps listed as such, and the chain head. Rows outside the tolerance are shown as `outside`, never dropped. The recorded miss note stays on the page until a ruling removes it with a reason; it is never removed because later days pass.

## 4. Model-reserve page (15.2 model risk; KR-215)

Source: the reserve report registered in `06-risk/model-reserve.md` (`risk.model_reserve.dispersion`, model inventory MG-7) and, when it exists, the K-8j model risk aggregation output (no K-8j spec exists on 2026-11-19; this page reads a file `docs/validation/model-reserve-report.json` that the K-8j lane will define; until then the page says "No model-reserve report yet" and lists the inventory's MG-7 entry). Shows per exotic: booked model, model prices, range, reserve, relative reserve, worst model, and the report's own labels. Label: "model-risk reserve from a set of calibrated models on simulated or golden inputs; not a prudent-valuation figure for any firm". No claim that the reserve is adequate.

## 5. Holdout-date check (plan 14.10 rule 6; KR-216)

Every rendered page's text is passed to `research/holdout_scan.scan_text(path, text)` before it is written; any hit fails the build (`HOLDOUT`). The ledgers' own verifiers already refuse holdout dates (paper P10, curve C-spec); this is the page-level check the rule asks for, because a page could also print dates that are not row dates (for example a source date in a note). `python research/test_preregs.py` runs in the same job.

## Acceptance tests (PROPOSED; fixed before the pages are built)

| ID | Plan | Test |
|---|---|---|
| DB1 | K-1, K-2 | Built from a 30-business-day synthetic ledger (the `pl_k-0003` run): every label of §2 present verbatim; counter reads 30 of 20; per-day and orders tables complete; explain terms sum to P&L on every printed row |
| DB2 | Q8k | Every order row shows pre-trade (placeholder weights) and post-trade TCA |
| DB3 | K-11 | Curve page from a synthetic two-day curve ledger shows the labels, the recorded miss note and an `outside` row |
| DB4 | 15.2 | Model-reserve page from `reserve_g` golden outputs shows the label and the values equal to the goldens |
| DB5 | 14.10 rule 1 | Planted faults, each failing with its code: a label removed (`LABEL`); a summary counter that disagrees with the rows (`COUNTER`); a late day counted as on time (`COUNTER`); a forbidden word in a template (`CLAIM`); a page date inside a holdout window (`HOLDOUT`); a ledger with one changed byte (page shows the no-figures banner, test asserts no number from the ledger appears) |
| DB6 | 14.10 rule 6 | `research/test_preregs.py` and the page scan green on the real build |
| DB7 | G10 | Each dashboard page checked at 375 px with no sideways scroll and in dark mode, recorded with the release check (`release-evidence.md`) |

## Out of scope

- Any performance statistic, chart of cumulative P&L, or comparison; any claim from the ledger.
- Live updating, JavaScript data fetching, or a server: pages are static and rebuilt with the site.
- Committing ledger data to `main`.
- Defining the K-8j aggregation itself.

## Limits

- The pages show what the ledgers hold at build time; the site can lag the ledgers by up to one docs build.
- The 20-day counter on the page is a display of the K-2 gate, not the gate; the tag gate is `verify_ledger.py ... --require-days 20` on the real ledger.
