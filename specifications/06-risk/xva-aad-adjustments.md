# AAD sensitivities of the valuation adjustments

Spec version 0.1.0. Status: **PROPOSED** (stage K item K-8, AAD part; lane `k-v1-aad`, 2026-11-20). Rulings `stage-k-rulings-xva-aad.md` KR-262 to KR-268; stage G G-9, G-41; the K-8b spec lane's KR-161 and KR-162 (branch `k-xva-spec`, not merged; names kept). Suite `stage_k/aadadj_k` (37 cases: 13 value, 24 error), written by `oracle/python/gen_stage_k_aadadj.py`.

**Plain idea.** A desk that hedges CVA needs to know how CVA moves when each input moves: the counterparty's hazard rate, its recovery, every point of the exposure profile, every discount factor, the funding spreads. Bumping each input and recomputing costs one recomputation per input. Reverse-mode automatic differentiation (AAD) runs the calculation once forwards, keeps the intermediate values, and then runs it once backwards, giving every derivative for a small fixed multiple of one calculation [Griewank and Walther, *Evaluating Derivatives*, 2nd ed., SIAM, 2008, chapter 3; not opened in this session, cited as `aad-core.md` cites it: recalled]. The formulas of `xva.adjustments.value` (G-41, `xva-framework.md`) are short sums, so the backward pass is written by hand in each build: no automatic-differentiation library. The acceptance is the plan's: each AAD number equals bump-and-revalue to 1e-8 relative, where the bump is done in 50-digit arithmetic so that the bump's own rounding cannot hide an error (KR-265).

## `xva.sens.aad` (rulings KR-262 to KR-267)

