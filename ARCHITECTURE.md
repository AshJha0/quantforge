# Architecture

QuantForge is one repository holding four isolated implementations and the neutral parts around them. The plain idea: a spec says what must be true, the oracle says what the answer is, and a runner that knows no finance compares each language's answer with it. Detail is in `architecture/`; decisions are in `architecture/decisions/`; diagrams are in `docs/diagrams/`.

Sources: each spec ends with a `## Sources` section naming the papers, books and standards (ISDA, BIS MAR21, ARRC and others) it follows; [References](docs/references.md) lists them all by topic with their status.

| Part | Role | May depend on |
|---|---|---|
| `specifications/` | What must be true | Nothing |
| `oracle/` | Expected results, from outside sources and hand cases | Specs, outside libraries. Tests only |
| `datasets/` | Schemas and golden files | Oracle output |
| `conformance/` | Neutral runner and tolerances | Golden files and each CLI's JSON. No financial logic |
| `java25/`, `cpp26/`, `python/`, `rust/` | Four equal implementations | Specs only. Never each other, never the oracle |
| `tools/` | Recorder, forward log, docs site build and Curves gallery | CLI output. No financial logic |

## Rules that shape it

- No language is a reference. The oracle is the source of golden results.
- No shared code, FFI or generated maths between implementations.
- The only interface that counts is the CLI: case JSON in, result JSON out.
- Libraries first, services last. Infrastructure arrives as local adapters in stage K.
- Trading is simulated only. There are no live orders.

The specification remains a shared-error risk: four builds and a hand case can share one misreading. That is why outside libraries are used wherever a licence allows. Validation is self-assessment: there is no second review (owner decision, 2026-11-18).

## Inside one implementation

Stage B adds the pricing framework (`specifications/04-pricing/pricing-framework.md`). The plain idea: terms, cashflows, market data, the model and the answer are five things, kept apart so that one can change without the others. Formally, each language separates instrument, product model, market data, pricing model and valuation result in its API; only the JSON is conformance. Use cases compose these parts and define nothing but their sums.

Stage B calculations are pure functions of their inputs, so stage F can add AD (ADR-0010). Risk is bump and rebuild for now.

## What each stage added

Services, `infra/` and the other domains do not exist yet.

### Stage A: Foundation

Built domain 01, and the neutral parts: `oracle/`, the CLI contract (`specifications/cli-contract.md`), `conformance/`, and the recorder and forward log in `tools/`. Limits: many golden cases rest on hand or replay sources, and the recorder is not scheduled.

### Stage B: FX and rates slices

Built slices of domains 02, 03, 04, 06 and 08, on top of domain 01 in each language. Build order is overnight curve, then projection, then FX. The [Curves gallery](docs/curves/README.md) shows these curves from real CLI runs. It sits outside the four implementations and only reads CLI output. Limits: inputs are synthetic, risk is bump and rebuild with no AD, and hedges are calculations with no connection to a market.

### Stage C: Equity vol slice

Built domain 05 (volatility) and slices of 02, 04 and 06: the equity forward on funding and borrow curves, Black models, Greeks, smiles, the surface and SABR. The plain idea: a vol is an input to a price model, so the forward and the curves come first, the models next, and smiles and surfaces sit on top. Dividends are carried on `C = D/B` and option PVs discounted on `D` (rulings C2, C3). CLI contract 1.4.0 adds one error, `E_ARBITRAGE`. Limits: inputs are synthetic, options are European only, and arbitrage checks run on given points only.

### Stage D: Curves and fixed income

