# Release notes template

Copy this file to `docs/releases/vX.Y.Z.md` for each release and fill every section. The "Evidence" and "Limits" sections are fixed: a release with nothing to say in one of them writes "None" and why, rather than deleting the heading. Gap G-7 of the docs plan; the stage H and stage K limits text (plan sections 15.1 and 15.2) goes in "Limits" word for word.

Rules that apply to every section: numbers come from committed files and name them; status words come only from the ladder in README `Status` (Proposed, Specified, Implemented, Validated, Benchmarked, Operationally tested); simulated results say "simulated" in their first sentence; crypto results say "crypto venue; not equities or rates" and show aggregates only; placeholder SIMM weights say "placeholder weights, not ISDA-calibrated".

---

# vX.Y.Z release notes: stage L, one-line subject

Released YYYY-MM-DD, tag `vX.Y.Z` on commit `abcdef12`.

### Who should read what

One line per audience: students, desk developers, quants and validators, researchers.

## What this release is

Two or three sentences: what was built, and the one thing it does not do.

## Headline figures

| Figure | Value | Source file |
|---|---|---|
| Golden cases, total and added | | `datasets/golden/...` |
| Outside-checked share, with and without the added cases (plan 14.10 rule 3) | | `tools/outside_shares.py` output |
| Mutation score, per gated module | | `conformance/mutation/...` |

## Added

One subsection per item delivered, each with its rulings and the path to its evidence.

## Evidence

For every item above: the acceptance test as fixed before the run, where the result is, and its evidence class (golden with outside check, hand case, blind re-derivation, simulation with planted truth, regulator text read, secondary copy, reference only). Items moved to a point release under the plan 15 gate rule are listed here with the reason.

## Research results

Each study with its prereg, its verdict whatever it is, and the standard error.

## Fixed

## Changed

## Limits

The stage's mandatory limits text, verbatim, then any limits found during the stage. For stage H this includes: crypto venue only, lit only; no live orders; dark pool, multi-venue routing and paper trading simulated.

## Known issues

## Verification

The commands that reproduce the headline figures, and the CI runs on the tagged commit.
