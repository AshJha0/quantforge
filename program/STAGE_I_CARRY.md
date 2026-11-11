# Stage I carry-overs from stage G: status (2026-11-11)

Lane `stage-i-carry`. Items as numbered in `STAGE_I_START.md` ("Carry-overs from stage G").

| # | Item | State |
|---|---|---|
| 1 | Rust mutation kill tests | Done. All 8 sampled survivors are now killed (below). |
| 2 | G-42b (six ORE runs) | Not attempted: needs WSL with about 6 GB free. |
| 3 | 50-digit regeneration of the `expsim_g` PFE goldens | Done: all 96 value cases regenerated, every value within 9.2e-4 of the runner limit of the old one, all four builds pass 102/102 on the new goldens; committed (below). |
| 4 | Formal G-9 AAD timing | Deferred: the machine was not quiet (below). |
| 5 | C++ ASan/UBSan on wave 4c | Not attempted: needs WSL. |
| 6 | FRTB CSR securitisations | Decided: out of scope with the documented limit, a candidate for a later "FRTB completion" item together with DRC. Note: `STAGE_I_CSR_SEC_DECISION.md` in the plan folder. |

## 1. Rust mutation

PR #31 (`Mutation by stage`, run 43073386336) gave no Rust result: bonds, credit_options and credit ended with exit 143 after a runner shutdown signal (at 6, 33 and 60 minutes), and exotics was cancelled. The earlier attempt (run 43069561885) was cancelled the same way. No mutation run on `main` covers these modules after the merge.

The latest complete runs are the stage F ones on the same source positions (stage G only added code; `cargo mutants --list` shows the same mutants at the same line and column):

| Module | Run (job) | Sample of 12: either killed | Survivors (unit and golden) |
|---|---|---|---|
| credit | 42888111129 (130081816617) | 8 | 4 |
| credit_options | 42888111129 (130081816625) | 12 | 0 |
| bonds | 42705795220 (129462885516) | 8 | 4 |
| exotics | 42705795220 (129462896160) | 12 | 0 |

Each survivor was applied in a scratch copy of `rust/` and the tests were run (`cargo test -j 2 -p quantforge-core --lib -- bonds:: credit::` and `--test bonds_mutants`):

| Mutant | Killed by |
|---|---|
| `credit.rs:197:64` `+` to `*` in `e_terms` | `credit::tests::e_terms_series_and_closed_form` (stage G) |
| `credit.rs:197:31` `+` to `-` in `e_terms` | same |
| `credit.rs:197:53` `*` to `+` in `e_terms` | same |
| `credit.rs:497:13` `&&` to `\|\|` in `CdsPrice::is_all_finite` | `credit::tests::finite_checks_see_every_field` (stage G) |
| `bonds.rs:405:16` `-=` to `/=` in `conversion_factor` | `tests/bonds_mutants.rs` `conversion_factor_counts_a_part_month_down` (new) |
| `bonds.rs:460:64` `-` to `/` in `futures_basis` | `net_basis_vanishes_at_the_implied_repo` (new) |
| `bonds.rs:554:31` `+` to `-` in `fit_nelson_siegel` | `fit_raises_the_damping_until_a_step_is_accepted` (new) |
| `bonds.rs:567:50` `*` to `/` in `fit_nelson_siegel` | same |

Why CI gave nothing: mutants such as `bonds.rs:58` `k += 1` to `k *= 1` or `-=` in `periods` (and `credit.rs:157` alike) make the schedule loop push to a `Vec` forever; the test eats the runner's memory and the runner agent dies (exit 143) before any result is written. Exotics, separately, needed 89 of its 90 minutes in stage F and has more mutants now. Fix on branch `ci-rust-mutation-fix` (commit 5a02b9a, cut from main, pushed on the owner's instruction, no PR): an 8 GiB address-space cap on every test binary (cargo target runner with `ulimit -v`) and on the golden check (`prlimit`, `QF_MUTANT_AS`), `timeout-minutes` 180, and a `paths` dispatch input that plans the run as a pull request touching those files. Verification run, dispatched 2026-11-11 20:20:

```bash
gh workflow run mutation-stage.yml -R AshJha0/quantforge --ref ci-rust-mutation-fix -f max=12 -f paths="rust/crates/quantforge-core/src/bonds.rs rust/crates/quantforge-core/src/credit.rs rust/crates/quantforge-core/src/credit_options.rs rust/crates/quantforge-core/src/exotics.rs"
```

Run 43095428122 ended `startup_failure` with no jobs after about 15 minutes queued; the workflow file parses and the same file started normally on the next dispatch, so the failure is taken as transient on GitHub's side. Re-dispatch (same command): run 43100924809. Its plan job succeeded and all four Rust jobs (bonds, credit, credit_options, exotics) started.