Built the rest of domain 02 (curves) and slices of 03, 04 and 05, in all four languages, from the specs alone: full SOFR and ESTR OIS with curve jumps, dated overnight compounding and IBOR fallbacks, meeting-date step curves, futures convexity, CSA discounting, index basis, joint bootstrap, regularised and robust fits (D1); bonds, repo, bond futures and sovereign fits (D2); cross-currency basis and NDFs (D3); the ISDA CDS model, index CDS and composite curves (D4); dividend, borrow and financing curves, index dividends, corporate actions and TRS (D5); inflation curves and linkers (D6); caps and swaptions (D7); commodity curves and storage (D8); MBS (D9). The curve object gained optional `jumps`. Operation prefixes and spec files are in `specifications/cli-contract.md` 1.5.0. On the oracle side, `oracle/python/gen_stage_d*.py` write the goldens; `specifications/stage-d-handover.md` lists what language sessions may read. Result: at merge `95cbf11` on 2026-11-07, each of the four implementations passed 5,514 of 5,514 golden cases (value-checked and error cases counted together) locally, 331 of them in stage D's 20 suites, and fuzzing with seed 17 found nothing (`conformance/README.md`). Limits: all inputs are synthetic, and several suites have hand or analytic sources only (`specifications/stage-d-rulings.md`).

### R1: credibility hardening (v0.4.1)

No new pricing; the diagrams are in `docs/diagrams/README.md`. Batch mode becomes normative in `specifications/cli-contract.md` 1.6.0: one result line per input line, in order, each equal bit for bit to `run` on that line, with no state between lines. The wire `contract_version` stays 1.0.0. Stream fixtures live in `datasets/batch/`, apart from the goldens, because they test the stream rather than an operation.

R1 also adds three pieces around the libraries, none of them inside a language tree:
- **Scheduled recorder.** `tools/recorder/record.py` runs on GitHub Actions twice each weekday. Hash-chained rows go to the `forward-log` branch, never to `main`, and no raw bytes leave the runner. `gap_monitor.py` reports missed business days and fails the job if one of the last three has no record.
- **Daily workflows.** `tools/workflows/` holds standard-library scripts with no finance in them: they fetch public data, send cases to one `quantforge --batch` process and compare the results with sanity bands in `sanity_bands.json`. All the maths stays in the CLI, so a workflow tests the same code the goldens test.
- **Governance records.** The edge-case register (`specifications/edge-case-register.md`), the model inventory (`docs/model-inventory.md`), calendar provenance (`datasets/calendar_provenance.json`) and tolerances in money (`conformance/tolerances/money.md`). Each has a scheduled or PR check where one is possible: the calendar expiry job and the outside-oracle floor.

### R2: the risk layer (v0.4.2)

Plain idea: risk is not a new model, it is the existing pricers run again on moved inputs. The risk layer owns the moves and the arithmetic, and owns no pricing rule.

Formally, `specifications/06-risk/par-and-key-rate.md` defines a `product` object (`OIS` or `BOND`) that names an existing pricer, a bump (`bump_bp`, `CENTRAL` or `FORWARD`) and a move:
- **par**: bump quotes, rebuild with `rates.ois.bootstrap`, revalue;
- **key rate**: shift zero rates on a given curve, with `TRIANGULAR` weights or one `PILLAR`, and revalue, with no rebuild;
- **Jacobian**: bump quotes, rebuild, read the pillar zero rates.

`risk.pnl.explain` composes these: two curve builds, one par risk run and a threshold that scales with the move (ruling R2-A3). All of it is bump and revalue (ADR-0010), so each language reuses its stage B to D pricers and adds no new maths. Workflow tools (`pnl_explain.py`, and the stability and rich/cheap jobs) stay free of finance: they send cases to `quantforge --batch` and judge the results.

Worked example: `risk_r2-0001` revalues a 2Y receiver 29 times (value, a central pair for the parallel bump, and a central pair for each of 13 quotes), each through the same `rates.ois.pv` the stage B goldens test.

### Stage E: full volatility, exotics, rates vol, correlation and credit (v0.5.0)

**Status: implemented in all four languages.** At the stage E merge, `597abf2` (2026-11-08), the golden set holds 6,817 cases (value-checked and error cases counted together) in 91 suite files (counted from `datasets/golden/`). C++, Java and Rust each reported 6,817 of 6,817 passing in their final stage E commits (`5af077d`, `a9cd195`, `141245d`; *reported*). Python passed 6,817 of 6,817 through the neutral runner on the merged tree, built from `597abf2` (*observed*, local, Windows, 2026-11-08). Outside oracle under plan rule 11.2.5, counting a case only if every output is a QuantLib 1.44 value (rulings E-A17, E-B28): 557 of the 895 stage E cases, 62.2% (spec A 280 of 446 in `oracle/outside_register_e_a.json`, spec B 277 of 449 in `oracle/outside_register_e_b.json`; *outside-checked*). All inputs are synthetic, and no model is Validated (`docs/model-inventory.md`).

