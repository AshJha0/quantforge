# Stage K rulings, K-7 release evidence: PROPOSED

Status: **PROPOSED**, not normative until the stage K coordinator confirms each row. Written by lane k-w3-spec on 2026-11-19 (commit 80b8f8ea, file `stage-k-rulings-w3.md` on branch `k-w3-spec`) and brought to branch `k-v1-k7` on 2026-11-20 with the K-7 rows only; the K-6 rows (KR-217 to KR-221) and the dashboard rows (KR-211 to KR-216 on that branch) belong to other lanes and are not copied. Reviewer: none: self-assessment; no second review (owner decision 2026-11-18). Spec: `12-platform/release-evidence.md`.

**Numbering check (read 2026-11-20 with `git grep` over every remote branch).** KR-222 to KR-227 appear on no branch except `k-w3-spec`, where they mean the same as here. Numbers in use elsewhere: KR-200 to KR-214, KR-230 to KR-242 and KR-250 to KR-256 on `k-v1`; KR-257, KR-260 and KR-300 to KR-326 on other branches (lane brief). The `k-w3-spec` rows KR-200 to KR-216 collide with the `k-v1` rows of the same numbers and are not brought here.

| ID | Topic | Ruling |
|---|---|---|
| KR-222 | Clean machine | Every example and tutorial on fresh Linux, Windows and macOS runners from CONTRIBUTING's commands only; unlisted tutorial fails |
| KR-223 | Attestation verify | `release-verify` job runs `gh attestation verify` on every asset and on a tampered copy (must fail) |
| KR-224 | Registers | Runbooks, known-issues register, per-model validation reports and the public results page each have a check script with a planted fault; every recorded MISS appears in the known-issues register |
| KR-225 | G1k | Owner turns the strict rule on; check reads ruleset 26732064 via the API and a coordinator draft PR behind main shows BEHIND |
| KR-226 | G3b | Waits for the owner's own free PyPI and crates.io accounts; Claude never creates accounts; moves to v1.0.1 if absent at tag time (K-QF) |
| KR-227 | G10 | Headless-browser check of every page at 1280 and 375 px (scrollWidth <= 375) and dark mode with pa11y AA; results in the release notes; planted 600 px element must fail |

## Notes from the build lane (k-v1-k7, 2026-11-20)

These notes record how the rows above were read when building; they change no row.

- KR-222: the build on `k-v1-k7` runs the examples on Linux in all four languages (the tutorial jobs) and the Python build on Windows and macOS (`clean-machine.yml`). Rust, Java and C++ on Windows and macOS are not added: each would rebuild a CLI per runner, and the cross-platform matrix (`cross-platform.yml`) already builds them there. Whether that meets "every example on fresh Linux, Windows and macOS runners" is the coordinator's call.
- KR-224: the planted faults live in each check's `--self-test` and run in `repo-gates`.
- KR-225: ruleset 26732064 read on 2026-11-20 shows `strict_required_status_checks_policy: false` (saved as `benchmarks/results/k7/ruleset-2026-11-20.json`). Turning it on is a repository setting, so the owner does it; no lane changes it.
