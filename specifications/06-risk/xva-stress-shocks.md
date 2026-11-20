# xVA under the stage J historical shock library

Spec version 0.1.0. Status: **PROPOSED** (stage K item K-8b; xVA spec lane 2026-11-19; nothing implemented, no golden file written). Rulings `stage-k-rulings-xva.md` KR-172 to KR-176; stage J J-W3-4, J-W3-6; stage G G-16, G-42. Gate: `program/STAGE_K_XVA_GATE.md`.

Label: "historical Treasury par-yield shifts applied as zero-rate shifts" (KR-176).

**Plain idea.** Stage J built a library of four historical curve moves (the 2008 crisis, the 2013 taper tantrum, the 2020 pandemic rally, the 2022 hikes) and a way to lay any of them on today's curve. CVA depends on the curve twice: through the exposures (a payer swap is worth more when rates rise) and through discounting. This page reruns the stage G exposure and CVA on each shocked curve and reports the change, so a desk can read "CVA if 2022 happened again". The arithmetic is the stage G engine on a different curve; what is new is the definition of the shocked curve and the comparison.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| J-W3-4, J-W3-6 | `06-risk/scenario-stress.md`, `stage-j-rulings-w3.md`; `datasets/scenarios/us_treasury_shocks.json` | read (repo) | the shocks and the interpolation rule |
| G-42 | `xva-exposure-portfolio.md` | read (repo) | the exposure and CVA engine |
| [ORE-E] | ORE examples "XVA Stress Testing" (classic and AMC, zero and par domains; no printed numbers) | read 2026-11-19 | why the ORE route does not use `xvaStress` |
| ORE stress file format | ORE User Guide `sec:stress` | **not read** (not located) | not used |

## Formal statement

### `xva.stress.shocked` (KR-172)

Inputs: `xva.exposure.portfolio_hw` inputs (curve given as continuously compounded zero rates at pillar tenors), `scenario` (a library name, or `{tenors, shift_bp}` given directly), optional `scale` (default 1).

Steps: `applied_bp = risk.scenario.replay(base_tenors = curve pillars, shock_tenors, shift_bp, scale).applied_bp` (J-W3-4: linear in tenor between shock tenors, flat outside); shocked zero rate `z_j' = z_j + applied_bp_j / 10,000`; shocked discount factors `exp(-z_j' T_j)` at the pillars, the curve's own interpolation between them; then `xva.exposure.portfolio_hw` on the shocked curve with the same model parameters, exposure times and credit.

Outputs: `applied_bp`, `shocked_zero_rates`, `shocked_discount_factors` (pillars), `base` and `shocked` blocks (each `discounted_ee`, `discounted_ene`, `epe`, `cva`), `delta_cva = shocked.cva - base.cva`, `label`.

## Case inputs (kept for the blind packet)

| Case | Inputs |
|---|---|
| shk_k-0001 | curve pillars `(1, 2, 5, 15, 20)` all at 3%; scenario `hikes_2022`; curve outputs only |
| shk_k-0002 | same curve; scenario `covid_2020`; curve outputs only |
| shk_k-0003 .. 0006 | ORE cases: one G-42b netting set (portfolio `P5` of run `runb2` (`a = 0.03`, `sigma = 0.01`), its curve converted to zero rates `z_j = -ln P_j / T_j` at its own pillars, its credit), one per scenario `gfc_2008`, `taper_2013`, `covid_2020`, `hikes_2022` |

<!-- strip:begin -->
## Worked examples

**shk_k-0001.** Library shifts for `hikes_2022` at 1, 2, 5, 10, 20 years: 419, 376, 308, 269, 260 bp; 15 years lies between 10 and 20: `269 + 0.5 x (260 - 269) = 264.5`. Shocked zero rates `(0.0719, 0.0676, 0.0608, 0.05645, 0.056)`, discount factors `exp(-z T)`: `(0.9306239535535964, 0.8735411859788502, 0.7378608664505911, 0.42880629021004973, 0.3262797946230395)`. A receiver book loses value and a payer book gains; the CVA of a payer book rises with its exposure.