Slices E1, E2, E3 and E5 (written by the first spec session): New operation families: `vol.svi.*`, `vol.ssvi.to_svi`, `vol.local.*`, `vol.forward.*`, `vol.smile.dynamics`, `vol.volofvol.*` (E1); `fx.option.*`, `fx.delta.*`, `fx.atm.*`, `fx.smile.*` (E3); `vol.heston.*`, `vol.bates.*`, `vol.merton.*`, `vol.slv.*` (E2); `exotic.*` (E5). No new error code. `E_ARBITRAGE` now also covers surfaces, local vol and forward vol. The specs are `specifications/05-volatility/{arb-free-surfaces,local-and-forward-vol,fx-smile,heston-family}.md` and `specifications/04-pricing/exotics.md`. Rulings are E-A1 to E-A24 in `specifications/stage-e-rulings.md`.

Design points:
- Surfaces are SVI slices joined linearly in total variance (ruling E-A4), so Dupire local vol has closed-form derivatives. The stage C grid surface is not used for local vol (E-A8).
- The two reference schemes, SLV leverage and the American FD, are specified step by step. Their goldens test that the four builds agree, not that the scheme has converged (E-A14, E-A23).
- Outside checks for spec A use QuantLib 1.44 through their own convention map (`oracle/python/qf_oracle/convmap_e_a.py`, report `oracle/OUTSIDE_E_A.md`); spec B has a separate map (`oracle/CONVENTION_MAP_E_B.md`). A case counts only if every output is a QuantLib value (E-A17): 280 of 446 spec A cases, 62.8%, at the merge; with spec B, 557 of 895 stage E cases, 62.2% (*outside-checked*).


Slices E4, E6, E7 and E8 (written by the second spec session):

Plain idea: stage E adds models on top of the stage D curves and pricers, not beside them. A swaption cube is the D7 swaption with a vol that depends on strike and node; a caplet strip is D7's cap priced many times; a CDS option is a forward CDS inside Black's formula. Correlation and variance work is closed form or a fixed convex problem.

Formally, spec B owns 22 operations in four groups, each with its own spec page and suite (`specifications/cli-contract.md`, section "Stage E operations, spec B"):
- **E4** `rates.swaption.price_cube`, `rates.cap.strip`, `rates.bondfut.*`, `infl.cap.*` (`05-volatility/rates-vol-cube.md`, suite `ratesvol_e`);
- **E6** `risk.corr.*` (`06-risk/correlation.md`, suite `corr_e`);
- **E7** `vol.garch.*`, `vol.varswap.*`, `vol.vix.*` (`garch.md`, `variance-swaps.md`, `vix-index.md`; suites `garch_e`, `varswap_e`, `vix_e`);
- **E8** `credit.cdsoption.*`, `credit.copula.joint_default`, `credit.lhp.*` (`04-pricing/credit-options-and-copulas.md`, suite `creditopt_e`).

No new error code and no wire-format change; `E_ARBITRAGE` (stage C) is reused for cap quotes that cannot be stripped. Four operations iterate (`vol.garch.fit`, `rates.cap.strip`, the two implied vols) and one converges (`risk.corr.nearest`); each is judged on what it must achieve (repricing, the objective, or a convergence tolerance), never on an iteration path (rulings E-B10, E-B16, E-B18). Goldens give non-money outputs their own tolerance through `output_classes` (ruling E-B14). On the oracle side, `oracle/python/gen_stage_e_b*.py` write the goldens, and `oracle/python/outside_e_b.py` re-prices them in QuantLib through the separate convention table `oracle/CONVENTION_MAP_E_B.md` (plan rule 11.2.5).

Worked example: `ratesvol_e-0006` touches four layers: the stage B curves (input), the D7 swap schedule and annuity (4.27337), the E4 parameter interpolation (`rho = -0.27995` between nodes), the stage C Hagan formula (vol 25.27%) and the D7 Black swaption price (205,137.03 on 10m). Status: implemented in all four languages; 277 of these 449 cases are outside-checked (ruling E-B28, `specifications/05-volatility/stage-e-targets-b.md`).

