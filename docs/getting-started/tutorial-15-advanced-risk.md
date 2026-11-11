# Tutorial 15: advanced risk

The plain idea: tutorial 1 took one sensitivity by bumping and repricing. Real books need more. A Bermudan swaption needs its price and its slope against every curve point and model parameter (a *ladder*); bumping each input costs one repricing per input, while reverse-mode automatic differentiation (*AAD*) gets the whole ladder for a small fixed multiple of one pricing. A Monte Carlo price needs Greeks that are not swamped by simulation noise. An exotic needs a reserve for the chance that the booked model is wrong. And a regulated book needs capital and margin numbers computed to a fixed public recipe: FRTB vega and curvature charges from the Basel Committee, and initial margin in the style of ISDA SIMM.

This tutorial runs one example of each: `rates.shortrate.bermudan_ladder`, `risk.mc.greeks`, `risk.model_reserve.dispersion`, `risk.frtb.vega`, `risk.frtb.curvature` and `xva.simm.ir_delta`. All data is synthetic; the inputs are those of golden cases `aadladder_g-0001`, `mcgreeks_g-0001` and `-0002`, `reserve_g-0001`, `frtb_f2c-0001`, `frtb_f2c-0012` and `simm_g-0001`. Budget 15 minutes.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [tutorial 1](tutorial-1-swap.md).
- Some familiarity with Black-Scholes Greeks and with what a swaption is. [LEARN: swaptions, Bermudans and the LMM](../../LEARN.md#swaptions-bermudans-and-the-lmm) covers the Bermudan.

## Step 1: Python

```bash
uv sync --locked --project python
```

Save the next block as `advanced_risk.py`:

<!-- tutorial:run python -->
```python
from quantforge_core import aad_ladder, frtb, mc_greeks, xva

# 1. AAD ladder: a 1y-into-5y Bermudan payer swaption on 1,000,000, Hull-White a = 5%, sigma = 1%.
times = [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
         10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782]
dfs = [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]
lad = aad_ladder.bermudan_ladder(times, dfs, 0.05, 0.01, False, 1.0, [2.0, 3.0, 4.0, 5.0, 6.0],
                                 0.039462, "PAYER", 1_000_000.0, [1.0, 2.0, 3.0, 4.0, 5.0], 101, 50, 6.0)
print(f"bermudan price {lad['price']:.4f}")
print("dV/dP " + " ".join(f"{g:.1f}" for g in lad["d_price_d_discount_factors"][:6]))
print(f"dV/da {lad['d_price_d_mean_reversion']:.1f}  dV/dsigma {lad['d_price_d_sigma']:.1f}")

# 2. Monte Carlo Greeks of a 1Y at-the-money call, 10,000 paths, the same seed for both methods.
for method in ("PATHWISE", "LIKELIHOOD_RATIO"):
    g = mc_greeks.greeks(100.0, 100.0, 1.0, 0.03, 0.01, 0.2, "CALL", method, 10_000, 20261109, None, None)
    print(f"{method:<16} delta {g['delta']:.6f} +- {g['delta_se']:.6f}  vega {g['vega']:.4f} +- {g['vega_se']:.4f}")

# 3. Model reserve: one down-and-out call priced by three models that fit the same vanillas.
r = xva.dispersion({"HESTON": 4.1832, "LOCAL_VOL": 4.6021, "SLV": 4.3907}, "SLV")
print(f"reserve {r['reserve']:.4f} ({r['relative_reserve']:.4%}) worst {r['worst_model']} range {r['range']:.4f}")

# 4. FRTB standardised approach: GIRR vega and curvature, three correlation scenarios each.
v = frtb.vega("GIRR", [("EUR", None, 1.0, 5.0, 1_000_000.0), ("EUR", None, 5.0, 10.0, -600_000.0),
                       ("USD", None, 1.0, 5.0, 800_000.0)])
print(f"FRTB vega      {v['capital']:.2f} ({v['binding_scenario']}); medium K_EUR {v['scenarios']['medium']['buckets'][0]['k']:.2f}")
c = frtb.curvature("GIRR", [("EUR", None, 500_000.0, 300_000.0), ("USD", None, -200_000.0, 400_000.0)], False)
picks = ", ".join(f"{b['bucket']} {b['selected']}" for b in c["scenarios"]["high"]["buckets"])
print(f"FRTB curvature {c['capital']:.2f} ({c['binding_scenario']}); {picks}")

# 5. SIMM-style IR delta margin: six tenor buckets, given risk weights and correlations.
rho = [[1.0, 0.659754, 0.535887, 0.407091, 0.33066, 0.237818],
       [0.659754, 1.0, 0.812252, 0.617034, 0.501187, 0.360465],
       [0.535887, 0.812252, 1.0, 0.759658, 0.617034, 0.443785],
       [0.407091, 0.617034, 0.759658, 1.0, 0.812252, 0.584191],
       [0.33066, 0.501187, 0.617034, 0.812252, 1.0, 0.719223],
       [0.237818, 0.360465, 0.443785, 0.584191, 0.719223, 1.0]]
m = xva.simm_ir_delta([1000.0, -500.0, 2500.0, 4000.0, -1200.0, 300.0],
                      [109.0, 105.0, 90.0, 71.0, 66.0, 66.0], rho, 1e9)
print(f"SIMM IR delta margin {m['margin']:.2f} (CR {m['concentration_factor']:.1f})")
```

```bash
uv run --project python python advanced_risk.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
bermudan price 22697.8097
dV/dP 127.3 191964.2 173815.8 147510.2 -233481.5 -343472.6
dV/da -52528.1  dV/dsigma 2269594.6
PATHWISE         delta 0.567128 +- 0.005831  vega 38.4717 +- 0.7349
LIKELIHOOD_RATIO delta 0.568857 +- 0.013621  vega 38.1801 +- 2.4982
reserve 0.2114 (4.8147%) worst LOCAL_VOL range 0.4189
FRTB vega      1095445.12 (high); medium K_EUR 467466.25
FRTB curvature 731436.94 (high); EUR UP, USD DOWN
SIMM IR delta margin 452205.34 (CR 1.0)
```

### Reading the numbers

**AAD ladder.** The trade is a payer Bermudan on 1,000,000, exercisable yearly from year 1 to year 5 into a swap paying 3.9462% to year 6, under Hull-White with mean reversion `a` = 0.05 and volatility `sigma` = 0.01 (the model of [HW90]).

- **Price** 22,697.81.
- **dV/dsigma** 2,269,594.6 per unit of `sigma`: a 1 bp rise in `sigma` (0.0001) adds about 2,269,594.6 × 0.0001 ≈ 227. Options gain from volatility.
- **dV/da** −52,528.1: raising `a` by 0.01 takes about 525 off. More mean reversion damps rate moves, so the option is worth less.
- **dV/dP**, one number per discount factor. A higher 1- to 3-year discount factor (127.3 at 6 months, then +191,964.2, +173,815.8, +147,510.2) raises the price; a higher 5- or 7-year one (−233,481.5, −343,472.6) lowers it, because it lowers the forward swap rate a payer receives against. The pillars from 10 years on are past the last payment and are exactly 0.
- **Head check: a parallel rise of 1 bp in continuously compounded zero rates.** Each discount factor moves by `−t P × 0.0001`. Summing `dV/dP × (−t P × 0.0001)` with the curve's times and factors: −0.0001 × (0.4986 × 0.98085 × 127.3 + 1 × 0.9619 × 191,964.2 + 2 × 0.9254 × 173,815.8 + 3 × 0.8906 × 147,510.2 − 5.0027 × 0.8242 × 233,481.5 − 7.0055 × 0.762 × 343,472.6) ≈ −0.0001 × (62 + 184,650 + 321,690 + 394,110 − 962,700 − 1,833,590) ≈ +190. A payer gains about 190 when rates rise 1 bp, the sign you expect.

**Monte Carlo Greeks.** A one-year at-the-money call (spot = strike = 100, `r` = 3%, dividend yield 1%, vol 20%), 10,000 paths, the same random draws for both methods. The Black-Scholes values are a check: `d1 = (0.03 − 0.01 + 0.02) / 0.2 = 0.2`, delta `= e^{−0.01} N(0.2) = 0.99005 × 0.57926 = 0.5735`, vega `= 100 e^{−0.01} φ(0.2) = 99.005 × 0.39104 = 38.715`.

- **Pathwise** delta 0.567128 ± 0.005831 (one standard error) is (0.5735 − 0.5671) / 0.0058 ≈ 1.1 standard errors from the closed form; vega 38.4717 ± 0.7349 is 0.33 standard errors away.
- **Likelihood ratio** delta 0.568857 ± 0.013621 is 0.34 standard errors away; vega 38.1801 ± 2.4982 is 0.21 away.
- **Noise.** On a call the likelihood-ratio standard error is 0.013621 / 0.005831 = 2.3 times the pathwise one for delta and 2.4982 / 0.7349 = 3.4 times for vega. Pathwise wins whenever the payoff is continuous; the likelihood ratio earns its place on a digital, where the pathwise derivative is zero almost everywhere.

**Model reserve.** A down-and-out call priced by three models that all fit the same vanilla smile: Heston 4.1832, local vol 4.6021, stochastic-local vol (SLV) 4.3907, booked on SLV.

- **Range** 4.6021 − 4.1832 = 0.4189.
- **Reserve** is the largest distance from the booked price: |4.6021 − 4.3907| = 0.2114, from local vol, which is 0.2114 / 4.3907 = 4.8147% of the booked price.

**FRTB vega.** Three GIRR vega sensitivities (vega times implied vol, in currency): EUR 1y-into-5y +1,000,000, EUR 5y-into-10y −600,000, USD 1y-into-5y +800,000. Risk weight 100%.

- **Medium scenario, EUR bucket.** The correlation between the two EUR factors is `exp(−0.01 × 4 / 1) × exp(−0.01 × 5 / 5) = e^{−0.05} = 0.9512`, so `K_EUR = sqrt(1,000,000² + 600,000² − 2 × 0.9512 × 1,000,000 × 600,000) ≈ 467,467`, the printed 467,466.25 to the rounding of the correlation.
- **Capital** 1,095,445.12 from the high-correlation scenario. There all correlations are scaled by 1.25 and capped at 1: the EUR pair becomes fully correlated, `K_EUR = 1,000,000 − 600,000 = 400,000`, and the cross-currency correlation 50% becomes 62.5%: `sqrt(400,000² + 800,000² + 2 × 0.625 × 400,000 × 800,000) = sqrt(1.2 × 10¹²) = 1,095,445`.

**FRTB curvature.** Curvature risk positions (the loss under a large up and a large down shock, beyond what delta already counts): EUR up 500,000, down 300,000; USD up −200,000, down 400,000.

- **EUR** takes the up shock (500,000 > 300,000); **USD** takes the down shock (a negative up loss counts as 0, and 400,000 > 0).
- **Capital** 731,436.94, high scenario: the GIRR cross-currency correlation 50% is squared to 25%, scaled by 1.25 to 31.25%, and `sqrt(500,000² + 400,000² + 2 × 0.3125 × 500,000 × 400,000) = sqrt(5.35 × 10¹¹) = 731,437`.

**SIMM-style IR delta.** Six tenor sensitivities (currency per bp) with given risk weights and tenor correlations.

- **Concentration.** The net sensitivity is 1,000 − 500 + 2,500 + 4,000 − 1,200 + 300 = 6,100, far below the threshold of 1e9, so the concentration factor CR is 1.0.
- **Margin** 452,205.34. Bounds as a check: the weighted sensitivities are 109,000, −52,500, 225,000, 284,000, −79,200 and 19,800. With all correlations 1 and all signs alike the margin would be their absolute sum, 769,500; with no correlation it would be the root of the sum of squares, about 390,600. Positive correlations among mostly same-signed positions put it in between.

## The formal statement, checked against the specs

**AAD ladder** (`specifications/06-risk/aad-core.md`, rulings G-9, G-35). `V(theta)` is the reference lattice-scheme price of `rates.shortrate.bermudan_swaption` (ruling G-18); the ladder is `dV/dtheta` over the discount factors `P_1..P_m`, `a` and `sigma`, the derivative of the *discrete scheme* (including the tridiagonal solve and the exercise `max` on its active branch), not of the continuous model. Times are year fractions, given directly; the curve is given as pillar times and discount factors. The golden is a Richardson-extrapolated central difference with relative bumps 1e-4 and 5e-5, cross-checked with a second pair; tolerance `1e-10 + 1e-8 |ref|` per unit notional. The idea of AAD for Greeks is from Giles and Glasserman, "Smoking adjoints", *Risk*, January 2006, and Griewank and Walther, *Evaluating Derivatives*, 2nd ed., chapter 3; the spec marks both "not opened".

**Monte Carlo Greeks** (`specifications/06-risk/mc-greeks.md`, rulings G-10, G-15). `S_T = S exp((r − q − v²/2) T + v sqrt(T) z)` with one normal `z` per path from `core.rng` (seed, stream 0), discount `D = e^{−rT}`, and `dS_T/dv = S_T (sqrt(T) z − v T)`. Pathwise call: delta term `D 1{S_T > K} S_T / S`, vega term `D 1{S_T > K} dS_T/dv` [Glasserman 2003, section 7.2]. Likelihood ratio: delta term `D f(S_T) z / (S v sqrt(T))`, vega term `D f(S_T) ((z² − 1)/v − z sqrt(T))` [Glasserman 2003, section 7.3; Broadie and Glasserman 1996]. Outputs are sample means; standard errors use the `n − 1` divisor over `sqrt(n)`. Rates and yield are continuously compounded, `T` in years. The spec notes Glasserman was not opened; the estimators are checked against their closed-form expectations.

**Model reserve** (`specifications/06-risk/model-reserve.md`, ruling G-36). `range = max p_m − min p_m` [Cont 2006], `reserve = max_m |p_m − p_ref|`, `worst_model` the model attaining it (ties: first name in code-point order), `relative_reserve = reserve / |p_ref|` (`null` when `p_ref = 0`). Prudent-valuation rules ask for a model-risk adjustment from a range of plausible models (Commission Delegated Regulation (EU) 2016/101, Article 11); the spec marks both sources "not opened".

**FRTB vega and curvature** (`specifications/06-risk/frtb-sa-vega-curvature.md`, ruling G-51, read against the Basel Framework MAR21). Vega: `WS_k = RW × VR_k` with `RW` 100% here (MAR21.92 Table 13); GIRR correlation within a bucket `min(exp(−a |T_k − T_l| / min(T_k, T_l)) × exp(−a |U_k − U_l| / min(U_k, U_l)), 1)`, `a = 1%`, `T` option maturities and `U` underlying residual maturities in years (MAR21.93); across buckets the delta `gamma` (MAR21.95); aggregation MAR21.4; three correlation scenarios (MAR21.6), capital the largest. Curvature: `CVR^± = −(V(x shocked) − V(x) ∓ RW s)` per MAR21.5(2), supplied by the caller; within a bucket `K^± = sqrt(max(0, Σ max(CVR^±, 0)² + Σ_{k≠l} ρ_kl CVR_k CVR_l ψ))`, `K_b = max(K^+, K^−)`; across buckets `sqrt(max(0, Σ K_b² + Σ_{b≠c} γ_bc S_b S_c ψ(S_b, S_c)))` with `ρ` and `γ` the squared delta correlations (MAR21.100, 21.101) and `ψ = 0` when both arguments are negative.

**SIMM-style IR delta** (`specifications/06-risk/xva-framework.md`, ruling G-43). `CR = max(1, sqrt(|Σ s_k| / T))`, `WS_k = RW_k s_k CR`, `margin = sqrt(max(0, Σ_k Σ_l ρ_kl WS_k WS_l))` with `ρ_kk = 1` [ISDA SIMM methodology]. Risk weights and correlations are **inputs**, not ISDA's calibration; the numbers above are illustrative, not a SIMM version.

## Step 2: the same in Rust, Java and C++

`examples/tutorial_advanced_risk.py` sends the seven cases to whichever CLI you name and prints the same lines. It uses only the Python standard library.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorial_advanced_risk.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorial_advanced_risk.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorial_advanced_risk.py cpp26/build/quantforge
```

Each prints the lines shown in step 1, digit for digit. The Monte Carlo lines agree because all four builds draw the same `core.rng` stream; the ladder agrees because each build's AAD matches the same bump reference within the `aad_sensitivity` tolerance (`conformance/tolerances`), far finer than the one decimal printed.

## For practitioners

- **AAD on the scheme, not the model.** The ladder differentiates the discrete lattice, including where the exercise boundary falls on the grid. Near an exercise node a bump can flip a decision; the spec drops such golden cases rather than judging them. Desk ladders usually come against par quotes, not discount factors; a Jacobian from discount factors to quotes (as `risk.curve.jacobian` gives for OIS curves) converts one into the other.
- **Per unit of sigma and a.** `dV/dsigma` is per unit of absolute Hull-White volatility, not per vega point of a Black or normal swaption vol. Multiply by 0.0001 for a 1 bp move.
- **No outside oracle for the MC Greeks.** No outside library reproduces the `core.rng` stream, so the goldens come from a float64 replica and the Black-Scholes closed form is the independent check, as above.
- **The reserve is a statistic, not a policy.** Desks set reserves by product-specific policy (often a share of the range, or a calibrated adjustment). The registered report that applies this statistic to Heston, local vol and SLV across exotics has not been run.
- **FRTB inputs.** Vega here is the MAR21.25 sensitivity (vega times implied vol), and curvature takes the bank's CVRs as given; computing those shocked revaluations is the caller's job. There is no FX scalar unless `fx_scalar` is set (FX only).
- **SIMM-style, not SIMM.** One currency, IR delta only, with weights and correlations you supply. ISDA SIMM adds inflation and cross-currency basis, vega and curvature margins, cross-bucket and cross-class aggregation, and a versioned calibration licensed from ISDA.

## Common mistakes

- **A seed as a JSON number.** `seed` is a decimal u64 *string* in the CLI (`"20261109"`), else `E_SCHEMA`; the Python library takes an integer.
- **Comparing MC Greeks without standard errors.** A pathwise and a likelihood-ratio delta that differ by 0.0017 are not in conflict when their standard errors are 0.006 and 0.014.
- **Pathwise on a digital without smoothing.** `PATHWISE` with `DIGITAL_CALL` needs `smoothing_width`, else `E_INPUT` (`mcgreeks_g-0014`).
- **Passing `underlying_maturity` outside GIRR**, or leaving it out for GIRR (`frtb_f2c-0008`).
- **Reading the medium scenario as the capital.** FRTB capital is the largest of the three scenarios; here it was the high one for both charges.

## What you just did

You took a full AAD ladder of a Bermudan, compared two Monte Carlo Greek estimators against Black-Scholes, sized a model reserve from three models' prices, computed FRTB vega and curvature capital under the three correlation scenarios, and computed a SIMM-style IR delta margin. Four implementations agree on every line.

## Try next

- Change `"CALL"` to `"DIGITAL_CALL"` and use `"LIKELIHOOD_RATIO"`; for `"PATHWISE"` add a `smoothing_width` (the spec's acceptance uses 1.0). Compare the standard errors.
- Raise `paths` to 40,000: every standard error should roughly halve (the spec measured slopes near −0.5).
- Set `fixed_rate` to 0.044462 (`aadladder_g-0002`): an out-of-the-money payer, with a smaller price and smaller `dV/dsigma`.
- Make the SIMM sensitivities all 1,000,000 (`simm_g-0003`): the concentration factor becomes `sqrt(6)`.
- Read [LEARN: FRTB standardised capital for rates](../../LEARN.md#frtb-standardised-capital-for-rates) and [LEARN: exposure and xVA](../../LEARN.md#exposure-and-xva).

## References and further reading

- Specs: `specifications/06-risk/aad-core.md`, `mc-greeks.md`, `model-reserve.md`, `frtb-sa-vega-curvature.md`, `xva-framework.md`; rulings in `specifications/stage-g-rulings.md`.
- [HW90] J. Hull, A. White, "Pricing interest-rate-derivative securities", *Review of Financial Studies* 3(4), 1990, [doi:10.1093/rfs/3.4.573](https://doi.org/10.1093/rfs/3.4.573) (paywalled; the DOI returns 403 to scripts, resolved through Crossref). Cited by `short-rate-models.md`, marked not opened.
- M. Giles, P. Glasserman, "Smoking adjoints: fast Monte Carlo Greeks", *Risk*, January 2006 (no stable link verified; not opened). A. Griewank, A. Walther, *Evaluating Derivatives*, 2nd ed., SIAM, 2008, [doi:10.1137/1.9780898717761](https://doi.org/10.1137/1.9780898717761) (paywalled; 403 to scripts, resolved through Crossref).
- P. Glasserman, *Monte Carlo Methods in Financial Engineering*, Springer, 2003, sections 7.2 and 7.3, [doi:10.1007/978-0-387-21617-1](https://doi.org/10.1007/978-0-387-21617-1) (paywalled). M. Broadie, P. Glasserman, "Estimating security price derivatives using simulation", *Management Science* 42(2), 1996, [doi:10.1287/mnsc.42.2.269](https://doi.org/10.1287/mnsc.42.2.269) (paywalled; 403 to scripts, resolved through Crossref). Both marked not opened by the spec.
- R. Cont, "Model uncertainty and its impact on the pricing of derivative instruments", *Mathematical Finance* 16(3), 2006, [doi:10.1111/j.1467-9965.2006.00281.x](https://doi.org/10.1111/j.1467-9965.2006.00281.x) (paywalled; 403 to scripts, resolved through Crossref). [Commission Delegated Regulation (EU) 2016/101](https://eur-lex.europa.eu/eli/reg_del/2016/101/oj), Article 11 (free). Both marked not opened by the spec.
- Basel Committee on Banking Supervision, *The Basel Framework*, [MAR21](https://www.bis.org/basel_framework/chapter/MAR/21.htm) (free): MAR21.4 to 21.6, 21.92 to 21.95, 21.98 to 21.101. The spec was read against the version in force from 2023-01-01.
- ISDA, [ISDA SIMM](https://www.isda.org/category/margin/isda-simm/) methodology page (free overview; the calibrated parameters are licensed). The spec cites the methodology without opening a version.
- [COOKBOOK: stage G recipes](../../COOKBOOK.md#stage-g-recipes) and [stage F recipes](../../COOKBOOK.md#stage-f-recipes).
- [GLOSSARY: stage G terms](../../GLOSSARY.md#stage-g-terms) (Bermudan swaption, pathwise and likelihood-ratio Greeks, SIMM), [stage F terms](../../GLOSSARY.md#stage-f-terms) (FRTB-SA) and [stage C terms](../../GLOSSARY.md#stage-c-equity-vol-slice) (Greeks).

Links checked 2026-11-11.
