# Stage F handover

From the stage F spec and oracle session to the four language sessions and the lanes. Append-only. Each wave section says what a language session may read. Never read anything under `oracle/`: that is the oracle, and reading it breaks the clean room.

All stage F goldens are in `datasets/golden/stage_f/`, run through `conformance/runner/runner.py` (it finds them by suite name). Always read `specifications/cli-contract.md` (block "Stage F") and `specifications/stage-f-rulings.md` with any stage F slice.

## T: tightened acceptance rows (2026-11-09)

Plan item 13.2 T. These rows replace the "Acceptance" cells of plan section 12 for A3, A4, A5, A7, Q3a, Q1 and M. They are copied into `QUANTFORGE_PLAN.md` section 12. The stage that owns each item may not change a parameter without a written ruling; a parameter changed after results are seen is a prereg breach.

Common parameters: every random draw uses the `core.rng` generator (`01-core/rng.md`) with seed `20261109` unless a row says otherwise. "SE" is the binomial or sample standard error of the stated estimate. Every count, threshold and seed below is fixed before the stage starts.

| ID | Stage | Acceptance (rewritten) |
|---|---|---|
| A3 | J | **Prereg** `research/prereg/A3-drift.md`, frozen before code. Null data: i.i.d. N(0,1), 2,000 paths of length 1,000, seed 20261109. Break data: same, with a mean shift of +1.0 sigma (CUSUM, Page-Hinkley) or a variance ratio of 2.0 (PSI, KS) at t = 500, 2,000 paths, seed 20261110. **CUSUM** two-sided, k = 0.5, h = 5.0 (Siegmund ARL0 about 469, ARL1 about 10.3): empirical ARL0 on 2,000 null paths of length 5,000 lies in [400, 540]; median detection delay at most 15 steps and at least 95% of break paths alarm within 40 steps. **Page-Hinkley** delta = 0.5, lambda = 50: same delay rule. **PSI** 10 bins at the reference-window deciles, reference window 250, test window 250, threshold 0.25: false alarms at most 2% of null paths; at least 95% of variance-break paths alarm by t = 750. **KS** two-sample at level 0.05, windows 250: null rejection rate in [0.035, 0.065] (3.5 SE band at 2,000 paths); at least 95% power on the variance break. Every number reported with its SE. |
| A4 | J | Simulated 2-state Gaussian HMM: transition matrix [[0.95, 0.05], [0.10, 0.90]], means (0.0, 2.0), standard deviations (1.0, 1.5), initial (0.5, 0.5), T = 5,000, seed 20261109. Baum-Welch from the fixed start [[0.8, 0.2], [0.2, 0.8]], means (-0.5, 1.5), sd (1, 1); stop when the log-likelihood gain < 1e-10 or at 1,000 iterations. **Recovery:** each transition probability within max(0.02, 3 SE) of truth, SE from the observed information. **Bit-reproducible:** two runs of the same binary on the same OS give an identical SHA-256 of the IEEE-754 bytes of all fitted parameters. **Across OSes and languages:** parameters within 1e-9 relative, log-likelihood within 1e-9 relative; the Viterbi path (ported, goldens) identical in all four languages on 20 golden cases, including ties broken to the lower state index. The Markov-switching AR(1) uses the same tolerances on its own frozen parameters. |
| A5 | G | **Domain (Heston):** v0 in [0.005, 0.25], kappa in [0.2, 8], theta in [0.005, 0.25], xi in [0.05, 1.5], rho in [-0.95, 0.2], log-moneyness ln(K/F) in [-0.5, 0.4], T in [0.02, 5]. **(SABR):** alpha in [0.01, 1], beta in {0, 0.5, 1}, rho in [-0.9, 0.9], nu in [0.05, 2], ln(K/F) in [-0.5, 0.5], T in [0.02, 10]. **Test set:** 100,000 points from the `core.sobol` sequence (Joe-Kuo directions, first 1,023 points skipped), mapped affinely; then 10,000 more points from the same sequence restricted to the wing (abs(ln K/F) > 0.3) and short-expiry (T < 0.1) sub-boxes, so these regions hold at least 10% of the set. **Pass:** max abs implied-vol error at most 1 bp (1e-4 in vol) against the full pricer over all 110,000 points, and 99.9th percentile at most 0.5 bp. Any point outside the domain returns `E_DOMAIN`, tested at each of the 14 faces plus NaN and infinity. Speed-up is measured and reported (G2 harness), not gated. Never in goldens; inventory tier "challenger". |
| A7 | K | **CI (stub model, recorded transcripts only):** malformed tool calls rejected by schema (at least 40 recorded cases, 100%); every number in an answer carries a provenance ID that resolves to a tool result in the same transcript (100% of recorded answers); red-team refusal on the recorded red-team transcripts (100%). CI never runs a real model. **Manual release check (real local model):** an eval set of at least 300 items; pass when the Wilson 95% lower bound of the accuracy is at least 0.95 (at n = 300 that needs at least 293 correct). A red-team set of at least 50 items written by someone other than the author of the server (another person, or a different-model session with no view of the server code): 100% refused. Results, model name, version and date recorded in the release notes. |
| Q3a | F | **Book:** 500 SOFR OIS swaps from `core.rng` seed 20261109: tenors uniform on the integer years 1 to 30, fixed rate = par + U(-100, 100) bp, payer or receiver with equal odds, notional 1 (risk is per unit notional). Curve: the stage F golden 12-pillar SOFR build. **AAD against bump:** reference = central difference with h = 1e-4 and h = 5e-5 on each par quote (in decimal), Richardson-combined, (4 D(h/2) - D(h)) / 3. Pass when, for every swap and every quote, abs(AAD - ref) <= 1e-10 + 1e-8 x abs(ref). **IFT Jacobian (dZ/dq, all four languages):** same reference on the zero rates at the pillars; pass when every entry satisfies abs(J - ref) <= 1e-11 + 1e-9 x abs(ref). Both bounds are stated per unit notional and per unit quote; the absolute term exists so that entries that are zero by construction (later quotes on earlier pillars) pass only when they are within 1e-11 of zero. |
| Q1 | F | **Reprice:** every input instrument reprices to abs(PV) <= 1e-12 per unit notional, for each of the five methods. **Against QuantLib** (version recorded per case, own convention objects, rule 11.2.5): (a) interpolation only, on the same pillar discount factors: zero rates at 200 dates (every 0.15 years to 30 years) within 1e-12 absolute (continuous zero) against `ConvexMonotone` (Hagan-West: quadraticity 0, monotonicity 1, forcePositive false; amended 2026-11-09 by ruling F-19, because QuantLib's forcePositive helper does not keep section averages) and `MonotonicLogCubic`; (b) full SOFR build (`PiecewiseYieldCurve` with `OISRateHelper`, accuracy 1e-14): zero rates at the same dates within 1e-10 absolute. **Locality** (on pillars, ruling F-22): a change in pillar i changes the instantaneous forward by at most 1e-14 outside the pillar intervals i-2 to i+2 (monotone convex), and changes nothing before the first step boundary at or after the moved quote's start (hybrid step segment). **Smoothness:** monotone convex forward continuous at every pillar (jump <= 1e-12); tension spline second derivative of ln P continuous (jump <= 1e-8); with all discrete forwards positive, the monotone convex forward is >= 0 at 10,000 grid points. |
| M | every stage | Equivalent mutants are listed per language in `oracle/MUTANTS*.md` with one row per mutant: location, operator, author reason, and a **second-reviewer column** that names the reviewer (a person, or a different-model session such as the R5 audit) and the date. A mutant without a second-reviewer entry counts as surviving. The 80% module floor is computed with that rule; the inventory and test-infrastructure scores tables state the count of signed and unsigned equivalents. |

## E1: non-finite inputs (spec rule, 2026-11-09)

Normative text: `specifications/stage-f-rulings.md` F-1 to F-4 and `specifications/cli-contract.md` block "Stage F". Summary:

- A real-number input may arrive as one of three exact strings, `"NaN"`, `"Infinity"`, `"-Infinity"`, which the build parses to the binary64 value. Any other string in a real field is still `E_SCHEMA`. The strings in an integer, date or enum field are `E_SCHEMA`.
- The first rule check of every operation (after `E_PARSE`, `E_SCHEMA`, `E_LIMIT`) is: every real input, at any depth, is finite. Otherwise `E_DOMAIN`.
- `-0.0` is finite and is treated exactly as `+0.0`: the result equals the `+0.0` result (the runner treats the two zeros as equal in outputs).
- Raw kernels reachable from the library API (not the CLI) either check the same rule or are private, or documented as unchecked in the API docs.

Goldens: `datasets/golden/stage_f/e1_*.json`, generated from the smallest ok golden case of every operation. For each real leaf (array: element 0 and, when longer, the last element) there are three non-finite cases expecting `E_DOMAIN`, and one negative-zero case. The negative-zero case either copies the expected result of a base case whose leaf is exactly zero, or is paired with a `+0.0` anchor case and expects `{"status": "same_as", "case_id": <anchor>}` (runner support added in `conformance/runner/runner.py`; the anchor expects `{"status": "any"}`, which passes on any well-formed result and fails on a crash).

## E4: name map (2026-11-09)

`specifications/name-map.json`, generated by `tools/gen_name_map.py` from the specs (operation names and their input and output keys) and from the shape rules in `specifications/stage-f-rulings.md` F-5. Each operation row gives the canonical library name in each language: Rust `snake_case` module path, Python `snake_case`, Java `camelCase` method in a `PascalCase` class, C++ `snake_case` in namespace `qf::<domain>`. The quality_gate check (infra lane) compares public symbols against this file. The ADR (docs lane) states the rules; the map is the data.

## Q5b: spec template field (2026-11-09)

`specifications/README.md` gains a required section for every spec that defines a numerical method: `## Convergence and limit cases`, holding (1) the asserted convergence order with the grid or path sequence used to measure it, and (2) at least one limit case with a closed form or an independent reference. The quality_gate check (infra lane) fails a spec that defines an iterative, grid, quadrature, tree or Monte Carlo method without the section, or with the section empty. Stage F specs all carry it.

## WAVE 0 READY (2026-11-09)

Language sessions may start F2 (E1, G4 with the name map, G9). Read:
- `specifications/stage-f-rulings.md` (F-1 to F-6)
- `specifications/cli-contract.md` (block "Stage F operations")
- `specifications/name-map.json` (data; regenerate with `python tools/gen_name_map.py`, check with `--check`)
- `specifications/edge-case-register.md` (rows F1 to F3)

Goldens: `datasets/golden/stage_f/e1_*.json`, 5,207 cases in 23 files over 206 operations (1,052 Real leaves; 24 operations have no Real input and get no case, listed in `oracle/E1_SUMMARY.json`). Build notes: implement F-1 in the JSON reader's Real conversion, and F-2 as one generic walk before dispatch only if the walk knows which fields are Real; a key-name heuristic is not enough (`initial_variance` is a string or a Real). The anchors (`zero_anchor` tag) expect any well-formed result, so a `+0.0` that is outside an operation's domain may return its own error; its `-0.0` twin must return the same.

### E1 golden fix (2026-11-09, from the C++ session)

- `same_as` (negative-zero) cases no longer copy the base case's `extra_checks`: those hold expected values for the base input, not for the zeroed input.
- A path counts as Real only if an **ok** golden writes a float there. Error cases (such as `rulings-0001`, `n = 4.0` → `E_SCHEMA`) no longer make an Integer field Real, so no case puts a token in `n` of `core.integrate.*`; F-1 makes that `E_SCHEMA`, untested here. `core.integrate.gauss_legendre` `a` and `b` are Real by `01-core/integration.md` (an explicit override in the generator).
- Now 5,207 cases. Case ids were renumbered: re-run the whole `e1_*` set, do not compare by old id.

## WAVE 1a READY (2026-11-09 21:10): F6 model fixes and F1 Q1 interpolation

Q4 (joint solve, funding curve) is wave 1b: its section below is not ready until a later "WAVE 1b READY" heading says so.

Read with every slice: `specifications/cli-contract.md` (block "Stage F operations"), `specifications/stage-f-rulings.md` (F-7 to F-27), `specifications/edge-case-register.md` (rows F4 to F10), `conformance/tolerances/policy.yaml` (new classes `jacobian`, `standard_error`).

### F6 R7 CDS index option
- New operation `credit.cdsindex.option_price`. Read `specifications/04-pricing/credit-options-and-copulas.md`, section "`credit.cdsindex.option_price`" (and the stage E legs above it). Goldens `stage_f/cdsidx_f.json` (45 cases).
- Build notes: the strike annuity is measured from `expiry` on the flat hazard that reprices the strike; solve it to 1e-15. Add a property test: payer minus receiver equals `N A (F_adj - K_adj)` to 1e-10 relative on your own outputs.

### F6 R8 GARCH estimate
- New operation `vol.garch.estimate`; new optional inputs on `vol.garch.loglik`. Read `specifications/05-volatility/garch.md`, section "Stage F additions". Goldens `stage_f/garch_f.json` (16 cases).
- Build notes: finish with Newton steps on an exact gradient and Hessian (or 1e-10-accurate ones) until the relative step is below 1e-12; parameters are judged at 1e-6 relative, standard errors at 1e-5. Java needs its own `lnGamma` (Lanczos g = 7, 9 terms, or Stirling with recurrence).

### F6 R10 VIX and local vol
- `vol.vix.*` quotes may be `null`; `vol.local.dupire` behaviour at slice expiries is pinned. Read `specifications/05-volatility/vix-index.md` and `local-and-forward-vol.md`, sections "Stage F additions" and "Continuity at slice expiries". Goldens `stage_f/vix_f.json` (10 cases, including the Cboe sample strip) and `stage_f/lvc_f.json` (3 cases).
- Build notes: a null series is removed from its own side's walk before it starts; it is neither a zero bid nor a break in a zero run. Add the continuity property tests listed in the spec.

### F1 Q1 interpolation
- New `interpolation` values `MONOTONE_CONVEX`, `MONOTONIC_LOG_CUBIC`, `TENSION_SPLINE`, `HYBRID` everywhere a curve object or a bootstrap takes one; new operation `rates.curve.inspect`. Read `specifications/02-curves/curve-framework.md`, section "Stage F: pluggable interpolation". Goldens `stage_f/curve_f.json` (84 cases).
- Build notes: follow the convex monotone branch rules in order, including the `eta = 0` limit; `forcePositive` is off (ruling F-19). The monotonic log cubic filter reads only chord slopes, node by node. Non-local methods need a global bootstrap (ruling F-21): Newton on all pillars works. Extrapolation of the new methods uses the left-hand forward at the last pillar.

### F1 Q4 joint solve and funding curve (NOT READY: wave 1b)
- New operations `rates.curve.joint_solve` and `rates.funding.curve`. Read `specifications/02-curves/joint-solve-and-funding.md` in full, and the instrument specs it names (`ois-curves.md`, `projection-and-fra.md`, `cross-currency.md`, `futures-convexity.md`, `meeting-steps.md`). Goldens `stage_f/joint_f.json` (pending cases).
- Build notes: the Jacobian is `-(dR/dx)^{-1} dR/dq`; central differences on `x` with `h` near 1e-7 meet the `jacobian` class. Structural zeros must be exact zeros (do not invert the full matrix with pivoting that mixes blocks; a block solve or a plain LU of a block lower-triangular matrix keeps them). `turn_sensitivity` is exactly 0 off the turn.

### Outside-oracle status (rule 11.2.5, ruling F-23)
`oracle/python/outside_f.py`: curve_f 48 of 84, vix_f 3 of 10 (Cboe sample), cdsidx_f, garch_f and lvc_f none (no free outside source). Stage F so far 51 of 158 = 32%, below the 60% floor; Q4, F4 (scipy, BCBS worked examples) and the remaining waves must raise it (ruling F-23).

### Open items
- R7: the Pedersen (2003) worked example is not reproduced (paper not freely available); added to the known issues for a human with access.
- T amendments made by this wave (rulings F-19, F-22): the Q1 row now names `forcePositive = false` and states locality on pillars. Both are written into the plan's section 12.10 and into the T table above.

### Where to resume (spec session checkpoint, 2026-11-09 22:05)
- Wave 1b (Q4): `cd oracle/python && uv run python -u -W ignore gen_stage_f_q4.py` writes `datasets/golden/stage_f/joint_f.json` (it prints a line per system solved and per bump-and-rebuild check). Then `uv run python -W ignore outside_f.py` (QuantLib check of the OIS + projection systems and the stage F share), the stub replay `python conformance/runner/runner.py --impl stub --suite joint_f`, fill the `TODO wave 1b` lineage hashes in `docs/model-inventory.md` (MF-5, MF-6), and add a "WAVE 1b READY" heading here.
- R8 coverage study: `uv run python -W ignore gen_stage_f_f6.py COVER` (about an hour; writes `oracle/R8_COVERAGE.json`, asserts the [0.90, 0.99] band).
- Regenerate E1 after new operations land: `gen_stage_f_e1.py` reads only suites outside `stage_f`, so the stage F operations (`credit.cdsindex.option_price`, `vol.garch.estimate`, `rates.curve.inspect`, `rates.curve.joint_solve`, `rates.funding.curve`) still need E1 cases: change its skip rule to skip only `e1_*` files, then rerun.
- Then waves 2 and 3 as in the task order (F3 and F4 specs, the E9 MC hash golden, F5 book).


## WAVE 1b READY (2026-11-09 22:12): F1 Q4 joint solve and funding curve, with one open system

The Q4 section above ("F1 Q4 joint solve and funding curve") is now ready, with `joint_f` at 13 cases: three joint systems (SOFR meeting steps fitted to SR3 futures with convexity and a solved year-end turn; SOFR + term log-linear; SOFR + term monotonic log cubic), four error cases and six funding-curve cases (one is the zero-spread limit). Stub replay 13 of 13. Each system's IFT Jacobian matches a bump-and-rebuild of the whole system (Richardson, `h = 1e-4`) within `1e-9 + 1e-6 |ref|`; structural zeros are exact. QuantLib 1.44 rebuilds the log-linear system and its bump Jacobian (counted). The monotonic log cubic system's QuantLib bump Jacobian differs by 3e-6 relative, which is QuantLib's 1e-12 bootstrap accuracy over a 1e-4 bump, so it is not counted.

**Open item (spec session, next turn):** the full system (SOFR monotone convex with a solved turn + term + ESTR monotonic log cubic + EUR xccy) solves to 1.6e-15, but its IFT Jacobian differs from bump-and-rebuild by up to 2e-3, so it is left out of the goldens (`gen_stage_f_q4.py`, `systems()[0]`, skipped in `main`). Suspects: a convex-monotone section at a branch boundary (the method is piecewise in its data, so its Jacobian is one-sided there), or the xccy `dR/dq`. Diagnostic script pattern: solve, `jacobian()`, `bump_jacobian()`, print the worst entries. Builds should implement the full operation regardless; the missing golden does not change the spec.

Outside share after wave 1: 52 of 171 = 30.4% (ruling F-23), below the 60% floor.


### Resume here (checkpoint 2026-11-09 22:15; laptop off at 23:00)
1. **Merge main first.** Part 1 merged to main as PR #25 (`5c8fa9d`): `git merge main` into `stage-f` before any new work.
2. **Four-curve Jacobian mismatch (Q4 open item).** Run `cd oracle/python && uv run python -u -W ignore diag_q4_jacobian.py`. The three committed systems pass (max excess below 0). Only `systems()[0]` fails (up to 2e-3 against bump-and-rebuild), and the script prints its four worst entries last. The 2026-11-09 run was stopped at the shutdown, before that output. Read the worst entries' rows and columns:
   - **XCCY quote columns wrong.** Check `System.dRdq` for `XCCY`: the residual is `L_foreign` and its derivative in `spread` is `sum alpha_i D_f(e_i)` on the foreign discount curve being solved. Also check that bumping `spread` in `bump_jacobian` uses the same key.
   - **USD-SOFR rows wrong** (monotone convex with the turn). Test whether a section sits on a branch boundary (`g0`, `g1` near a rule switch in `interp_f._cm_sections`). If so, either move the quotes off the boundary and assert a margin in the generator, as the stage E goldens do with `away()`, or state in the spec that the Jacobian of a piecewise method is one-sided at a boundary.
   - **Turn column wrong.** Check that the turn unknown's columns in `dR/dx` and the `turn_sensitivity` zeroing agree.

   When it passes, remove the skip in `gen_stage_f_q4.py` `main` (the "OPEN" comment) and rerun it (about 5 minutes). Then rerun `outside_f.py` and the stub replay, update the `joint_f` hash in `docs/model-inventory.md` (MF-5, MF-6), and tell the coordinator the new case count.
3. Then the items in "Where to resume" above: R8 coverage, E1 for the new stage F operations, waves 2 and 3.

**Diagnostic result (2026-11-09 22:17).** Full system max excess 1.99e-3. The worst entries, IFT against bump:
- `USD-SOFR:turn:2026-12-31` / `SOFR-3M`: 0.18997 against 0.19196.
- `USD-TERM-3M` pillars 2028-11-13, 2031-11-12, 2036-11-12 / `SOFR-2Y`: errors of about 5e-4 each.

No XCCY column appears, so the xccy suspect is unlikely. The errors sit in SOFR quote columns (3M near the turn, 2Y), which points to the monotone-convex SOFR curve. Check whether a section near 3M or 2Y switches branch rule under a 1e-4 quote bump (compare `interp_f._cm_sections` branch kinds at `x` and at the bumped solutions). If it does, the 1e-4 Richardson bump straddles a kink: use a smaller bump for the reference (1e-6) and compare again, then either keep the quotes off the boundary with an asserted margin or state one-sided derivatives in the spec.

## Q4 FOUR-CURVE GOLDEN READY (2026-11-10): `joint_f` is now 14 cases, re-run it

The held-back four-curve system (SOFR monotone convex with a solved turn + term + ESTR monotonic log cubic + EUR xccy) is in the goldens as `joint_f-0001`. **Case ids moved by one**: re-run the whole `joint_f` suite, do not compare by old id. Read ruling F-28 and the amended F-26 in `specifications/stage-f-rulings.md`, and the amended `dR/dq` line in `joint-solve-and-funding.md`.

- **Cause:** the 2e-3 mismatch was the bump reference, not the IFT golden. The monotone convex SOFR curve is piecewise in its data, and a middle section changes region about 6e-5 away in the SOFR-2Y quote (SOFR-3M similar), so a `h = 1e-4` Richardson bump straddled a kink. The first and last sections sit at `g1/g0 = -2` and `-1/2` exactly by the endpoint rule; rounding flips there are harmless (the regions agree on that line).
- **Fix (F-28):** the generator halves the reference step from 1e-4 until no interior section changes region under any `+-h`, `+-h/2` bump and the `h^4` error estimate is below half the `jacobian` tolerance. The four-curve case needs `h = 6.25e-6` (in its `verified_by`); the other three keep `5e-5`.
- **Build note (from the Rust lane, thanks):** your own `dR/dx` stencil can also straddle a kink. A fixed five-point 1e-5 stencil puts `turn` / `SOFR-1M` at 0.11714 instead of 0.11790. The oracle's Richardson 1e-5 / 5e-6 central differences give 0.1178976 and pass. Rust's per-column adaptive stencil (shrink until two steps agree) is a good pattern.
- **F-26 amended:** `turn_sensitivity` is exactly 0 for non-spanning instruments only on `OIS_STEPS` curves. On pillar curves it is the honest `dR/dx` column: in the four-curve case `SOFR-1M` has about -0.023.
- **XCCY `dR/dq`:** the spread annuity `sum alpha_i D_f(e_i)`, not -1 (the oracle always used this; the text now says so).
- Stub replay 14 of 14. Outside: still 1 of 14 (the log-linear system); the four-curve case has an xccy curve, which QuantLib cannot build.

## WAVE 2 READY (2026-11-10): F3 sensitivities and F4 portfolio risk

Read with every slice: `specifications/cli-contract.md` (rows F3, F4), `specifications/stage-f-rulings.md` F-29 to F-33, `conformance/tolerances/policy.yaml` (new classes `aad_sensitivity`, `ift_jacobian`), `specifications/name-map.json` (regenerated: 226 operations).

### F3 (suite `risk_f3`, 54 cases): `06-risk/book-sensitivities.md`
- `risk.book.ois_sensitivity` (Q3a, the T row): PVs, par-quote sensitivities and the zero-rate Jacobian of an OIS book. Case 1 is the 500-swap book (core.rng seed 20261109, written into the input). **Rust:** reverse-mode AAD through the IFT (the reference, ruling F-29), plus a unit test against its own Richardson bump (`h = 1e-4`, `5e-5`). **C++, Java, Python:** an exact chain rule (closed form or forward duals). Central differences on the unknowns are not enough for `1e-8` relative. Zero-Jacobian entries above the diagonal are exactly 0 (F-30).
- `risk.curve.pca`, `risk.curve.cross_gamma`, `risk.credit.jtd`: small. PCA's sign rule is the largest-absolute entry positive; repeated eigenvalues are `E_DOMAIN`.
- Goldens come from a 40-digit replica, with no bump in the golden.

### F4 (suites `risk_f4`, 102 cases, and `frtb_f`, 16): `06-risk/var-es-and-backtests.md`, `06-risk/frtb-sa-girr.md`
- VaR/ES: historical, filtered historical (EWMA seeded with the mean square), parametric, Monte Carlo (core.rng, Cholesky). Order statistic `k = ceil(n c)`; ES includes the VaR scenario (F-31).
- Backtests: Kupiec, Christoffersen, traffic light (Basel 1996 zones and plus factors). An LR below 1e-12 is 0 (F-32): implement this, or p-values near 1 fail by 1e-7.
- FRTB-SA GIRR delta under MAR21, three correlation scenarios, with the alternative `S_b` (F-33).

## WAVE 3 READY (2026-11-10): F5 book and use case 4

Read ruling F-34 and the cli-contract rows F5.
- `book.lifecycle.apply`, `book.marks.resolve` (suite `book_f`, 32 cases): `07-portfolio/book-lifecycle.md`. Average cost; expiry, default and roll as trades; marks fall back by source, then to stale within `max_age_days`; IPV flag. This is a new `book` domain in each language (name map).
- `usecase.factor_attribution` (suite `uc4_f`, 27 cases): `04-pricing/use-cases.md` use case 4. OLS with an intercept; `mean_return = alpha + sum contributions`.

### Outside-oracle status after waves 2 and 3 (ruling F-23)
182 of 403 = 45.2% (was 52 of 171 = 30.4%). New outside: PCA 24 (SciPy `eigh`), VaR/backtests 82 (SciPy, NumPy `inverted_cdf`), use case 4 24 (SciPy `lstsq`). The floor of 60% is still not met. What remains has no free outside source: R7 (Pedersen 2003 not available; known issue in the README), GARCH, FRTB (MAR21 has no worked example), the book rules (own conventions), FHS and MC VaR. Raising the share further needs either new outside sources (the `arch` package for GARCH and FHS would be the next candidate, if added to the oracle environment) or a ruling on the floor.

### Deferred to wave 2b (not specified here)
Inflation01, dividend and borrow sensitivity, correlation sensitivity (F3); reverse stress, limits, concentration, liquidity-adjusted risk, portfolio vol by horizon, model-risk reserves (F4); FRTB vega, curvature and the other risk classes. E1 cases for the stage F operations are still missing (`gen_stage_f_e1.py` skips `stage_f`; change it to skip only `e1_*` and rerun).

## R8 coverage study done (2026-11-10)

`oracle/R8_COVERAGE.json`: 200 simulated series of 2,000 per distribution; share of fits whose ±2 SE interval holds the true parameter. NORMAL (omega, alpha, beta) 0.98, 0.94, 0.98; STUDENT_T (omega, alpha, beta, nu) 0.95, 0.935, 0.955, 0.96. Every value is inside the preregistered band [0.90, 0.99], so the R8 standard errors are confirmed. (Run: `uv run python -W ignore gen_stage_f_f6.py COVER`, several hours when the machine is shared.)

### Resume here (spec session checkpoint, 2026-11-10)
State: `stage-f` holds 8d55279 (Q4 four-curve golden, F-28), 9f5a7a5 (waves 2 and 3), a3cd572 (R8 coverage), and this note. Everything is committed locally; **nothing is pushed**.
1. **E1 for the stage F operations.** In `gen_stage_f_e1.py`, change the skip rule to skip only `e1_*` files, rerun, then stub-replay `e1_*`. This adds E1 cases for every wave 1 to 3 operation. Announce the new case count, since ids renumber.
2. **Outside share 45.2% (182 of 403), floor 60%.** Candidates: add `arch` to the oracle environment and check `garch_f` estimates and the FHS cases against it; check FRTB against any published bank or vendor example the R5 audit can find. Otherwise ask the owner for a ruling on the floor for stage F.
3. **Known issues to carry into the release notes:** R7 has no outside case (Pedersen 2003); the FRTB `low` scenario formula needs checking against the BIS PDF (F-33); the equity FRTB parameters were read only in summary.
4. **Wave 2b list** (above): specify it when the lanes are through waves 2 and 3, or move it to stage G with a ruling.
5. Then the R5 audit (Sonnet, read-only) over waves 1 to 3, the docs review, and the part 2 PR and v0.6.0 as in `STAGE_F_RESUME.md`.
