# Release evidence for v1.0.0 (K-7, G1k, G3b, G10)

Spec version 0.2.0-proposed (written by lane k-w3-spec on 2026-11-19, commit 80b8f8ea; brought to branch `k-v1-k7` on 2026-11-20 with the K-7 parts only). Status: PROPOSED until the stage K coordinator confirms rulings KR-222 to KR-227 (`specifications/stage-k-rulings-k7.md`). Some checks are now built on `k-v1-k7` and none has run on a tag; "Build state" at the end says which. Plan items: 14.8 K-7; 12.7 G1k, G3b, G10; 14.10 rules 1 and 2. Builds on `.github/workflows/release.yml` (which already refuses a version with no CHANGELOG section, attests each asset with SLSA provenance and ships a CycloneDX SBOM, as its header states).

**Plain idea.** A release should be checkable by someone who was not there. Each item below is a script or a CI job that leaves a file or a run link behind, and each is shown failing on a planted fault before it is trusted. Items that need the owner's own hands (repository settings, registry accounts) are marked as waiting for the owner; Claude prepares them and never creates accounts.

## Acceptance tests copied from the plan (not softened)

> K-7: Clean-machine run of every example and tutorial; signed release with attestations verified by `gh attestation verify`; runbooks; known-issues register; per-model validation reports; public results page; G1k strict rule on.
>
> G1k: Ruleset 26732064 shows strict on; a PR behind main cannot merge.
>
> G3b: `pip install` and `cargo add` work for the release.
>
> G10: Checked and recorded in the release notes (desktop, phone 375 px with no sideways scroll, dark mode).

## Checks

