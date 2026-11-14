# R3-01 amendment 8: US Treasury curve butterfly mean reversion, terminal rule for a study short of 250 counted days

Status: **signed**. Signed by Claude (stage J fixes lane; signing delegated by the owner, 2026-11-07, decision relayed by the stage J coordinator) on 2026-11-14. Second read: `program/R3_A8_REVIEW.md` (a separate Claude subagent; human check: none).
- SHA-256 of the body below the marker line: `37009337f2570342a26f2525dfc19759e8abc8b1501dc27e5df67d25f771ce5e`
- SHA-256 of the amended prereg `R3-01-treasury-fly.md` (whole file): `57e047579bf2952fad7f1a15197ca1a702fe994d8c77c32f3652105bdd7d7a3e`
- SHA-256 of `R3-01-amendment-1.md` (whole file): `a0b92234f172fe8fc0a846d0378d059a5315230213288cf813a5e767d6a9a77b`
- SHA-256 of `R3-01-amendment-2.md` (whole file): `feb357708a5614be55217500934968fd3dc075338f6475e719ba559d69632f6e`
- SHA-256 of `R3-01-amendment-3.md` (whole file): `4fc7d3dce832bdf409c713f76d144df9f2c32f46fb661ff8f5197b142433b30d`
- SHA-256 of `R3-01-amendment-4.md` (whole file): `8327fc5b04401d8720719ac6ae08d13cae36c6d39cc3ed58631a13ddd0c47813`
- SHA-256 of `R3-01-amendment-5.md` (whole file): `7d2b155fa9d88565f524de6ac311100aea4cb52f4f67f5417f433297067d5b52`
- SHA-256 of `R3-01-amendment-6.md` (whole file): `ef1ad90371e56c27ffecd006621d454a2d4fd016e81f496c3be0ab733e813b33`
- SHA-256 of `R3-01-amendment-7.md` (whole file): `8234595f43efbd9406391d0c76eced02e0ae23edbc4c9e2b916290877f6234c1`
- SHA-256 of the common rules (`README.md` body): `53566e4c3060d1adfd386a543b8d789b1de0b9b53393a8ffa03e0c3f4b5d58aa`
- SHA-256 of `DEVIATION-2026-11-12.md` (whole file): `b7e9e4d33e14dc164ed2c34312bf52bb894accfa124c3c8c45400d913e67c1db`
- SHA-256 of `DEVIATION-2026-11-12-recorder-rule.md` (whole file): `8a4bdeee378644ae4389b22b81ee259b3c101d6f0dd54c9be72a170fac2e3044`
- SHA-256 of `research/holdout_runs.csv` (whole file): `8555ba6896697b2dde780cb98921637aeb2973a3b5607ec5fdd7ebf2087823e0`
- SHA-256 of `research/r3/forward_signals.jsonl` (whole file): `5de53f521168b4def207aa8cab15f1272b63e30fad8eac213e2ebfed52e82787`
- Fixed before any forward judgement; no forward outcome has been evaluated at signing.
- This file is not edited after signing; a further change is a new amendment.

<!-- body -->
Amends each of `R3-01-treasury-fly.md`, `R3-02-bill-repo-spread.md` and `R3-03-breakeven-seasonality.md` (one shared text; the file header names the study it amends) and that study's earlier amendments (R3-01: 1 to 7; R3-02 and R3-03: 1 to 4, 6 and 7). They stand; where this amendment differs, this amendment governs. Common rules: `README.md`. Source: the owner question left open by amendment 7 ("Not decided here (owner)": a terminal rule for a study that never reaches 250 counted days), answered by the stage J coordinator under the owner's delegation on 2026-11-14, and the second read `program/R3_A8_REVIEW.md`.

**State at signing.** Fixed before any forward judgement. No forward outcome has been evaluated: no forward return, P&L, Sharpe, confidence interval or agreement test has been computed for any study on any date, and none is computed by the writer. The rule below depends only on the count of counted days defined by amendment 7 Change 1 and on the calendar, never on a position's value or on any outcome.

## Change 1: terminal rule for a study without 250 counted days

Replaces amendment 7's "Until the owner sets one, such a study is reported as not yet judged" with the following.

- The **cut-off date** is 2027-11-05 (inclusive; a UTC date, as in amendment 7 Change 1), the same for all three studies.
- Only rows dated on or before the cut-off date whose `knowledge_time` (write time) is on or before 2027-11-05T23:59:59Z count. A row written later, including a back-fill dated earlier, adds no counted day for this rule; after that instant each study's status is frozen.
- A study whose judgement date (amendment 7 Change 1: the counted day on which its count reaches 250) falls on or before the cut-off date is judged on that date by the agreement test of amendment 1, unchanged.
- A study whose count has not reached 250 by the end of the cut-off date is reported **"not judged: insufficient data"**, with its counted-day count at the cut-off date. This is a final report for this preregistration: it is never a pass, never reported as agreement or disagreement, and it is not turned into a judgement by rows dated or written after the cut-off date. The 60-day pipeline check (common rules) is unaffected.
- Before the cut-off date a study short of 250 counted days is reported "not yet judged", as now.
- A later study of the same idea needs a new preregistration; it may not reuse this one's forward rows as unseen data.
- The rule is applied by `judgement` in `research/r3_forward.py` (extended and tested in the signing commit with an `as_of` date, the cut-off, the write-time rule above and a `status` per study: `judged on <date>`, `not yet judged`, or `not judged: insufficient data`). It reads no return. `tools/recorder/holidays.txt` already lists the 2027 holidays.

**Why.** Without a terminal rule a study whose feed stops, or whose rule is rarely defined (R3-01's window fills around December 2027 under amendment 7), stays open without end, and a late judgement could be chosen once some outcome is known. A fixed calendar cut-off, set before any forward outcome is seen, closes that freedom. Reporting the short study as "not judged" rather than as a fail keeps the label honest: too few days is absence of evidence, not evidence against the rule, and it is never evidence for it.

## What is unchanged

Everything amendment 7 lists as unchanged; amendment 7 Change 1 (which days count) and Change 2 (where rows are written); the agreement test of amendment 1; the holdout results (`research/r3/RESULTS.md`, all three fail).

## Prior knowledge

As in amendment 7. No forward return or outcome has been computed. The signer knows the back-fill state (R3-03 defined positions; R3-01 and R3-02 null) and the amendment 7 estimate that R3-01's 250-day window fills around December 2027, which may place R3-01 under this rule (R3-02's back-fill is also null, so it may be affected too); the cut-off date was chosen from the review calendar (about one year after signing), not from any outcome.

## AI assistance (`research/TEMPLATE.md` section 7)

- Tool and version: Claude Code, model claude-opus-5-5 (Opus 5.5), 2026-11-14.
- What it did: drafted this amendment from the coordinator's decision and signed it under the owner's delegation.
- Claims checked by a human: none yet. The second read was by a separate Claude subagent, not a person.
