# Architecture

QuantForge is one repository holding four isolated implementations and the neutral parts around them. The plain idea: a spec says what must be true, the oracle says what the answer is, and a runner that knows no finance compares each language's answer with it. Detail is in `architecture/`; decisions are in `architecture/decisions/`; diagrams are in `docs/diagrams/`.

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

The specification remains a shared-error risk: four builds and a hand case can share one misreading. That is why outside libraries are used wherever a licence allows, and why a human review closes the project. Until that review, validation is self-assessment.

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

Built the rest of domain 02 (curves) and slices of 03, 04 and 05, in all four languages, from the specs alone: full SOFR and ESTR OIS with curve jumps, dated overnight compounding and IBOR fallbacks, meeting-date step curves, futures convexity, CSA discounting, index basis, joint bootstrap, regularised and robust fits (D1); bonds, repo, bond futures and sovereign fits (D2); cross-currency basis and NDFs (D3); the ISDA CDS model, index CDS and composite curves (D4); dividend, borrow and financing curves, index dividends, corporate actions and TRS (D5); inflation curves and linkers (D6); caps and swaptions (D7); commodity curves and storage (D8); MBS (D9). The curve object gained optional `jumps`. Operation prefixes and spec files are in `specifications/cli-contract.md` 1.5.0. On the oracle side, `oracle/python/gen_stage_d*.py` write the goldens; `specifications/stage-d-handover.md` lists what language sessions may read. Result: at merge `95cbf11` on 2026-11-07, each of the four implementations passed 5,514 of 5,514 golden cases locally, 331 of them in stage D's 20 suites, and fuzzing with seed 17 found nothing (`conformance/README.md`). Limits: all inputs are synthetic, and several suites have hand or analytic sources only (`specifications/stage-d-rulings.md`).

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

**Status: implemented in all four languages.** At the stage E merge, `597abf2` (2026-11-08), the golden set holds 6,817 cases in 91 suite files (counted from `datasets/golden/`). C++, Java and Rust each reported 6,817 of 6,817 passing in their final stage E commits (`5af077d`, `a9cd195`, `141245d`; *reported*). Python passed 6,817 of 6,817 through the neutral runner on the merged tree, built from `597abf2` (*observed*, local, Windows, 2026-11-08). Outside oracle under plan rule 11.2.5, counting a case only if every output is a QuantLib 1.44 value (rulings E-A17, E-B28): 557 of the 895 stage E cases, 62.2% (spec A 280 of 446 in `oracle/outside_register_e_a.json`, spec B 277 of 449 in `oracle/outside_register_e_b.json`; *outside-checked*). All inputs are synthetic, and no model is Validated (`docs/model-inventory.md`).

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

Implemented in all four languages, each passing 12,462 of 12,462 golden cases on the merged part 2 tree (2026-11-10, observed). What changes in the structure:
- **Curves (domain 02)** take a pluggable interpolation on `S = D/J`: monotone convex, monotonic log cubic, tension spline and hybrid. A joint solver treats several curves as one system and returns the IFT Jacobian. Curves are passed in dependency order, so `dR/dx` is block lower triangular and the cross-curve zeros are exact (ruling F-25).
- **Risk (domain 06)** gains its first non-bump method. `risk.book.ois_sensitivity` defines exact derivatives; Rust computes them on an AAD tape through the IFT, and the other builds by the chain rule (ruling F-29; ADR-0010 still governs every older risk operation). Portfolio risk adds VaR and ES (four methods), the Kupiec, Christoffersen and traffic-light backtests, and FRTB-SA GIRR delta.
- **Portfolio (domain 07)** gets its first operations: the book lifecycle and end-of-day marks, with a new `book` module in each language (name map, ADR-0011).
- **Inputs:** a Real input may be the string `"NaN"`, `"Infinity"` or `"-Infinity"`, and every operation refuses a non-finite input first (rulings F-1 to F-4).
- Public names across the four languages follow one generated name map, with units in names, enums for closed choices, validated constructors and a thread-safety line per type ([ADR-0011](architecture/decisions/ADR-0011-api-style.md)). What must be bit-exact and what is within tolerance is in [docs/determinism.md](docs/determinism.md).
