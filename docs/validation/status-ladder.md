# Status ladder and the 60% outside-check rule

**Plain idea.** Two separate questions decide what may be said about a piece of QuantForge. First, how far has it got: written down, built, checked on real data, timed, run in operation? That is the status ladder. Second, has anyone outside the author's own reading checked its numbers? That is the outside-check share, and a stage or item below 60% of its value cases may not be released as done: it moves to a point release instead. A third thing, agreement between the four builds, is necessary but says nothing about whether the spec is right, because four programs written from one spec can agree on the same mistake.

## The ladder

Every capability moves through `Proposed → Specified → Implemented → Validated → Benchmarked → Operationally tested` (README, `Status`; status words come only from this list, `docs/releases/TEMPLATE.md`).

| Rung | What it takes (source) | Where QuantForge is |
|---|---|---|
| Proposed | a capability named in a plan or a spec draft | stage K wave 2 items, SIMM |
| Specified | a spec with inputs, outputs, errors, golden cases and an acceptance test fixed before any run | stage K items on lane branches before they are merged |
| Implemented | all four languages pass the goldens (`docs/model-inventory.md`, "Status words") | stages A to J, R6 and H, released |
| Validated | tested on real data against an independent benchmark, with a written report (`docs/model-inventory.md`) | **nothing**; every golden input to date is synthetic, except the stage J shock-library Treasury yields and the stage H crypto book |
| Benchmarked | timed against targets fixed before the run, on the stated acceptance machine | nothing; H-9 has laptop timings only, labelled "local laptop, not the acceptance machine", and its workload R result of 2026-11-19 is a recorded MISS |
| Operationally tested | run on a schedule, unattended, with its own evidence trail | nothing; the stage K paper ledger is built (branch `k-paper`) and has 0 of the 20 recorded days its gate needs |

"Outside-checked" is not a rung. It is evidence attached to Implemented: some goldens are re-derived outside the author's own code (`docs/model-inventory.md`). There is no second review, human or otherwise (owner decision 2026-11-18), so every rung above Specified rests on self-assessment plus the outside checks below.

## The 60% rule

**Formal statement.** Plan section 15 and rule R6-13 (decision D6, owner 2026-11-12), as implemented in `tools/outside_shares.py`:

