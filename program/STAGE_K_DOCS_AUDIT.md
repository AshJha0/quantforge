# Stage K round 1: documentation audit

Docs lane, branch `k-docs` (off `k-r1` at `f2d90738`: release v0.10.0 plus the H-9 R2 spec commit), 2026-11-19. Scope: README, ROADMAP, CHANGELOG (top), ARCHITECTURE, LEARN, COOKBOOK, GLOSSARY, the question bank, the tutorial index, the curves gallery index, the diagrams page, `docs/releases/v0.10.0.md`, the site builder and home template, and gaps G-1 to G-12 of the docs plan (`DOCS_PLAN_NEXT_STAGES.md`, outside the repository). Facts the pages are held to: v0.10.0 released 2026-11-19; 15,940 cases (7,866 value, 5,560 error, 2,514 invariance; `docs/case-figures.md`); 358 operations (`specifications/name-map.json`); contract 1.16.0 (`CONTRACT` in `conformance/runner/runner.py`); stage H outside share 78.0%, 160 of 205 (`oracle/OUTSIDE_SHARES.md`); stage K planned, started 2026-11-19.

Order of work, stated plainly: the three content sub-lanes (question bank, LEARN and COOKBOOK, diagrams) committed before this file (`f562921d`, `80ca98d0`, `8ffba006`), so this audit is not the branch's first commit as the brief asked. Their changes are listed below as fixes.

## How the checks were run

| Check | Tool | Result before fixes | Result after fixes |
|---|---|---|---|
| Relative links, every tracked `.md` (files) | `tools/build_site.py` (existing) | 0 broken | 0 broken |
| Anchors, every tracked `.md` (234 `#` links) | `tools/check_md_anchors.py` (new, this branch) | 0 missing | 0 missing |
| Every `href` in the built site, with anchors | `tools/check_md_anchors.py --site` | 1 broken: `README.html` links `LICENSE`, which is not a site page | 0 |
| Holdout-date guard | `research/test_preregs.py` | OK | OK (one sub-lane draft failed it, fixed before commit) |
| Banned word | `git grep -i` | 0 hits | 0 hits |
| LSE / LSEG | `git grep -i -E "lseg|london ?stock|\blse\b|swapclear|xlon|turquoise|refinitiv|ftse"` | 2 hits, both exclusion statements | unchanged (not removed, see L-1) |
| Em dashes in docs | `git grep` for U+2014 in `*.md` | 4 files | 2 files left, both not mine to edit (see F-19, F-20) |
| Question bank set 13 numbers | `docs/question-bank/verify/v13_execution_microstructure.py` | 26 questions | 47 questions, 53 checks pass |
| Main CI | `gh run list --branch main` | all ten push workflows green on `f3bf89f1` (2026-11-19) | n/a |
| Visual check of the built site | built-in browser, local server | n/a | home, tutorial 43, curves gallery, diagrams and ARCHITECTURE at 375 px in dark mode: no horizontal page scroll (code blocks scroll inside their box); home at 1280 px in light mode; 50 of 50 diagrams render after F-34 |

`tools/check_md_anchors.py` slugs headings the way Python-Markdown's `toc` extension does (the site build); GitHub's slugs agree except for some punctuation. It now runs in `docs.yml` after the site build.

## Findings

Severity: **High** = a reader would take a false statement about the current state; **Medium** = stale, inconsistent or missing in a way a careful reader notices; **Low** = wording, history kept as current, or cosmetics.