| ID | Check | Script or job | Evidence stored | Planted fault (rule 1) |
|---|---|---|---|---|
| RE1 | Clean-machine run of every example and tutorial | `tutorial.yml` extended to every file under `examples/` and `docs/getting-started/tutorial-*.md` code blocks, on fresh `ubuntu-latest`, `windows-latest` and `macos-latest` runners, following only CONTRIBUTING's setup commands; a tutorial listed nowhere fails (`UNLISTED`) | run link and per-tutorial pass list, `benchmarks/results/k7/clean-machine.json` | a tutorial block with a wrong expected output; a new tutorial file not in the list |
| RE2 | Attestations verified | new job `release-verify` after `release.yml`: downloads every release asset and runs `gh attestation verify <asset> --repo AshJha0/quantforge` on each; also checks the SBOM is present | job log and `benchmarks/results/k7/attest.json` (asset, digest, verdict) | a copy of one asset with one byte changed must fail verification (done in the job on a temp copy) |
| RE3 | Runbooks | `docs/runbooks/` (recorder failure, paper-ledger and curve-daily red runs, anchor failure, release, rollback of a bad tag); `tools/check_runbooks.py`: every command in a runbook code block names a script or workflow that exists | check output in `docs.yml` | a runbook naming a missing script |
| RE4 | Known-issues register | `docs/known-issues.md`, one row per issue (ID, severity, area, workaround, evidence path); `tools/check_known_issues.py`: every MISS, "point release" move and open limitation recorded in specs, ROADMAP and CHANGELOG appears in the register (for example H-9 workload R MISS, K-8 ladder moved to a point release, the curve consistency miss of 2026-11-13) | check output | a spec with a recorded MISS not in the register |
| RE5 | Per-model validation reports | `tools/inventory_counts.py` extended: every model in `docs/model-inventory.md` has a "Validation report" path that exists and is not a placeholder | check output | an inventory row pointing at a missing file |
| RE6 | Public results page | `docs/results.md`: every study and gate verdict with its evidence path, misses first; generated from a list file and checked like RE4 | page and check | a verdict line without an evidence path |
| RE7 | G1k strict rule on | **owner setting** (repository rules are the owner's account settings): owner turns on "require branches to be up to date" in ruleset 26732064. Check: `gh api repos/AshJha0/quantforge/rulesets/26732064` shows the required-status-checks rule with strict policy true, saved to `benchmarks/results/k7/ruleset.json`; then a throwaway branch one commit behind `main` with a draft PR shows merge state BEHIND and cannot merge (the coordinator opens and closes that PR; lanes do not open PRs) | ruleset JSON and the PR link | the check script given a saved ruleset JSON with strict false must fail |
| RE8 | G3b registry publishing | **waiting for the owner's own free accounts on PyPI and crates.io (no card); Claude never creates accounts.** Prepared meanwhile: a distinct free name (`quantforge` is taken on both, plan 12.7) chosen by reading both registries' search pages, and a publish job using the registries' token-free trusted publishing where the owner enables it. Check after publish: on a fresh runner `pip install <name>==1.0.0` and `cargo add <name>@1.0.0` then a one-line import and call | install log | publish job pointed at a version that does not exist must fail the install check. If the accounts are not there at tag time, G3b moves to v1.0.1 (owner decision K-QF) and the release notes say so |
| RE9 | G10 site check | `tools/check_site_view.py` on the built site with a headless browser (Playwright, free; licence to be read before use): every page at 1280 px and at 375 px, `document.documentElement.scrollWidth <= 375` at phone width, and in dark mode (`prefers-color-scheme: dark`) the existing pa11y AA run passes; screenshots of home, LEARN, COOKBOOK, the gallery and the three dashboards in both modes | result table pasted into the release notes, screenshots as release assets | a test page with a 600 px fixed-width element must fail at 375 px |

The CHANGELOG entry for v1.0.0 says "delivered" for an item only with its evidence path (rule 2).

## Out of scope

- Creating any account, token or secret; changing repository settings (owner only).
- A second review of any kind (owner decision 2026-11-18); the plan 14.10 rule 5 different-model audit before the tag is a separate item (K-9).
- Signing keys beyond what `release.yml` already uses (GitHub's OIDC-based attestation).

## Limits

- `gh attestation verify` shows the asset was built by the workflow at that commit, not that the code is correct.
- The site check is automated layout and contrast checking, not a usability study.

## Build state on branch `k-v1-k7` (2026-11-20)

What exists now, what has run, and what has not. Evidence class in brackets.

| ID | Built | Run so far | Not done |
|---|---|---|---|
| RE1 | `tools/check_examples.py` (every `examples/*.json` and `batch.jsonl` case through `quantforge batch`, every example script no tutorial page runs, `UNLISTED` tutorial pages); a step in each `tutorial.yml` job; `clean-machine.yml` for the Python build on Windows and macOS | Python CLI on the owner's Windows laptop: 80 cases and 1 script as expected, 7.9 s (measured, local laptop); planted faults fail (`--self-test`) | no CI run yet; Rust, Java and C++ on Windows and macOS not run by this check (KR-222 note); `benchmarks/results/k7/clean-machine.json` not written: the run log is the evidence until a run writes it |
| RE2 | `tools/release_verify.py` and the `release-verify` job; `SHA256SUMS` now written before the attest step and attested; `tools/check_versions.py --expect` in `release-changelog` | `--self-test` with a stub verifier (measured); v0.10.0 read via the API: 6 of 7 assets attested, `SHA256SUMS` not (`benchmarks/results/k7/v0.10.0-attestations-2026-11-20.json`, read) | the job runs only on a tag push: never run |
| RE3 | `docs/runbooks/` (5 runbooks and an index); `tools/check_runbooks.py` | passes; planted faults fail (measured) | the anchor-failure runbook is part of `daily-jobs.md`, not its own page |
| RE4 | `tools/check_known_issues.py`; register rows added for every recorded miss and point-release move found | passes; planted faults fail (measured) | |
| RE5 | `tools/validation/model_reports.py`: 120 reports under `docs/validation/models/` | `--check` passes; planted faults fail (measured) | the inventory's "Validation report" lines still name specs; the reports link back to them |
| RE6 | `docs/results.md` from `tools/results_page.py` and `tools/results_verdicts.json` | `--check` passes; planted faults fail (measured) | |
| RE7 | `tools/check_ruleset.py` | ruleset read 2026-11-20: strict off, so the check fails (read; `benchmarks/results/k7/ruleset-2026-11-20.json`) | owner setting; the behind-main PR test is the coordinator's |
| RE8 | nothing | | waits for the owner's accounts (KR-226) |
| RE9 | nothing | | no headless-browser check yet (KR-227) |
