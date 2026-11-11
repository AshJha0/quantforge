# Calibration surrogate for Heston and SABR (A5, challenger only)

Spec version 1.0.0. Status: Specified (stage G, A5). Rulings: `stage-g-rulings.md` G-11 (parameters, from plan 12.10), G-37 (test-set construction and harness). No goldens and no four-language conformance by ruling G-11: Python research module only, inventory tier "challenger". Acceptance harness `oracle/python/a5_acceptance.py`.

**Plain idea.** Calibrating Heston or SABR to a volatility surface calls the pricer thousands of times. A surrogate is a cheap function (a Chebyshev expansion or a small neural network) trained to return the implied volatility the full pricer would give, so calibration runs much faster [Horvath, Muguruza, Tomas, "Deep learning volatility", *Quantitative Finance* 21(1), 2021; Gass, Glau, Mahlstedt, Mair, "Chebyshev interpolation for parametric option pricing", *Finance and Stochastics* 22, 2018 (not opened)]. The risk is that it is wrong where nobody looked, usually in the wings and at short expiries. So it is accepted only against a fixed, dense test set that over-samples those regions, it must refuse inputs outside its training box, and it never replaces the full pricer: it is a challenger.

## Formal statement

Domain (G-11, plan 12.10). Heston: `v0` in [0.005, 0.25], `kappa` in [0.2, 8], `theta` in [0.005, 0.25], `xi` in [0.05, 1.5], `rho` in [-0.95, 0.2], `ln(K/F)` in [-0.5, 0.4], `T` in [0.02, 5]. SABR: `alpha` in [0.01, 1], `beta` in {0, 0.5, 1}, `rho` in [-0.9, 0.9], `nu` in [0.05, 2], `ln(K/F)` in [-0.5, 0.5], `T` in [0.02, 10].

Interface: `heston_iv(p)` and `sabr_iv(p)` return a Black implied volatility for a parameter vector in the order above (SABR `beta` passed as an index coordinate in [0, 3): 0 for `beta = 0`, 1 for 0.5, 2 for 1). Outside the box, or with NaN or infinity, they raise the domain error (`E_DOMAIN` in the platform).

Full pricer (the reference). Heston: Lewis's single integral with the characteristic function of `05-volatility/heston-family.md`, forward 1, undiscounted, the out-of-the-money option, quadrature to 1e-13 relative; then Black implied volatility. Checked against QuantLib 1.44 `AnalyticHestonEngine` on 200 test points at whole-day maturities: largest price gap 1.6e-14. SABR: Hagan's lognormal expansion (`ql.sabrVolatility`), forward 0.03 for `beta < 1` and 1 for `beta = 1` (G-37).

Test set (G-37). `core.sobol` (`01-core/sobol.md`; index 0 never served), first 1,023 points skipped. Main set: the next 100,000 points mapped affinely onto the box. Extra set: the next 10,000 points; even rows put `ln(K/F)` in the wing `|ln K/F| > 0.3` (length-proportional over the two wing pieces), odd rows put `T` in [0.02, 0.1]. Points whose reference out-of-the-money price is below `1e-12` (forward-relative) are excluded, because their implied volatility is not identifiable in binary64; if more than 1% of the 110,000 points are excluded, the run is invalid (not a pass).

Pass (all required): max `|IV_surrogate - IV_ref|` <= 1e-4 (1 bp) over the judged points; 99.9th percentile <= 5e-5; for Heston, the domain error on each of the 14 faces (a point 1e-9 relative outside each bound, others at the box centre) plus NaN and infinity. Speed-up is measured and reported (G2 harness), not gated.

Worked example of the harness itself (`oracle/A5_HARNESS_SELFTEST.json`, 400 points per model): the exact pricer passes (error 0, 16 of 16 domain checks); the pricer shifted by 2 bp fails (max error 2.0e-4); the exact pricer without a domain guard fails (0 of 16 domain checks). So the test can fail and is not vacuous.

## Status

Harness and parameters fixed (registered 2026-11-11, before any surrogate exists). No surrogate has been trained in this session; the research lane trains one and runs `a5_acceptance.py --module <file>`.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Lewis integral (reference) | quadrature to 1e-13 relative | 200 points against QuantLib: gap 1.6e-14 | `xi -> 0`: Black-Scholes at `sqrt` of the integrated variance | QuantLib `AnalyticHestonEngine` |
| Surrogate | none asserted (a fit) | the 110,000-point test set | outside the box: domain error | the reference |
