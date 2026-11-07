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

### R1: credibility hardening (in progress)

No new pricing. Batch mode becomes normative in `specifications/cli-contract.md` 1.6.0: one result line per input line, in order, each equal bit for bit to `run` on that line, with no state between lines. The wire `contract_version` stays 1.0.0. Stream fixtures live in `datasets/batch/`, apart from the goldens, because they test the stream rather than an operation.