| # | File, line or section | What is wrong, stale or missing | Severity | Fix (this branch unless stated) |
|---|---|---|---|---|
| F-1 | README.md l.74, Status | Says stage H "is at Specified: specs confirmed 2026-11-18, no code merged, target v0.10.0". Contradicted by README l.112, ROADMAP and the release notes (released 2026-11-19, all four builds) | High | Stage H slices of domains 09 and 10 listed as Implemented; limits kept |
| F-2 | README.md l.23 | "Nine stages are built and released"; stage H missing from the list; stage K not mentioned | High | "Ten stages", stage H added, stage K "planned and started 2026-11-19; nothing released" |
| F-3 | README.md l.30 | "Today every golden case uses synthetic inputs": `scen_j` goldens carry published US Treasury par yields | Medium | Statement corrected |
| F-4 | README.md l.144 | "No market data is used": stage H uses one recorded crypto venue book; `scen_j` uses Treasury yields | High | "Little market data is used", with what and where, crypto label kept |
| F-5 | README.md l.30 | Cross-class FRTB total "is being added in R6": done in R6 (v0.8.1) | Medium | Past tense, plan row named |
| F-6 | README.md l.120, CI | CI statement stops at v0.8.1 (`0f52bc2`) | Medium | Added: all ten push workflows green on `main` at `f3bf89f1`, observed with `gh run list` 2026-11-19 |
| F-7 | README.md l.3 badge | A link to the file LICENSE inside a badge escapes the site builder's link rewrite; the site page links a file it does not publish | Medium | Badge links the GitHub LICENSE URL |
| F-8 | README.md, site home | No single block saying what is real, simulated, missed and unchecked | High (brief) | "Status at a glance" generated from `tools/site_facts.json` and tree counts by `tools/status_glance.py`, rendered on the site home through `{{status_glance}}`; `build_site.py` fails if README's block is stale |
| F-9 | ROADMAP.md, H row | Column shift: the "Done" cell held the old "Specified: ..." list and "Carried" was empty | Medium | Cells rebuilt; Carried now lists H-1/H-18 full studies, H-9 R2 in progress (targets fixed 2026-11-19 before timing), H-1b, HR-40 result, the simulator ADR |
| F-10 | ROADMAP.md, K row | "Planned" without the start date; "Nothing yet" | Medium | "Planned, started 2026-11-19"; "nothing released or merged yet; round 1 work is on lane branches" |
| F-11 | ROADMAP.md, "Not in the repository yet" | Lists per-domain flow diagrams and microstructure folders as absent | Medium | Removed (diagrams added on this branch; stage H modules exist) |
| F-12 | ARCHITECTURE.md | No top-level diagram on the page; "the other domains do not exist yet" | Medium | New section "The whole system in one picture": four builds, contract, oracle, goldens, runner, CI gates, with plain idea, formal statement and a worked example (`imp_h-0001`) |
| F-13 | ARCHITECTURE.md l.154 | Stage J share "130 of 212 (61.3%)" as current | Low | v0.9.0 figure kept as history, current 143 of 215 (66.5%) added |
| F-14 | ARCHITECTURE.md l.161, l.165 | Simulator ADR "open for the stage H integration"; H-9 says nothing of R2 | Low | ADR carried to stage K; R2 in progress, HR-130/131 |
| F-15 | LEARN.md l.704 | Stage J share 130 of 212 as current | Medium | Fixed by the LEARN sub-lane (`8ffba006`) |
| F-16 | LEARN.md appendix l.840 | Tutorial stage summary stops at stage I | Low | J, R6 and H added (`8ffba006`) |
| F-17 | LEARN.md l.11 | Said tutorials 36 to 40 preview stage H ahead of the code | Medium | Fixed (`8ffba006`) |
| F-18 | COOKBOOK.md l.937 | "`lit_h-0001` to `0009` cover one order type each": it is `0002` to `0010` | Medium | Fixed (`8ffba006`) |
| F-19 | docs/curves/calib-stability.md | 24 em dashes as empty table cells | Low | Not fixed: the page is generated by `tools/gallery_r2.py` from stored run data; change the generator in a round that reruns `calib_stability.py` |
| F-20 | benchmarks/targets.md | One em dash | Low | Not mine (benchmarks/ owned by another lane) |
| F-21 | docs/developer-guides/r1-infra.md, r2-infra.md | Em dashes as empty cells | Low | Replaced with "none" |
| F-22 | docs/diagrams/README.md l.656; question bank Q13.17 | "Raw messages exist for one 14-minute sample only": raw recording for the R2 window started 2026-11-19 11:41:24 UTC (HR-130) | Low | Both now name the R2 window |
| F-23 | docs/getting-started/README.md l.71 | "Pages 2 to 32 use the builds that page 1 makes": there are 50 pages | Low | "Later pages" |
| F-24 | docs/getting-started/README.md, rows 36 to 50 | "(available from v0.10.0)" on every stage H row, written before the release | Low | Kept: still true, and the tutorial checker reads these pages; reword in the stage K tutorial pass |
| F-25 | `.github/workflows/tutorial.yml` comment | "pages 2 to 26 reuse it" | Low | Not changed (CI file owned by the coordinator); list only |
| F-26 | `specifications/cli-contract.md` l.4 | Says builds report `contract_version` 1.15.0; l.21 and the runner say 1.16.0 | Medium | **Spec: for the coordinator.** Not edited |
| F-27 | docs/question-bank (set 13) | No questions on dark pool, router, book checksums, lit order types beyond FIFO, multi-asset conventions, auction, FX last look, futures venue, HR-122 check order, workload R miss | Medium | 21 questions added, Q13.27 to Q13.47 (`80ca98d0`), verify script extended |
| F-28 | LEARN.md stage H | No section with a worked example for the book rebuild, the lit engine, the dark pool and the router | Medium | Three sections added (`8ffba006`) |
| F-29 | COOKBOOK.md stage H | No dark pool recipe; lit, router and rebuild recipes were prose only | Medium | Runnable recipes with real Python CLI output (`8ffba006`) |
| F-30 | docs/diagrams | No stage G diagram (G-1), no H-9 diagram, no per-domain flows (plan 14.5) | Medium | Added (`f562921d`); system diagram now shows the gates. Mermaid syntax read by hand; mermaid-cli was not run |
| F-31 | Router against single-venue routing (HR-40) | Pages describe the comparison on 10,000 simulated orders; no result file is in the repository | Medium | No page quotes a figure; ROADMAP H row lists it as carried. **Coordinator: confirm whether a result exists** |
| F-32 | README.md l.107 | Stage J paragraph gives "CLI contract 1.15.0 ... 302 operations" with no current figure anywhere in README | Low | Kept as stage J history; current 1.16.0 and 358 operations are in Status at a glance (generated) |
| F-33 | docs/getting-started tutorial 48 | Lead text "three misses included" refers to workload S; workload R miss is in its notes (l.73) | Low | Kept; the page states the R miss with the label |
| F-34 | docs/diagrams/README.md, "Shortfall decomposition" | Mermaid parse error: edge labels with parentheses were unquoted, so the diagram showed "Syntax error" on the site (found in the browser check, 2026-11-19) | Medium | Labels quoted; all 50 diagrams on the page and the one on ARCHITECTURE render with no error (checked in the built site) |