- A value-checked golden case counts as outside-checked only if **every** compared output is checked, and only by one of: `library-object` (a library's own pricing or estimation object, such as a QuantLib engine), `library-primitive` (numpy or SciPy numerics applied to a different formulation of the same problem), or, where no free library exists, `independent-rederivation` (a blind lane under DR-H2, or a figure printed in the source). A formula written again around a library call (`reimplementation`) and a published worked example alone (`none`, under D6 for stages D to J) do not count. Our own oracle, such as the mpmath generators, never counts.
- The floor is 60% of a stage's value-checked cases, without generated sweeps; error and invariance cases are a separate class and leave the denominator.
- From stage H on, the floor applies **per plan item** as well as per stage. An item under 60% moves to a point release unless it is re-derived blind first. The threshold is never loosened to let an item through (lane rules; owner decision K-QB, 2026-11-18).
- Stage K wave 2 counts published figures (P), independent libraries (L) and blind re-derivation (B) separately, and does not count table lookups (T) (ruling KR-68, proposed; `program/STAGE_K_W2_GATE.md` on branch `k-w2-spec`).

**How blind re-derivation works**, since it is the main outside check where no library exists: a script strips every expected value, derivation and worked example from the spec; a separate lane on a different model derives the answers from that packet alone and freezes them with a committed hash; a compare script fixed in advance compares them with the goldens. A case whose answer leaked to the blind lane is not counted, even when it matches. See the [diagram](../diagrams/README.md#blind-re-derivation-packet-deriver-compare).

## Current shares (generated)

The tables below are generated from the committed shares file; do not edit them by hand.

<!-- generated:status-ladder:begin (tools/validation/status_ladder.py; do not edit by hand) -->
Source: `oracle/OUTSIDE_SHARES.json` (written by `tools/outside_shares.py`). Floor: 60.0% of value-checked cases, without generated sweeps. "Library" counts `library-object` and `library-primitive`; "with re-derivation" adds blind `independent-rederivation` cases where the rule allows them.

| Stage | Value cases | Library | Library share | With re-derivation | Share with re-derivation | Floor |
|---|---:|---:|---:|---:|---:|---|
| D | 526 | 451 | 85.7% | 451 | 85.7% | met |
| E | 710 | 557 | 78.5% | 557 | 78.5% | met |
| F | 417 | 224 | 53.7% | 355 | 85.1% | met |
| G | 441 | 359 | 81.4% | 359 | 81.4% | met |
| I | 153 | 102 | 66.7% | 102 | 66.7% | met |
| J | 215 | 143 | 66.5% | 143 | 66.5% | met |
| H | 205 | 0 | 0.0% | 160 | 78.0% | met |
| K | 87 | 0 | 0.0% | 78 | 89.7% | met |

Stage H per plan item (plan section 15: at least 60.0% of each item's value cases):

| Item | Suites | Value cases | Counted | Share | Per item |
|---|---|---:|---:|---:|---|
| H-11 | `lit_h` | 14 | 10 | 71.4% | met |
| H-12 | `dark_h` | 5 | 3 | 60.0% | met |
| H-13 | `sor_h` | 5 | 3 | 60.0% | met |
| H-14 | `alg_h` | 16 | 16 | 100.0% | met |
| H-15a | `imp_h` | 4 | 4 | 100.0% | met |
| H-16 | `venue_h` | 5 | 5 | 100.0% | met |
| H-17 | `tcx_h` | 6 | 6 | 100.0% | met |
| H-2 | `ob_h` | 10 | 8 | 80.0% | met |
| H-21 | `pt_h` | 24 | 17 | 70.8% | met |
| H-22 | `auc_h`, `eqc_h`, `ses_h` | 30 | 20 | 66.7% | met |
| H-23 | `fxc_h`, `fxv_h` | 21 | 15 | 71.4% | met |
| H-24 | `fut_h`, `rtc_h` | 19 | 18 | 94.7% | met |
| H-3a | `sched_h` | 8 | 6 | 75.0% | met |
| H-3b | `ac_h` | 5 | 3 | 60.0% | met |
| H-3c | `tca_h` | 3 | 2 | 66.7% | met |
| H-4a | `as_h` | 6 | 6 | 100.0% | met |
| H-4b | `mest_h` | 7 | 7 | 100.0% | met |
| H-6 | `uc5_h` | 3 | 2 | 66.7% | met |

Stage K per plan item (plan section 15: at least 60.0% of each item's value cases):

| Item | Suites | Value cases | Counted | Share | Per item |
|---|---|---:|---:|---:|---|
| F (existing traffic_light) | `tlk_k` | 11 | 11 | 100.0% | met |
| K-4a | `bt_k` | 8 | 6 | 75.0% | met |
| K-4b | `inc_k` | 4 | 4 | 100.0% | met |
| K-4c | `trig_k` | 6 | 4 | 66.7% | met |
| K-5a | `idr_k` | 5 | 5 | 100.0% | met |
| K-8 | `k8_k` | 7 | 7 | 100.0% | met |
| K-8 guard | `rich_k` | 6 | 6 | 100.0% | met |
| K-8d | `saccr_k` | 16 | 12 | 75.0% | met |
| K-8e | `btk_k` | 24 | 23 | 95.8% | met |
<!-- generated:status-ladder:end -->

## Stage K, round 1: per-item shares quoted from lane files (not generated)

Stage K is not merged, so the shares file on this branch has no stage K yet. The table below is quoted by hand from the lane branches' own records (read 2026-11-19); no figure in it is computed here. After the merge, `tools/outside_shares.py` writes stage K into the shares file, the generated section above picks it up, and this table is deleted (`program/STAGE_K_DOCS_PENDING.md`).

| Item | Value cases | Counted | Share | 60% | Source (branch) |
|---|---:|---:|---:|---|---|
| K-4a bitemporal store | 8 | 6 blind | 75.0% | met | `oracle/OUTSIDE_SHARES.md`, stage K section, generated by the k-w1 version of `tools/outside_shares.py` (`k-w1`) |
| K-4b incremental curve update | 4 | 4 blind | 100.0% | met | same |
| K-4c recalibration triggers | 5 | 4 blind | 80.0% | met | same |
| K-5a intraday risk with error bounds | 5 | 0 | 0.0% | **NOT MET** | same; the blind lane checked the bounds to 6 decimals only and `idr_k-0005` was not in its packet |
| K-8 guard (`num.richardson.check`) | 6 | 6 blind | 100.0% | met | same |
| K-8d SA-CCR | 16 | 5 published + 7 blind = 12 | 75% | met | `program/STAGE_K_BLIND_W1B.md` (`k-w1b`); 4 further blind matches excluded for a leak; the spec's own acceptance line still says 31% (pre-blind) and the coordinator updates it |
| K-8e FRTB backtesting (`btk_k`) | 24 | 23 SciPy `binom.cdf` | 96% if counted | open | `program/STAGE_K_W1B_HANDOVER.md` (`k-w1b`): whether a SciPy cdf that is itself the compared quantity is `library-primitive` is a coordinator decision; 12 cases also match MAR99 Table 2 |
| Existing `risk.backtest.traffic_light` (`tlk_k`) | 11 | 11 published and SciPy | 100% | met | same |
| K-8 method `CN_RANNACHER_SMOOTHED` | 7 (`k8_k`) | not yet classified | n/a | open | the spec names QuantLib `FdHullWhiteSwaptionEngine` as the counted outside check of the ladder (acceptance 1); `k8_k` is not in any shares register yet (`k-k8`) |
| K-2 daily paper ledger | 3 (`pl_k`, in a test file) | 0 | 0% | n/a | `program/STAGE_K_PAPER_HANDOVER.md` (`k-paper`): hand check of the worked example only; no outside tool has checked the marks |
| K-8a FRTB DRC and RRAO (wave 2) | 18 | 2 strict (P or L) | 11% | not met yet | `program/STAGE_K_W2_GATE.md` (`k-w2-spec`); blind lane in progress, no B claimed |
| K-8f IMA ES, stressed ES, IMCC, SES, RFET, PLA, capital (wave 2) | 33 | 12 strict | 36% | not met yet | same |
| K-8g BA-CVA and SA-CVA (wave 2) | 16 | 2 strict | 12.5% | not met yet | same |
| K-8i leverage ratio and large exposures (wave 2) | 18 | 5 strict | 28% | not met yet | same |

Plain reading: the four wave-1 data and calibration items and SA-CCR meet the rule; intraday risk bounds do not; FRTB backtesting waits on one classification decision; no wave 2 item can reach 60% without its blind lane, which is running; SIMM, if built, runs on placeholder weights, not ISDA-calibrated, and could only be checked by a blind re-derivation of its algebra, never against ISDA's numbers (`program/STAGE_K_W2_GATE.md`).

## What the rule does not say

- **A share above 60% does not make an item correct.** A blind lane reads the same rules as the first lane; it catches arithmetic and convention slips, not a wrong rule. The stage H SEC compliance date was wrong in all four builds and in the spec, and was found by reading the SEC order, not by re-derivation (HR-120).
- **A share below 60% does not make an item wrong.** It means the item has not been checked enough to be released as done.
- **Error cases are not in the share.** They check refusals, which have their own evidence class.

## Regenerate

```bash
python tools/outside_shares.py                 # recompute oracle/OUTSIDE_SHARES.json and .md
python tools/validation/status_ladder.py       # rewrite the generated tables on this page
python tools/validation/status_ladder.py --check
```
