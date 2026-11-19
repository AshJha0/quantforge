# K-8: what "the default grid" is (fact record, 2026-11-19)

Written by the K-8 audit-response lane for audit finding KA-B1 (`STAGE_K_R1_AUDIT_B.md`, different-model audit, 2026-11-19). It records facts only. The ruling that follows from them is KR-113 (`specifications/stage-k-rulings-w1.md`).

**Plain statement.** Neither Bermudan operation has a default grid. The phrase "default grid" is a documentation habit, and the repo uses it for two different grids: 201/100 in the stage G pricing spec and in every K-8 file, 101/50 in the R6 use restriction that K-8 was meant to lift.

## 1. What the operations do when the caller passes no grid (read and measured)

`grid` `{nx, steps_per_year, width}` is a required input of `rates.shortrate.bermudan_swaption` and `rates.shortrate.bermudan_ladder`. No build fills in a value.

| Where | Evidence (read 2026-11-19 at `0b5ca451`) |
|---|---|
| Contract and spec | `specifications/04-pricing/short-rate-models.md`:92 lists `grid` `{nx, steps_per_year, width}` among the inputs with bounds and no default; `specifications/cli-contract.md`:544 adds `method` (optional, default `G18_IMPLICIT`) and says nothing of a grid default |
| Python | `python/quantforge_core/cli/ops_shortrate.py`:122-124 (`_grid`: `i.object("grid")`, `g.integer("nx")`, `g.integer("steps_per_year")`, `g.real("width")`) for the swaption; `python/quantforge_core/cli/ops_lmm_xva_frtb.py`:76, :89-90 for the ladder |
| Java | `java25/src/main/java/org/quantforge/cli/OpsRateModels.java`:50-54 (`in.object("grid")`, `g.integer("nx")`, `g.integer("steps_per_year")`, `g.real("width")`), used by both operations (:185-186, :360) |
| C++ | `cpp26/src/cli/ops_shortrate.inc`:186-190 (`in.need("grid")`, `g.integer("nx")`, `g.integer("steps_per_year")`, `g.real("width")`), used at :251 and :282 |
| Rust | `rust/crates/quantforge-cli/src/ops/shortrate.rs`:282-287 (`sub(i, "grid")?`, `g.int("nx")?`, `g.int("steps_per_year")?`, `g.f64("width")?`), one arm for both operations (:275) |

Measured 2026-11-19 with the four-build probe (`_h4ci/probe/run.py`, builds of the stage H worktree; the grid handling dates from stage G): both operations, inputs of `k8_k-0001` without `method`.

| Request | Python | Java | C++ | Rust |
|---|---|---|---|---|
| no `grid` | `E_SCHEMA` | `E_SCHEMA` | `E_SCHEMA` | `E_SCHEMA` |
| `grid` without `nx` | `E_SCHEMA` | `E_SCHEMA` | `E_SCHEMA` | `E_SCHEMA` |
| `grid` without `steps_per_year` | `E_SCHEMA` | `E_SCHEMA` | `E_SCHEMA` | `E_SCHEMA` |

The same answers for both operations. (The `error.field` text differs, `grid.nx` in Python against `nx` in the other three; only `error.code` is compared by the contract.)

## 2. What each document means by "default grid" (read)

| Document | Grid meant | Evidence |
|---|---|---|
| Stage G pricing spec | 201/100 | `specifications/04-pricing/short-rate-models.md`:111, "At the default grid (201 nodes, 100 steps a year)" (commit `ee9a074b`, 2026-11-10). It is the grid of 12 of the 17 `bermudan_g` goldens |
| R6 use restriction, spec | 101/50 | `specifications/06-risk/aad-core.md`:18: the heading says "not for hedging at the default grid" and the measurement that follows is "At 101 space points and 50 steps a year" (commit `5fa5d6ca`, 2026-11-12). All five `aadladder_g` goldens run at 101/50 |
| R6 use restriction, model inventory MG-6 | 101/50 | `docs/model-inventory.md`:619, "not for hedging at the default grid 101/50" |
| R6 release notes and handover | 101/50 | `docs/releases/v0.8.1.md`:105, "The ladder at the default grid 101/50 is **not for hedging**"; `program/R6_HANDOVER.md`:260, "the default grid (101/50)" |
| Plan row R6-27 | 101/50 measured, "default grid" in the restriction wording | `QUANTFORGE_PLAN.md`:629: "at the golden grid (101 points, 50 steps a year) ... a use restriction (\"not for hedging at the default grid\")" |
| Plan row K-8 (14.8) | not stated | `QUANTFORGE_PLAN.md`:700: "at the default grid every ladder entry is within 1% of the converged model derivative" |
| Stage K start file, owner-approved 2026-11-18 | 201/100 | `STAGE_K_START.md`:21 (K-8c acceptance "at 201/100"), :80 (K-QB: "If K-8c misses 1% at 201/100 ..."), :95 (owner: yes) |
| K-8 spec | 201/100 | `specifications/06-risk/bermudan-ladder-k8.md`, table header "201/100 (default) \| 101/50 (golden)" and acceptance 2 "At the default grid 201/100" |

## 3. When 201/100 entered the K-8 spec (read, `git log --follow -p`)

In the first commit of the file, `1bbfdf7e` (2026-11-18 20:18 UTC): line 11 "201/100 (default) | 101/50 (golden)" and acceptance 2 "At the default grid 201/100". That is before the first acceptance run (`oracle/K8_ACCEPTANCE_W1.json`, 2026-11-18) and before the method was revised. Acceptance items 2 and 3 are unchanged in `4adb52e1` and in every later commit. The grid was not moved after a miss.

## 4. Did the K-8 lane's "default grid 201/100" match the operation's real default?

No. The operation has no default, so there was nothing to match. 201/100 matched the stage G spec's use of the phrase and the stage K start file the owner approved. It did not match the grid the R6 restriction was written about: MG-6, the v0.8.1 notes and the R6 handover call 101/50 "the default grid", and `aad-core.md`:18 gives its figures at 101/50. A reader of the restriction therefore reads "default grid" as 101/50, where the K-8 method was never judged and, measured since, misses 1% on two of the three cases (KR-113).

Consequence, stated without softening: the K-8 lane did not redefine the grid to pass (section 3). But KR-110 lifted a restriction worded "at the default grid" without naming a grid, on evidence at 201/100 only, while the restriction's own text and inventory entry describe 101/50. Audit finding KA-B1 is correct.
