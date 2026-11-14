# Expected-shortfall backtest: the Acerbi-Szekely Z2 statistic

Spec version 1.0.0. Status: Implemented (stage J, wave 2) in Python, Rust, Java and C++; every build passes all its cases (15,315 of 15,315, 2026-11-14). CLI contract 1.14.0 (ruling J-W2-1). Rulings: `stage-j-rulings-w2.md` J-W2-10, J-W2-14. Suite: `datasets/golden/stage_j/esbt_j`, written by `oracle/python/gen_stage_j_w2.py`. Plan 14.5 ("expected-shortfall backtest (Acerbi-Szekely)"), 14.6 J-8. Companion of `var-es-and-backtests.md` (VaR exception tests).

**Plain idea.** A VaR backtest counts how often losses beat VaR. That says nothing about how large those losses were, which is what expected shortfall (ES) claims to measure. Z2 compares the size of the exceedances with what the model's ES said they should average: about 0 when the model is right, clearly negative when ES was too small.

Sources:
- [AS14] C. Acerbi, B. Szekely, "Backtesting expected shortfall", *Risk*, December 2014 (test 2: `Z2 = sum_t X_t I_t / (T alpha ES_t) + 1` with returns `X_t` and positive `ES_t`; expected value 0 under the null; critical values about -0.70 at 5 % and -1.8 at 0.01 % for alpha 2.5 % across the distributions they tried) (not opened in this session; the critical values are recalled and are **not** used in any golden or output). Evidence class: paper, recalled.

## `risk.backtest.es_z2`

Inputs `losses` (`L_t`, length `T >= 1`, positive = loss), `var` and `es` (forecast levels made before each period, length `T`, `es > 0`), `alpha` (tail probability, `0 < alpha < 1`, for example 0.025). Errors: lengths differ or `T = 0`: `E_INPUT`; `alpha` outside `(0, 1)` or any `es <= 0`: `E_DOMAIN`.

Definition (J-W2-10): `I_t = 1` when `L_t > VaR_t` (strict); `Z2 = 1 - sum_t L_t I_t / (T alpha ES_t)`. With losses `L = -X` this is the paper's statistic.

Outputs `z2`, `exceptions` (Integer, exact), `expected_exceptions` (`T alpha`). Tolerance `simple_analytic`.

Worked example (`esbt_j-0001`): losses `(1, 3, 0.5, 4)`, VaR 2, ES 2.5, `alpha = 0.25`, `T alpha = 1`. Exceptions at 3 and 4: `Z2 = 1 - (3/2.5 + 4/2.5) = 1 - 2.8 = -1.8`.

## Property tests (each language, own data)

- No exceptions gives `Z2 = 1` exactly; scaling `L`, `VaR` and `ES` by one positive constant leaves `Z2` unchanged; raising every `ES_t` raises `Z2`.

## Limitations

The statistic only. Its null distribution depends on the tail model, so the size study of J-8 (2,000 simulated paths, size within 3 SE of nominal) is a research script (gap G13) that simulates under the model, as the paper does; no p-value or traffic-light zone is an output.