### Stage F: curve layer, portfolio risk and book (v0.6.0)

Implemented in all four languages, each passing 12,462 of 12,462 golden cases (value-checked, error and invariance cases counted together) on the merged part 2 tree (2026-11-10, observed). What changes in the structure:
- **Curves (domain 02)** take a pluggable interpolation on `S = D/J`: monotone convex, monotonic log cubic, tension spline and hybrid. A joint solver treats several curves as one system and returns the IFT Jacobian. Curves are passed in dependency order, so `dR/dx` is block lower triangular and the cross-curve zeros are exact (ruling F-25).
- **Risk (domain 06)** gains its first non-bump method. `risk.book.ois_sensitivity` defines exact derivatives; Rust computes them on an AAD tape through the IFT, and the other builds by the chain rule (ruling F-29; ADR-0010 still governs every older risk operation). Portfolio risk adds VaR and ES (four methods), the Kupiec, Christoffersen and traffic-light backtests, and FRTB-SA GIRR delta.
- **Portfolio (domain 07)** gets its first operations: the book lifecycle and end-of-day marks, with a new `book` module in each language (name map, ADR-0011).
- **Inputs:** a Real input may be the string `"NaN"`, `"Infinity"` or `"-Infinity"`, and every operation refuses a non-finite input first (rulings F-1 to F-4).
- Public names across the four languages follow one generated name map, with units in names, enums for closed choices, validated constructors and a thread-safety line per type ([ADR-0011](architecture/decisions/ADR-0011-api-style.md)). What must be bit-exact and what is within tolerance is in [docs/determinism.md](docs/determinism.md).

### Stage G: rates models and xVA (v0.7.0)

Implemented in all four languages; on the integration tree `stage-g-int` (2026-11-11, observed on one Windows machine through the neutral runner) each build passed 14,492 of 14,492 golden cases (value-checked, error and invariance cases counted together). What changes in the structure:
- **Pricing (domain 04)** gains term-structure models. Short-rate models (Vasicek, CIR, Hull-White, G2++) share one curve rule: log-linear discount factors with `(0, 1)` first (ruling G-3). Bermudan swaptions and callable bonds run on one lattice scheme (ruling G-18). The LMM prices caplets and swaptions by Rebonato's formula (`04-pricing/lmm.md`).
- **Risk (domain 06)** gains Monte Carlo Greeks (pathwise, likelihood ratio, smoothed digitals), a model-reserve dispersion report and an AAD ladder on a Bermudan (`mc-greeks.md`, `model-reserve.md`, `aad-core.md`).
- **xVA (new, under domain 06)**: exposure is computed first (`xva-exposure.md`), and the adjustments are pure arithmetic on exposure profiles, discount factors and hazard rates (`xva-framework.md`). That split keeps CVA, DVA and FVA testable without a simulation. Portfolio exposure (`xva.exposure.portfolio_hw`, wave 4c) is exact one-factor integration, and ORE's Monte Carlo is the outside check, kept under `oracle/ore/` and never read by a build.
- **CLI**: the 21 stage G operations are listed in `specifications/cli-contract.md` ("Stage G operations") and the generated name map.

### Stage I: hedging (v0.8.0)