### Evidence classes and labels (spot check)

Read in full: the stage H parts of README, LEARN, COOKBOOK, ARCHITECTURE, the release notes and the new question-bank entries. Every numeric claim checked there names a golden, spec, results file or an observed run. Required labels present where the claim appears: "simulated" on every venue output, "crypto venue; not equities or rates" on recorded data, "local laptop, not the acceptance machine" (or "laptop under WSL, not the acceptance machine") on H-9 figures, workload R stated as a MISS. "placeholder weights" has no occurrence yet: no SIMM number with sensitivity-based weights exists until stage K. Pages before stage H were not re-read line by line for evidence classes in this round.

### LSE / LSEG

Two mentions remain, both exclusion statements, not citations: `specifications/09-microstructure/asset-conventions.md` l.25 and `specifications/stage-h-rulings-multiasset.md` l.26 (HR-99: "No London Stock Exchange or LSEG material"). The two legacy citations recorded on 2026-11-17 are not in the repository any more: `specifications/r6-rulings.md` R6-7.4 (l.31) now cites Strata and QuantLib only, and "Standard (LSE/OCC)" was in `R5_STAGE_D_AUDIT.md`, which is outside the repository. Nothing removed.

## Coverage of stage H areas (after this branch)

| Area | LEARN | Question bank | Cookbook | Diagram |
|---|---|---|---|---|
| Schedules and Almgren-Chriss | yes | Q13.1 to Q13.9 | yes | AC frontier |
| Impact models | yes | Q13.12, Q13.13 | yes | (frontier page; none for impact) |
| Order book and matching | yes (new) | Q13.16, Q13.32 to Q13.37 | yes, runnable (new) | matching engine state, crypto data path |
| Dark pool and router | yes (new) | Q13.27 to Q13.31 | yes (new) | simulated venue topology |
| Venue analytics and TCA | yes | Q13.10, Q13.11, Q13.23, Q13.25 | yes | shortfall decomposition |
| Low-latency book | yes | Q13.26, Q13.46 | results only | H-9 (new) |
| Paper trading | yes | Q13.19 to Q13.21, Q13.47 | yes | ledger flow, paper order lifecycle |
| Multi-asset conventions and venues | yes | Q13.38 to Q13.44 | yes | multi-asset venues |

By domain: 01 to 11 each have LEARN material, a question set and recipes; domain 12 (platform) has none, as nothing is built. Per-domain flow diagrams now exist for all 12.

## Docs plan gaps G-1 to G-12

| Gap | State after this branch |
|---|---|
| G-1 stage G diagram | Closed (`f562921d`) |
| G-2 glossary market impact split | Closed earlier (GLOSSARY "Quadratic cost (stage I)" and "Market impact") |
| G-3 glossary SIMM rewrite | Open, stage K (SIMM on placeholder weights not built) |
| G-4 domain organisation | Partly: COOKBOOK domain index added (`8ffba006`); LEARN still stage-ordered |
| G-5 risk and capital term structures on the curves page | Open, stage K |
| G-6 validation rungs page | Partly: `docs/validation/README.md` and per-model checklists exist; no model is at Validated |
| G-7 release-notes template | Closed (`docs/releases/TEMPLATE.md`) |
| G-8 ROADMAP structure | Closed for H and K rows (dated, tagged); R1 and R2 sections kept as history |
| G-9 recorded feeds page | Closed (`docs/data/recorded-feeds.md`) |
| G-10 simulators page | Closed for stage H (`docs/simulators/README.md`); stage K extends it |
| G-11 model risk tiering and reserves | Partly: tiers in `docs/model-inventory.md`; aggregation and reserve dashboard open, stage K |
| G-12 references free and read marks | Closed (`docs/references.md` marks Free, Read, Paywalled, Not opened) |

Also from the plan's stage H list: `docs/benchmarks/r4-api.md` (H-5 p50/p99 page) does not exist; H-5 has one local Java run only (release notes). Open.

## For the coordinator

1. F-26: `specifications/cli-contract.md` l.4 says 1.15.0 (spec owner).
2. F-31: is there an HR-40 router-against-single-venue result? Pages quote none.
3. F-25: `tutorial.yml` comment, and F-20 `benchmarks/targets.md` em dash (other owners).
4. The simulator ADR ("simulators are not the library") is undecided and now carried to stage K.