Inputs: `operation` (`"xva.adjustments.value"`, the only value accepted in this version), `inputs` (that operation's request: `times`, `discount_factors`, `ee`, `ene`, `counterparty`, `own`, `funding`, optional `im` with `im_spread`, optional `capital` with `hurdle_rate`), optional `wrt` (array of keys from the list below).

Outputs: `cva`, `dva`, `fca`, `fba`, `fva` (and `mva`, `kva` when given), the same numbers as `xva.adjustments.value`; `gradient`, an object from each of those names to an object of derivatives keyed by input (KR-263):

| Key | Shape | Unit of the derivative |
|---|---|---|
| `counterparty.hazard_rate`, `own.hazard_rate` | number | per 1.0 of hazard (per year); per bp: times 1e-4 |
| `counterparty.hazard_buckets`, `own.hazard_buckets` | one per bucket | per 1.0 of the hazard of bucket `(t_(j-1), t_j]` of a piecewise-flat curve, at the flat input |
| `counterparty.recovery`, `own.recovery` | number | per 1.0 of recovery |
| `discount_factors` | one per bucket | per 1.0 of discount factor (a zero rate: `-t_i D_i` times this) |
| `ee`, `ene` | one per bucket | per one currency unit of the profile point |
| `funding.borrow_spread`, `funding.lend_spread` | number | per 1.0 of spread; per bp: times 1e-4 |
| `im`, `capital` (when given) | one per bucket | per one currency unit |
| `im_spread`, `hurdle_rate` (when given) | number | per 1.0 |

Formal statement. With `S_c(t) = e^(-h_c t)`, `S_b(t) = e^(-h_b t)`, `t_0 = 0`, `dt_i = t_i - t_(i-1)`, `W_i = D_i S_c(t_(i-1)) S_b(t_(i-1)) dt_i`, G-41 reads `CVA = (1 - R_c) sum D_i ee_i (S_c(t_(i-1)) - S_c(t_i)) S_b(t_(i-1))`, `DVA = (1 - R_b) sum D_i (-ene_i) (S_b(t_(i-1)) - S_b(t_i)) S_c(t_(i-1))`, `FCA = s_b sum W_i ee_i`, `FBA = sum s_l' W_i (-ene_i)` with `s_l' = s_l`, or `max(s_l - h_b (1 - R_b), 0)` when `exclude_dva_overlap`, `FVA = FCA - FBA`, `MVA = s_IM sum W_i IM_i`, `KVA = hurdle sum W_i capital_i`. The gradient is the derivative of these formulas as computed (KR-264).

The backward pass (what every build implements, per output): seed the output's adjoint with 1. Each default term `D_i x_i b_i S'(t_(i-1))`, with `b_i = S(t_(i-1)) - S(t_i)` the bucket's default probability of its own name kept as one quantity, sends its adjoint to `D_i`, `x_i`, `b_i` and the start survival `S'(t_(i-1))` of the other name. Each funding term `c_i W_i x_i` sends `W_i x_i` to the spread `c_i`, `c_i W_i` to `x_i` (with the sign of `-ene` for FBA) and `c_i x_i` to `W_i`, which passes it on to `D_i`, `S_c(t_(i-1))` and `S_b(t_(i-1))`. With `bar S_k` the adjoint of a survival used alone and `bar b_i` that of a difference (`t_0 = 0`): `d / d h = -sum_k bar S_k t_k S_k - sum_i bar b_i (t_(i-1) S_(i-1) - t_i S_i)` and, for bucket `j`, `d / d h_j = -dt_j (sum_(k >= j) bar S_k S_k + sum_(i > j) bar b_i b_i - bar b_j S_j)` (indices of `S` by time point, `S_k = S(t_k)`). Keeping `b_i` whole matters: at `h = 0` every `b_i` is exactly 0 and the bucket entries of a zero profile point come out exactly 0; adding `bar b_i` to `S(t_(i-1))` and subtracting it from `S(t_i)` instead leaves a rounding residue (measured: 3.6e-12 on a profile of 35,000 in the random set of A2, above the 1e-12 absolute term). On the linear branch of the overlap floor, the adjoint `g` of `s_l'` in bucket `j` also adds `g` to `s_l`, `g h_b` to `R_b` and `-g (1 - R_b)` to `h_j` (and to `h_b`). FVA's gradient is FCA's minus FBA's. Recovery entries are `-CVA / (1 - R_c)` and `-DVA / (1 - R_b)` in closed form; the backward pass gets them as the sums of the terms.

Kinks (KR-264). `|ene_i| = -ene_i` on the domain, so its derivative is -1 including at `ene_i = 0`. The overlap floor's branch is decided on the binary64 value of `s_l - h_b (1 - R_b)`; at exactly 0 the linear branch is taken, a convention (golden `aadadj_k-0009`). No other kink exists in G-41.

Order of evaluation. The tolerance (below) leaves the order of additions open; the four builds use the order of the backward pass above, bucket by bucket from the first.

<!-- strip:begin -->
## Worked example (`aadadj_k-0001`, the inputs of `xvaadj_g-0001`)

Four half-year buckets to 2 years, `D = (0.985, 0.97, 0.955, 0.94)`, `EE = (120, 150, 130, 80)`, `ENE = (-60, -90, -100, -70)`, counterparty `h_c = 2%`, `R_c = 40%`, own `h_b = 1%`, `R_b = 40%`, both spreads 0.8%. `CVA = 2.7098617740030235` (G-41). Selected entries (oracle, 50 digits, rounded once to binary64):

- `d CVA / d h_c = 133.0258166316599`: a 1 bp rise in the counterparty hazard adds 0.0133 to a CVA of 2.71. By bucket: 34.105, 41.998, 35.570, 21.353, which sum to the flat entry.
- `d CVA / d R_c = -4.51643629000504 = -CVA / (1 - R_c)`.
- `d CVA / d h_b = -1.7909357321811956`: a higher own hazard lowers the first-to-default weight `S_b(t_(i-1))`; the last own bucket has entry 0 because CVA uses own survival only at bucket starts.
- `d CVA / d ee_2 = 0.6 x 0.97 x (e^(-0.01) - e^(-0.02)) x e^(-0.005) = 0.005704780048492856`.
- `d FCA / d s_b = FCA / s_b = 226.952805418071`; `d FVA / d s_l = -150.34122754292395`.

On the kink (`aadadj_k-0009`: `s_l = 0.005`, `h_b = 1%`, `R_b = 50%`, so `s_l - h_b (1 - R_b) = 0` exactly): `FBA = 0`, and the linear branch gives `d FBA / d s_l = 150.34122754292395`, `d FBA / d h_b = -75.17061377146197` (`-(1 - R_b)` times it), `d FBA / d R_b = 1.5034122754292394` (`h_b` times it).
<!-- strip:end -->

## Errors (order KR-267, the KR-230 order)

`E_SCHEMA`: `operation` not `"xva.adjustments.value"`; `inputs` missing, not an object or failing the G-41 schema; `wrt` not an array of strings. `E_LIMIT`: more than 10,000 entries in `times`, `discount_factors`, `ee`, `ene`, `im` or `capital` (KR-266). `E_DOMAIN`: a non-finite Real (F-2). Structural `E_INPUT`: `wrt` empty, repeating a key, naming a key not listed above or naming `im`, `im_spread`, `capital` or `hurdle_rate` when the request does not carry it; then G-41's structural checks. `E_DOMAIN`: G-41's domain checks.

## Tolerances and outside share

Every output, value and gradient, `|a - e| <= 1e-12 + 1e-10 max(|a|, |e|)` (class `aad_sensitivity` with the golden's `tolerance_limit`, KR-265). That is the acceptance A1: it implies `|AAD - bump| <= 1e-8 max(1, |bump|)`. Outside: none (KR-268); the 50-digit bump is our own reference. Plan item K-8 AAD is under the 60% per-item outside-check floor: a recorded miss.

<!-- strip:begin -->
## Acceptance (fixed before any build ran; proposed, frozen on confirmation)

- A1 (plan 14.8 K-8, KR-265): every gradient entry of the 13 value goldens in each of the four builds within the golden tolerance above. Conformance is the test.
- A2 (Python): the same bound against the 50-digit bump computed in the test (`decimal`, 50 digits) on 1,000 seeded random requests (seed 20261120).
- A3 (Python, reported): the KR-161 binary64 Richardson bump against AAD on the value goldens; largest relative gap recorded here once measured.

**Measured (Python, 2026-11-20, local laptop, not the acceptance machine).** A1: 13 of 13 value goldens, every entry within the golden tolerance (`tests/test_xva_aad.py`, and conformance `aadadj_k` 36 of 36). A2: 1,000 requests, 164,169 entries, all within `1e-12 + 1e-10 max(|AAD|, |ref|)`; largest `|AAD - ref| / max(1, |ref|)` 2.4e-12. The first version of the backward pass (survival adjoints only, no `b_i`) missed this bound on 4 entries of 3 requests, all bucket hazards of a zero profile point at `h_c = 0` (true value 0, residue up to 3.6e-12); the backward pass above replaced it before any port. A3: largest relative gap of the binary64 Richardson bump 9.6e-10 (`aadadj_k-0013`, a discount-factor entry of FBA on 1,000,000 notional), below 1e-8 but ten times A1's limit: the bump's own rounding. On the kink case `-0009` the binary64 central bump straddles the kink and returns the mean of the two branches (36.39 against the convention's 73.97 for `d FVA / d h_b`), which KR-161's second-pair test would drop; bumps that leave the domain (`ee_i = 0` bumped down) are not run.
<!-- strip:end -->

## Accuracy envelope (plan 14.10 rule 4)

AAD is exact to rounding for these formulas: each entry is a sum of at most a few thousand products of inputs and exponentials, so its binary64 error is a small multiple of `eps` times the sum of the magnitudes of its terms. The edges are (1) inputs equal to 0 (`ee`, `ene` zero entries, hazard 0: `aadadj_k-0004`, `-0008`, `-0012`), where the derivative is still the formula's; (2) the overlap kink (`-0009` on it, `-0007` and `-0010` on the zero branch, `-0002` 20 bp above it); (3) recovery near 1 (`-0006`, `R_c = 0.999999`), where CVA is small and its recovery derivative is `-CVA / (1 - R_c)`; (4) large profiles (`-0013`, 40 buckets on 1,000,000 notional). A binary64 bump is not a valid judge at 1e-8 on small profile points (KR-265); that is a property of the bump, not of AAD.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Hand-written adjoint of G-41 | exact to rounding | `aadadj_k`, 1,000 random requests (Python) | zero exposure: every adjustment 0, hazard entries 0 (asserted by `-0004`); `h = 0`: CVA = DVA = 0 (`-0008`) | 50-digit Richardson bump (KR-265) and the 50-digit closed-form adjoint, agreeing to 1e-30 |

## Limits

- Only `xva.adjustments.value` is differentiated; the other operations of KR-162 wait for their specs.
- No second derivatives; no derivative with respect to `times`.
- Bucket hazards are derivatives of a piecewise-flat curve at the flat point; the operation does not accept a bucketed curve as input.