Built in all four languages, with 443 golden cases in 21 suites; each build passed 14,935 of 14,935 golden cases (7,413 value-checked, 5,008 error, 1,257 invariance and 1,257 `any` base cases) on the integration tree (2026-11-11, observed; `program/STAGE_I_HANDOVER.md`). What changes in the structure:
- **Hedging (domain 08)** gets its first operations, all built around one solver. `hedge.qp.solve` (weighted least squares with ridge, equalities and bounds, and optional spread, impact, liquidity and margin terms) is the kernel; the Greek, credit, correlation and cross-asset hedges each build a risk matrix from their own pricing and pass it to that solve, and `hedge.frontier.solve` and `hedge.select.solve` call it repeatedly (`specifications/08-hedging/`). The fixed check order (shapes, then domain, then rank, then feasibility) makes the error code of a bad problem the same in every build (rulings I-3, I-14). The cost terms are solved by a sign-state active-set method in Java and C++ and a sign-state correction loop in Rust, so no build caps the instrument count below the 200 of I-4 (I-48), and the result is exact at a switch point (I-54).
- **Reuse of earlier domains:** credit hedges reuse the `credit.cds.price` legs (domain 04), and cross-asset hedges reprice rather than use Greeks, so the risk is a half-difference of prices on a rebuilt curve (I-15, I-21).
- **Errors:** a new code, `E_INFEASIBLE`, for constraints no point satisfies (`specifications/cli-contract.md`); the contract is 1.11.0, which `conformance/runner/runner.py` requires (I-51). `hedge.select.solve` returns `E_LIMIT` above 100,000 candidate subsets (I-53).
- **Tutorials** for stage I import `quantforge_core` modules, as tutorial 1 does; `quantforge.hedge.*` in the name map is a logical name (I-52).

### Stage J wave 1: research tools (v0.9.0)