At the final check (2026-11-11 23:33): run 43100924809 still in progress. All four Rust jobs (bonds, credit, credit_options, exotics; jobs 130792006349, 130792006286, 130792006258, 130792006345) started at 21:11 and are inside `golden_mutants.py` after 140 minutes; none was killed, so the memory cap holds. **Unverified: no result, so no per-module caught, missed or timeout counts and no survivors yet.** Before the fix bonds died at 6 minutes; in stage F it finished in about an hour, so the cap may be turning runaway mutants into slow timeouts. The job limit of 180 minutes falls at 00:11. If a job hits it, `golden_mutants.py` writes its JSON only at the end and the artifact will be empty: then the next adjustment on `ci-rust-mutation-fix` is to pass `--timeout` (cargo-mutants per-mutant limit) and to write partial results as they come. Open: read the run's result, record each module, write kill tests for any survivor (new files under `rust/crates/quantforge-core/tests/`); the branch reaches main through the stage I PR.

## 3. expsim_g PFE regeneration

The generator `oracle/python/gen_stage_g_w4c.py` (function `golden`, unchanged) runs on all 96 cases with 2 worker processes, writing to a scratch folder, never over the committed `oracle/ore/W4C_GOLDEN_RAW.json`. Note: the generator works at `mp.mp.dps = 25` (the suite tags it `mpmath-25-quadrature`); "50-digit" in the carry-over list and in `fix_w4c_pfe.py` refers to this generator. It was run as committed.

- Started 2026-11-11 19:24 local, Windows process 18468 (`cmd.exe` running `run_regen.cmd`).
- Folder: `C:\Users\ashis\AppData\Local\Temp\claude\615d9a8404c697b8\68854005-fd86-4dbf-8f7c-4acb00304417\scratchpad\pfe\`. Log `regen.log` (one line per case, `DONE` and `EXIT 0` at the end); partial results `regen_partial.jsonl`; full result `W4C_GOLDEN_RAW.regen.json`.
- Check: `python compare.py` in that folder (it reads the partial file until the full one exists) prints the largest absolute difference and the largest difference over the runner limit `1e-4 + 1e-8 max(|a|, |b|)`.
- Finished 2026-11-11 22:48 (forward job 70 cases, reverse job 26, merged by `compare.py`). Both jobs then stopped.
- Result over all 96 value cases (4,104 values): 1,683 values changed; largest |diff| 8.6e-5 (`expsim_g-0075`, set P3, `pfe_99` at date index 5, on a value of 10,756,015); largest |diff|/limit 9.2e-4 (`expsim_g-0040`, S20R, `pfe_95` index 8). Every value is far inside the runner limit `1e-4 + 1e-8 max(|a|, |b|)`.
- Four builds on the new `expsim_g.json` through the neutral runner (observed, this machine, 2026-11-11 22:55 to 23:07, Rust, C++ and Java CLIs built by their lanes from `stage-i` that evening, Python from this branch's source): Rust, C++, Java and Python each 102 of 102.
- Committed: `oracle/ore/W4C_GOLDEN_RAW.json` (the regenerated raw file), `datasets/golden/stage_g/expsim_g.json` (expected outputs of the 96 value cases replaced, inputs, tolerances, tags and the 6 error cases unchanged; compact form as the generator writes it), and the `expsim_g` lineage hash in `docs/model-inventory.md` (now `49b806c2...65ba`). `governance_gate.py` and `check_hygiene.py` exit 0.
- Not redone: `ORE_CHECK_4C.json` and the G-42 count, which need the ORE outputs (not in git). The changes are at most 8.6e-5 absolute, far below ORE's Monte Carlo standard errors, so the count is not expected to move; the G-42b re-test will recount on the new goldens.
- A copy of every result file is in the plan folder, `stage_i_pfe_regen/`.

## 4. G-9 AAD timing (deferred)

Not run: five other lanes were building, and the PFE regeneration held two cores. A timing taken under that load would not be the formal record. Next time, on a quiet machine (no builds, llama-server paused by the owner), one language at a time, each from the repo root:

```bash
cd rust && cargo bench -p quantforge-bench --bench aad_ladder
```

```bash
cd python && uv run pytest tests/test_stage_g2.py::test_ladder_cost_ratio_report -s -q
```

```bash
cd java25 && mvn -B -q test -Dtest=ShortRateTest#aadCostRatioG9
```

```bash
cmake -S cpp26 -B cpp26/build-rel -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build cpp26/build-rel -j 2 --target quantforge_core_tests && cpp26/build-rel/quantforge_core_tests "Q3b AAD ladder*" -s
```

Each prints the median-of-21 (after 5 warm-ups) ratio of price plus ladder over one price; G-9 passes at `<= 5`. Record the four ratios, the two medians and the machine state in the model inventory (MG entry of the Q3b ladder).
