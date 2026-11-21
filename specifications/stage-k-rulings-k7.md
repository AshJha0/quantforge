# Stage K rulings, K-7 release evidence: confirmed 2026-11-20

Status: **CONFIRMED** as written, by the stage K coordinator under the owner's delegation, 2026-11-20. Confirming a row fixes the rule; it does not say the rule is met. Not met at confirmation: KR-222 (Rust, Java and C++ examples do not yet run on Windows and macOS runners; Python only), KR-223 (cannot run before a tag), KR-225 (owner setting, strict is off), KR-226 (owner decision 2026-11-20 below: registry publishing is not done), KR-227 (no script yet). Written by lane k-w3-spec on 2026-11-19 (commit 80b8f8ea, file `stage-k-rulings-w3.md` on branch `k-w3-spec`) and brought to branch `k-v1-k7` on 2026-11-20 with the K-7 rows only; the K-6 rows (KR-217 to KR-221) and the dashboard rows (KR-211 to KR-216 on that branch) belong to other lanes and are not copied. Reviewer: none: self-assessment; no second review (owner decision 2026-11-18). Spec: `12-platform/release-evidence.md`.

**Numbering check (read 2026-11-20 with `git grep` over every remote branch).** KR-222 to KR-227 appear on no branch except `k-w3-spec`, where they mean the same as here. Numbers in use elsewhere: KR-200 to KR-214, KR-230 to KR-242 and KR-250 to KR-256 on `k-v1`; KR-257, KR-260 and KR-300 to KR-326 on other branches (lane brief). The `k-w3-spec` rows KR-200 to KR-216 collide with the `k-v1` rows of the same numbers and are not brought here.

| ID | Topic | Ruling |
|---|---|---|
| KR-222 | Clean machine | Every example and tutorial on fresh Linux, Windows and macOS runners from CONTRIBUTING's commands only; unlisted tutorial fails |
| KR-223 | Attestation verify | `release-verify` job runs `gh attestation verify` on every asset and on a tampered copy (must fail) |
| KR-224 | Registers | Runbooks, known-issues register, per-model validation reports and the public results page each have a check script with a planted fault; every recorded MISS appears in the known-issues register |
| KR-225 | G1k | Owner turns the strict rule on; check reads ruleset 26732064 via the API and a coordinator draft PR behind main shows BEHIND |
| KR-226 | G3b | Waits for the owner's own free PyPI and crates.io accounts; Claude never creates accounts; moves to v1.0.1 if absent at tag time (K-QF) |
| KR-227 | G10 | Headless-browser check of every page at 1280 and 375 px (scrollWidth <= 375) and dark mode with pa11y AA; results in the release notes; planted 600 px element must fail |

**Under KR-226, owner decision 2026-11-20** (relayed by the stage K coordinator; the row above is unchanged): "no registry accounts; publishing to PyPI and crates.io is not done and not planned; v1.0.0 is installed from the GitHub release assets, which are checksummed and attested". G3b is therefore stated as "not done: owner decision", not as moved to v1.0.1.

## Notes from the build lane (k-v1-k7, 2026-11-20)

These notes record how the rows above were read when building; they change no row.

- KR-222: the build on `k-v1-k7` runs the examples on Linux in all four languages (the tutorial jobs) and the Python build on Windows and macOS (`clean-machine.yml`). Rust, Java and C++ on Windows and macOS are not added: each would rebuild a CLI per runner, and the cross-platform matrix (`cross-platform.yml`) already builds them there. Whether that meets "every example on fresh Linux, Windows and macOS runners" is the coordinator's call.
- KR-224: the planted faults live in each check's `--self-test` and run in `repo-gates`.
- KR-225: ruleset 26732064 read on 2026-11-20 shows `strict_required_status_checks_policy: false` (saved as `benchmarks/results/k7/ruleset-2026-11-20.json`). Turning it on is a repository setting, so the owner does it; no lane changes it.

## Notes from the second build lane (k-v1-k7b, 2026-11-20)

These notes record what was built after confirmation; they change no row.

- KR-222: `cross-platform.yml` now runs `tools/check_examples.py` in every Rust, Java and C++ cell on Windows and macOS (every run), and `tools/check_tutorial.py` in those cells outside pull requests (weekly and by hand), each against the CLI the cell just built. Python on Windows and macOS stays in `clean-machine.yml`. None of these steps has run in CI yet, so KR-222 is not yet shown met.
- KR-226: owner decision 2026-11-20, recorded under the table above.
- KR-227: `tools/check_site_view.py` and the `docs-site-view` jobs of `docs.yml`, plus a dark-mode pa11y run in `docs-site`; "Build state" in `12-platform/release-evidence.md` gives the local run and what CI has not yet run. The pa11y AA part runs on the four pages of the existing pa11y set (`.pa11yci.json`) in light and dark mode, as check RE9 of the spec words it ("the existing pa11y AA run passes"); the width and Mermaid checks run on every page. Whether pa11y must also cover every page is the coordinator's reading of the row.
- KR-227, 2026-11-20, branch `k-v1-a11y`: pa11y AA on every page, light and dark, is built (`tools/check_site_a11y.py`; `docs.yml` jobs `docs-site-a11y`, 12 shards, and `docs-site-a11y-summary`); not met until its first CI run is green. Split 2026-11-20: the jobs `docs-site-a11y` and `docs-site-a11y-summary` are not in `docs.yml` on main yet; they are held on branch `k-v1-a11y-ci` until every page passes (first CI runs, pull request #63: 33 pages per mode were reported for chart-text contrast that the tool could not measure, since changed to light and dark chart images; tutorials 36 and 39 still fail in both modes, cause not established). The tool, its self-test and the site fixes are on main. KR-227 stays not met.

**Coordinator reading of KR-227, 2026-11-20.** The row is read strictly: the pa11y AA check is meant for every page, like the width check. Built today: width at 1280 and 375 px, dark mode and Mermaid rendering on every page; pa11y AA on the four-page `.pa11yci.json` set in light and dark. KR-227 is therefore not met until pa11y runs on every page; this is listed in `docs/known-issues.md`.
