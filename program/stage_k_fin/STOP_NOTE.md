# Stage K stop note, lane k-v1-fin (2026-11-21)

Branch `k-v1-fin` from `k-v1` 5e4facc9, pushed. No PR, no merge. Reviewer: none: self-assessment; no second review (owner decision 2026-11-18). Evidence class in brackets. No gate, tolerance, threshold or bound was changed.

## Done

**A. Rulings** (coordinator decision: accept `institutional-quant-engine-plan/STAGE_K_RULINGS_DECISIONS_2026-11-21.md`).
- Marked CONFIRMED 2026-11-21 "by the stage K coordinator, delegated by owner": wave 2 KR-50 to KR-69 and KR-300 to KR-326 (rest of the rows of KR-312, KR-319, KR-324), with block headers, the four `06-risk` spec status lines and `cli-contract.md`; rev1 KR-340, KR-341, KR-343 and KR-342 with the amendment text (describes the guard on `k-v1`; the earlier SUPERSEDED note is kept as history); golden suite name `fuzzrev_k` accepted (rev1 header); paper KR-200 to KR-202, KR-205, KR-206, KR-208, KR-210 to KR-214; curve KR-203, KR-204, KR-207, KR-209, KR-254, KR-255; audit-c KR-250 to KR-252. Older blocks were confirmed only where code cites them [read: `git grep` counts per build].
- KR-310 follow-up: `frtb-ima.md` A3 sentence replaced, "an LH class key repeated" deleted from Errors. KR-318: KR-62 row notes its list output is superseded. KR-133 = KR-324 note in the w2 confirmation section.
- **KR-326 code fix**: `Leverage.java` now uses `FrtbDrc.CODE_POINT` for the group map and the report tie-break. New golden `lex_k-0011` (labels U+FFFF and U+1F600, equal exposures; generator `oracle/python/gen_stage_k_w2b.py`). `String.compareTo("￿", U+1F600)` is +10178 in Java, so the old code put U+1F600 first [measured with a one-file Java run]. C++ (`std::map<std::string>`, `operator<` on bytes) and Rust (`BTreeMap<&str>`, `cmp` on bytes) already give code-point order [read], so nothing changed there and no WSL run was made.
- Counts: 16,610 cases (8,143 value, 5,913 error, 2,554 invariance); `TOTALS:` line added to `program/R6_HANDOVER.md`; generated pages regenerated. Stage K outside share is now 171 of 219 (78.1%); K-8i 22 of 24 (91.7%), since the new case is a hand case.

**B. K-9 review part 2**: Major 1 (K-7 row: failed run 44896558134, then green on `k-v1` 44933978902, 44934025010, 44937618361; met on the branch, not main); Major 2 (counts consistent); Major 4 (planted-fault scope and the Java heap quantity in README, known-issues, `docs/capacity.md`, soak spec; bounds unchanged); minors: README fuzz text, Rust TSan row closed (log lines read from run 44815556573; C++ and jcstress planted-fault lines added to the race row), library-only stage K share 0 of 219 beside the blind figure (README), KR-240 ratio (about 88 and 205 times the measured Python error; tolerance not changed), K-3 single-run wording (LEARN, CHANGELOG). Old CHANGELOG "human review after the project": no current doc claims it (`docs/releases/v0.8.1.md:129` is a historic release note), so nothing added. Major 3 skipped (other lane).

**C.** K9-1b moved to Closed (transient, retrying fetch; last main run of `daily-workflows.yml` green). K9-1c rewritten (causes found and fixed; open until the 2026-11-22 scheduled run is green). Wave 2 mutation row: first scores from branch dispatch 44928637420 (five cells below 80%: Python `frtb_drc` 62.5, `frtb_ima` 70.0, `cva_capital` 72.5, `leverage` 65.0; C++ `leverage` 70.6) [read from the report log]. CHANGELOG lines added.

**D.** K-2 now "not met: 1 of 20 recorded trading days (measured 2026-11-21, verifier with Bitcoin headers)" in README, ROADMAP, `site_facts.json`, known-issues; LEARN, diagrams and ARCHITECTURE got the 2026-11-21 count beside the old 13:00 UTC lines.

**E.** `adding-an-operation.md`: Repo gates runs `check_case_total.py`. **F.** COOKBOOK WWR: one sentence citing `docs/determinism.md`.

## Verification [measured, local laptop, not the acceptance machine]
- Java `mvn -B -Pcoverage verify`: 1097 tests, 0 failures, 0 errors, 1 skipped; coverage gate 0 modules below. Conformance runner: Python 16,610 of 16,610, Java 16,610 of 16,610.
- Every step of `repo-gates.yml` and `docs.yml` that runs on Windows passed (script `C:/Work/Claude/qf-wt/_h4ci/kv1/fin_win/gates.sh`, outside the repo): hygiene, job names, mc_hash self-test, coverage gate tests, mutation stage checks, case figures, case totals, references, E1 coverage, stage F E1 and C++ CLI case generators `--check`, SBIM tables, K tables, share figures, status ladder, model reports, results page, known issues, runbooks, examples `--static`, release_verify, ruleset and versions self-tests, scheduled runs self-test and live check, adapter deps, feed fixtures, quality gate register, preregs, checklists, outside shares, `tools/test_tools.py`, cookbook recipes, quickstart, gallery, site build with anchors and the static a11y check, `python -m pytest -q tools`. Not run locally: pa11y and Playwright page views (CI only).
- Dispatched after the push: see the coordinator report (run ids).
- Not run: C++ and Rust conformance with `lex_k-0011` (no code change there; CI runs it).

## Open, for the coordinator
- **New fuzz finding on `k-v1` 5e4facc9**: Fuzz run 44937631714 failed `fuzz-python`: `paper.book.apply_fill` with a fill `side` given as a list raised `TypeError` (exit 70). Not fixed here; recorded in K9-1a and README.
- Skipped because their rulings live on unmerged branches: KR-258 (`k-v1-fix`), KR-262 to KR-268 incl. the KR-264 amendment (`k-v1-aad`), KR-296 to KR-299 and KR-160 to KR-176 (`k-xva-spec`).
- Left PROPOSED: SBIM KR-130 to KR-141 (`risk.sbim.placeholder` is not implemented; `sbim-placeholder.md` says nothing implemented) and `bermudan-ladder-k8.md` / KR-8 (not in scope).
- **KR-175 against KR-230, not resolved**: `origin/k-xva-spec` c7a036cc `specifications/stage-k-rulings-xva.md:24` KR-175 says "Error order HR-66 / KR-67: `E_SCHEMA`, structural `E_INPUT`, `E_DOMAIN`, `E_LIMIT`" (E_LIMIT last). Confirmed KR-230 (`stage-k-rulings-w1.md:127`) and KR-67 put `E_LIMIT` second (HR-122: E_SCHEMA, E_LIMIT, finite-rule E_DOMAIN, structural E_INPUT, E_DOMAIN). KR-266 on `k-v1-aad` follows KR-230. KR-175 is the outlier; it needs amending to KR-230 when `k-xva-spec` merges.