Built in all four languages and merged to `main` with wave 2 (PR #40, `a148d0e`, 2026-11-14). After wave 1 each build passed 15,215 of 15,215 golden cases (7,504 value-checked, 5,197 error, 2,514 invariance), 99 of them in the four wave 1 suites; after wave 2 the total is 15,315 (`docs/case-figures.md`, checked by `tools/check_case_total.py`). What changes in the structure:

- **Research (domain 11)** gets its first CLI operations, in a new `research` module per language (`python/quantforge_core/research.py`, `rust/crates/quantforge-core/src/research.rs`, `java25/src/main/java/org/quantforge/research/Research.java`, `cpp26/src/core/research.cpp`) with a thin CLI handler beside it. The module depends on nothing above domain 01: a backtest takes prices and target positions, not a pricer, so studies built on it stay outside the four builds (`specifications/11-research/`).
- **Operations:** `research.backtest.run`, `research.cv.purged_kfold`, `research.cv.cpcv_paths`, `research.regime.viterbi`, `research.stats.psr`, `.dsr`, `.pbo`, `.power`; 284 operations in the generated name map after wave 1 (291 after wave 2).
- **Contract:** 1.13.0 at wave 1, no new error code (J-1); 1.14.0 after wave 2. These operations carry their own page limits in place of the general 100,000-element array limit (J-20).
- **Outside checks:** vectorbt, timeseriescv, scikit-learn, skfolio, hmmlearn and statsmodels check 41 of the 63 value cases (65.1%, J-19a, `oracle/OUTSIDE_SHARES.md`); with wave 2, 99 of the 130 stage J value cases (76.2%).

### Stage J wave 2: portfolio construction and risk-model tests (v0.9.0)

Built in all four languages and merged to `main` (PR #40). 100 new golden cases (67 value-checked, 33 error) in `optim_j`, `estim_j`, `esbt_j` and `baumwelch_j` bring the total to 15,315 (`docs/case-figures.md`); every build passes all 100 (2026-11-14, observed through the neutral runner). What changes in the structure:

- **Portfolio (domain 07)** gets optimisation and estimation operations, beside a second module per language for the wave (`python/quantforge_core/research_w2.py`, `java25/src/main/java/org/quantforge/research/Allocation.java`, CLI handler `OpsResearchW2.java`). Like wave 1, it depends on nothing above domain 01: it takes expected returns, a covariance and weights as numbers, never a pricer or a market-data object, and no operation calls another. The pipeline is drawn in [`docs/diagrams/README.md`](docs/diagrams/README.md#portfolio-pipeline).
- **Operations:** `research.portfolio.mean_variance`, `research.portfolio.risk_parity`, `risk.contrib.euler`, `research.estimate.ledoit_wolf`, `research.estimate.black_litterman`, `risk.backtest.es_z2`, `research.regime.baum_welch`; 291 operations in the generated name map.
- **Shared linear algebra:** the symmetry test (`1e-12 max|S|`) and the positive-definiteness test (a Cholesky factorisation with every pivot positive) are fixed by ruling J-W2-3, so every build refuses the same matrices with `E_DOMAIN`. Mean-variance has a unique optimum, and goldens keep a `1e-6` strict-complementarity margin, so `at_bound` is the same for any correct solver (J-W2-4); the method (active set recommended) is free.
- **Determinism of an iterative fit:** Baum-Welch's iteration and stop rule are fixed (J-W2-11), and each golden's tolerance is chosen so every stop test is decided by at least `1e-11`, so every build stops at the same iteration (J-W2-12).
- **Contract:** 1.14.0, no new error code (J-W2-1); every build reports it and the runner expects it. Page limits replace the general array limit (J-W2-14).
- **Outside checks:** 58 of the 67 value cases (J-W2-16, J-W2-23): mean-variance by DAQP, risk parity by cvxpy with Clarabel, Euler by autograd, Ledoit-Wolf by scikit-learn, Black-Litterman by PyPortfolioOpt, Baum-Welch by hmmlearn; the seven `esbt_j` value cases have no free Z2 library (`oracle/OUTSIDE_J.json`). Before those, the generator's exact KKT certificates, scipy SLSQP agreement and pairs of independent algebraic forms were the internal checks (J-W2-15).

### Stage J wave 3 and the curves lane (v0.9.0)

Built in all four languages on branch `stage-j2` (2026-11-15). Wave 3 adds 88 golden cases (56 value-checked, 32 error; `scen_j`, `interpbt_j`, `drift_j` and four `fuzzfix_j` cases), the curves lane 51 (20 value-checked, 31 error; `termfin_j`, `liqcurve_j`) and the hedge rank-cut fix 4 (`hedgecut_j`, J-I.1) and the hedge sign-state and selection fixes 5 (`hedgesign_j`, `selectcost_j`, J-I.2 and J-I.3), the minimum-variance constant-series fix 3 error cases (`minvarconst_j`, J-I.4) and the E1 completion 48 error cases (`e1_j`: a non-finite input for each of 25 wave 3, curves and stage J operations that had none), for 15,514 in all (`docs/case-figures.md`). On the merged tree (2026-11-15, observed through the neutral runner) every build passes all 15,514. What changes in the structure:

- **Wave 3 module per language** (`python/quantforge_core/research_w3.py` and `drift.py`, `rust/crates/quantforge-core/src/research_w3.rs`, `java25/src/main/java/org/quantforge/research/StressDrift.java` with CLI handler `OpsResearchW3.java`, `cpp26/src/core/research_w3.cpp`). Scenario stress sits in risk (domain 06) but takes yields and DV01s as numbers, never a curve object; the interpolation backtests reuse `core.interp.evaluate`; the drift detectors depend on nothing above domain 01.
- **Curves lane module per language** (`term_curves.py`, `term_curves.rs`, `OpsTermCurves.java`, `term_curves.cpp`): the term financing structure extends ruling D22 without changing the stage D operations (J-C-2); the liquidity curve is in execution (domain 10) for stage H reuse (J-C-8).
- **Data:** the shock library `datasets/scenarios/us_treasury_shocks.json` is built by `datasets/scenarios/build_shock_library.py` from Treasury daily par-yield files and checked against H.15 (J-W3-6, J-W3-7); it is the first stored market data an operation's worked example reads.
- **Operations:** `risk.scenario.historical_shock`, `risk.scenario.replay`, `research.backtest.interp_loo`, `research.backtest.surface_holdout`, `research.drift.cusum`, `.page_hinkley`, `.psi`, `.ks` (wave 3); `repo.term.curve`, `eq.forward.term_financed`, `liq.curve.cost` (curves lane); 302 operations in the generated name map.
- **Contract:** 1.15.0 for both lanes (J-W3-1, J-C-1), no new error code; wave 3 page limits J-W3-14; `risk.backtest.traffic_light` `observations` above 1,000,000 is `E_LIMIT` (J-W3-17).
- **Outside checks:** 31 of the 56 wave 3 value cases (numpy `interp` on replays, scipy interpolants, scipy `ks_2samp` exact; `oracle/OUTSIDE_J.json`), none of the curves lane's (J-C-9); stage J as a whole 130 of 212 (61.3%).

### Stage H: microstructure and execution (v0.10.0, unreleased)

Built in all four languages, except the `paper.*` operations, which are Python only (Java, C++ and Rust ports pending in this PR). The specs are confirmed (spec version 0.1.0, 2026-11-18; rulings HR-1 to HR-41 in `specifications/stage-h-rulings-w1.md` and `stage-h-rulings-w1b.md`, later rulings in the other `stage-h-rulings-*.md` files); the generated name map has 338 operations, 235 stage H golden cases in `datasets/golden/stage_h/` (119 value-checked). What the specs fix about the structure:

- **Domains 09 and 10 get their first slices.** Formula operations (`exec.schedule.*`, `exec.ac.*`, `exec.tca.shortfall`, `exec.impact.*`, `micro.mm.as_quotes`) are pure functions like the rest of the library and sit beside the stage J liquidity curve, which was put in domain 10 for this reuse (J-C-8).
- **Simulated venues.** The lit engine (`exec.sim.lit.run`), dark pool (`exec.sim.dark.run`) and router (`exec.sor.allocate`) are deterministic simulators: integer ticks and lots, a logical event sequence, seeded randomness from `core.rng`, and byte-identical replays in every language. They consume library operations but are not models of prices, so they are kept out of the numerical core in their own module per language, in line with ADR-0006's modular boundaries. Every output carries a "simulated" label fixed in its spec. Whether this boundary needs its own decision record ("simulators are not the library") is open for the stage H integration. See [Simulators](docs/simulators/README.md).
- **Recorded data.** `micro.book.rebuild` reads the recorded Kraken L2 files as decimal strings (HR-12); the recorder stays in `tools/recorder/`, with no financial logic, and its data never enters git ([Recorded feeds](docs/data/recorded-feeds.md)).
- **Latency (H-9).** The in-process order-book benchmark measures the rebuild and engine paths in each language against targets fixed before any run (`specifications/09-microstructure/low-latency-targets.md`); every table carries "in-process, simulated feed; no network or venue latency". It follows ADR-0011's in-process API style.
- **Scope added 2026-11-18 (owner):** H-19, outside checks for the stage D value cases and a QuantLib Schedule comparison; H-20, curves against published central-bank curves as consistency checks; H-21, paper trading with simulated fills, positions, cash, daily P&L explain, risk limits, pre-trade checks and a hashed append-only ledger, on the stage H simulators. Never live orders.
- **Simulator layer (wave 2).** The three venues share one shape: decimal strings in, integer ticks and lots inside, a logical event sequence, seeded draws from `core.rng`, and a fixed label on every output. The router calls the venue simulators' cost model, not the venues; paper trading is the only caller that drives all three in sequence. See the [simulator flow](docs/diagrams/README.md#simulator-flow).
- **Paper trading is a Python application above the library.** `python/quantforge_core/paper.py` (book, explain, pre-trade, ledger) and `paper_fills.py` (fills) sit above the library: they call the operations that exist in all four languages (`exec.sim.lit.run`, `exec.sim.dark.run`, `exec.sor.allocate`, `exec.tca.shortfall`) through one dispatch and keep the stateful parts (positions, cash, the ledger file) to themselves. That keeps the four-language contract stateless and lets acceptance test A7 replay every venue golden through the paper path. Round 3 also exposes the stateless steps as CLI operations (`paper.book.apply_fill`, `.end_of_day`, `paper.ledger.append`, `.verify`, `paper.pnl.explain`, `paper.pretrade.check`, `paper.session.run`; goldens `pt_h` 28 and `e1_hpt` 5), in Python (`cli/ops_paper.py`); Java, C++ and Rust ports pending in this PR. No module under `paper*` imports a network library (test A5). See the [ledger flow](docs/diagrams/README.md#paper-trading-ledger-flow).
- **Round 3 operations.** Microstructure estimators (`micro.est.*`, H-4b), venue analytics (`exec.venue.analytics`, H-16), adaptive algorithms (`exec.algo.*`, H-14) and pre-trade and attribution TCA (H-17) are pure functions like the wave 1 formulas. The low-latency book (H-9) is a second implementation of `micro.book.rebuild` in C++ and Rust, held to the same answers, with its own benchmark binaries and a CI regression workflow.
