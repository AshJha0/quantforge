# Status ladder and the 60% outside-check rule

**Plain idea.** Two separate questions decide what may be said about a piece of QuantForge. First, how far has it got: written down, built, checked on real data, timed, run in operation? That is the status ladder. Second, has anyone outside the author's own reading checked its numbers? That is the outside-check share, and a stage or item below 60% of its value cases may not be released as done: it moves to a point release instead. A third thing, agreement between the four builds, is necessary but says nothing about whether the spec is right, because four programs written from one spec can agree on the same mistake.

## The ladder

Every capability moves through `Proposed → Specified → Implemented → Validated → Benchmarked → Operationally tested` (README, `Status`; status words come only from this list, `docs/releases/TEMPLATE.md`).

| Rung | What it takes (source) | Where QuantForge is |
|---|---|---|
| Proposed | a capability named in a plan or a spec draft | stage K wave 2 items, the sensitivity-based initial margin (`sbim`, K-8h) |
| Specified | a spec with inputs, outputs, errors, golden cases and an acceptance test fixed before any run | stage K wave 2 specs merged on the integration branch `k-r1` without an implementation |
| Implemented | all four languages pass the goldens (`docs/model-inventory.md`, "Status words") | stages A to J, R6 and H, released; stage K round 1 items on the integration branch `k-r1`, not released |
| Validated | tested on real data against an independent benchmark, with a written report (`docs/model-inventory.md`) | **nothing**; every golden input to date is synthetic, except the stage J shock-library Treasury yields and the stage H crypto book |
| Benchmarked | timed against targets fixed before the run, on the stated acceptance machine | nothing; H-9 has laptop timings only, labelled "local laptop, not the acceptance machine", and its workload R result of 2026-11-19 is a recorded MISS |
| Operationally tested | run on a schedule, unattended, with its own evidence trail | nothing; the stage K paper ledger is built, is not scheduled (schedule withheld while audit findings are open, `docs/known-issues.md`), and has 0 of the 20 recorded days its gate needs |

"Outside-checked" is not a rung. It is evidence attached to Implemented: some goldens are re-derived outside the author's own code (`docs/model-inventory.md`). There is no second review, human or otherwise (owner decision 2026-11-18), so every rung above Specified rests on self-assessment plus the outside checks below.

## The 60% rule

**Formal statement.** Plan section 15 and rule R6-13 (decision D6, owner 2026-11-12), as implemented in `tools/outside_shares.py`:

- A value-checked golden case counts as outside-checked only if **every** compared output is checked, and only by one of: `library-object` (a library's own pricing or estimation object, such as a QuantLib engine), `library-primitive` (numpy or SciPy numerics applied to a different formulation of the same problem), or, where no free library exists, `independent-rederivation` (a blind lane under DR-H2, or a figure printed in the source). A formula written again around a library call (`reimplementation`) and a published worked example alone (`none`, under D6 for stages D to J) do not count. Our own oracle, such as the mpmath generators, never counts.
- The floor is 60% of a stage's value-checked cases, without generated sweeps; error and invariance cases are a separate class and leave the denominator.
- From stage H on, the floor applies **per plan item** as well as per stage. An item under 60% moves to a point release unless it is re-derived blind first. The threshold is never loosened to let an item through (lane rules; owner decision K-QB, 2026-11-18).
- Stage K wave 2 counts published figures (P), independent libraries (L) and blind re-derivation (B) separately, and does not count table lookups (T) (ruling KR-68, proposed; `program/STAGE_K_W2_GATE.md`).

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

**Stage K shares above are under review, not settled (audit finding KA-C18, open; `docs/known-issues.md`).** They count cases checked against a figure printed in the regulator text, on part of their outputs and at print precision. By the strict reading of the rule (every compared output checked) the stage is 50 of 87 (57.5%), under the floor; items under the floor by that reading: F (existing traffic_light) 0 of 11 (0.0%); K-8d 7 of 16 (43.8%); K-8e 11 of 24 (45.8%).
<!-- generated:status-ladder:end -->

## Stage K, round 1: what the generated table does not cover

Every stage K round 1 item in the generated table above comes from `tools/outside_shares.py` on the integration branch `k-r1`; no stage K share on this page is typed by hand. Not in that table:

- The daily paper ledger (K-2) has no golden suite in `datasets/golden/`; its worked example is checked by hand only (`program/STAGE_K_PAPER_HANDOVER.md`), so no outside share is stated for it.
- Wave 2 items (K-8a DRC and RRAO, K-8f IMA, K-8g CVA capital, K-8i leverage and large exposures) are specifications only on `k-r1`; their goldens and implementations are on lane branches not merged, and `program/STAGE_K_W2_GATE.md` records that none reaches 60% from published figures and libraries alone. No share for them is stated here until their goldens are merged and the tool computes it.
- The sensitivity-based initial margin (`sbim`), if built, runs on placeholder weights from a stated rule, and could only be checked by a blind re-derivation of its algebra, never against any outside model's numbers (`program/STAGE_K_W2_GATE.md`).

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