**shk_k-0002.** `covid_2020` at 15 years: `-102 + 0.5 x (-99 + 102) = -100.5`. Zero rates `(0.0184, 0.0196, 0.0205, 0.01995, 0.0201)`, discount factors `(0.9817682465077646, 0.9615583782382694, 0.9025781497529256, 0.7413740427544523, 0.6689807456903467)`.

## Golden cases (designed 2026-11-19; not yet frozen)

| Case | Expected | Outside check |
|---|---|---|
| shk_k-0001 | as above (binary64 rounding of the library shifts kept: 419.00000000000006 bp at 1 year gives 0.0719 after the addition) | B |
| shk_k-0002 | as above | B |
| shk_k-0003 .. 0006 | base and shocked exact one-factor EE, CVA (G-42 quadrature) | O |
<!-- strip:end -->

## Errors (order KR-175)

`E_SCHEMA`: missing field, wrong type. Structural `E_INPUT`: unknown scenario name; `shift_bp` and `tenors` of different lengths; the curve not given as zero rates at pillars. `E_DOMAIN`: as `xva.exposure.portfolio_hw` and `risk.scenario.replay`; a shocked zero rate making a discount factor non-finite. Error goldens: shk_ke-0001 scenario `"dotcom_2001"` (`E_INPUT`); shk_ke-0002 `scale` NaN (`E_DOMAIN`); shk_ke-0003 `scenario 7` and `scale "x"` at once (`E_SCHEMA`).

<!-- strip:begin -->
## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 Curve outputs to 1e-14 relative; EE and CVA as G-42 (1e-10 relative).
- A2 Properties: `scale 0` returns the base exactly; the `base` block equals `xva.exposure.portfolio_hw` on the unshocked inputs exactly; a parallel shift of `+d` bp moves every shocked zero rate by `d` bp.
- A3 Gate: at least 4 of 6 value cases outside-checked (60% of 6 is 3.6).
<!-- strip:end -->

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Shocked curve (replay interpolation) | exact to rounding | candidate oracle `shk_k` (50 digits, 2026-11-20) | tenor beyond the last shock tenor: flat | J-W3-4 |
| Exposure by one-factor quadrature (O cases) | quadrature to 1e-11 relative as G-42 | not run (needs WSL) | the largest shock (`hikes_2022`) | G-42, KR-172 |

## Accuracy envelope

The base and shocked values are exact one-factor integrals. The shock definition (par-yield moves applied as zero-rate moves, J-W3-4 interpolation, model parameters unchanged) is a scenario choice and is labelled; it has no accuracy to measure. The largest shock (`hikes_2022`, up to 424 bp) is the edge for the exposure engine: a payer's exposure moves far into the money, where the PFE flat-top issue of G-42 was seen; the O cases include it.

## Outside-check design (registered here before any run)

- **B (2):** shk_k-0001, 0002 (curve arithmetic from the library and J-W3-4).
- **O (4), stage G route, not `xvaStress`:** for each scenario we write the **shocked curve** as the ORE market (the same generator `oracle/ore/build_case.py` writes for G-42b, fed with the shocked discount factors), so ORE's own stress-file conventions, which were not read, cannot enter. Netting set `P5` of `runb2` (`a = 0.03`, `sigma = 0.01`), seeds 20261361 to 20261364, 5,000 samples. Count as G-42b: means (EE, ENE per date, per-sample EPE and CVA) within `max(3, z_Bonf) SE`; PFE not compared (not an output here). A case counts when its shocked block passes; the base block is G-42b's own case and is not counted again.
- **None:** 0.

## Limits

- Only the four library scenarios and caller-given shifts; no spread or volatility shocks (the library has none).
- Model parameters are not re-calibrated under the shock.
- The shocked curve is used for exposure and discounting alike; no basis between them.
