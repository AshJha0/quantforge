# Review request: Financing term structures (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is filed under a labelled "AI review" section of the curve's evidence checklist and checked against the repository before anything is acted on.

Stage: J. Evidence line from the project's curve table: 13 golden cases for `repo.term.curve`, `eq.forward.term_financed`, 13 with an outside library in `verified_by`.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. No library builds this curve. Round 2 (2026-11-18) reads the cumulative funding, spread and fee with QuantLib `LinearInterpolation` and the repo discount factors with `InterestRate(Simple)`; every output is arithmetic on those (`oracle/python/outside_j.py` wave 4, class library-primitive, the class numpy interp earned for scenario replay). All 13 cases agree. It is a check of the interpolation rule and the arithmetic, not an independent model.
9. The time inputs are year fractions, not dates, so QuantLib's date-based dividend engine could not price `eq.forward.term_financed` directly without rounding the times.

## Spec

### `specifications/02-curves/financing-term-structure.md`

# Financing term structure: term repo spread and stock borrow over the funding curve

Spec version 1.0.0. Status: Specified and implemented in all four builds (stage J curves lane, v0.9.0). Rulings: `stage-j-rulings-curves.md` J-C-1 to J-C-5 and J-C-9. Suite `stage_j/termfin_j`. Extends ruling D22 (stage D), which kept borrow and financing as flat rates over the funding curve; D22 still governs `eq.dividend.implied`, `eq.borrow.implied` and `eq.futures.basis` (J-C-2).

**Plain idea.** A desk that holds a bond or a stock pays to finance it, and the rate depends on how long it locks the financing in: overnight repo is cheaper or dearer than three-month term repo. The funding curve (`rates.funding.curve`) says what the desk's own unsecured money costs. The financing curve says how much more, or less, secured money for this collateral costs at each term. For a stock there is a second term structure: the fee a lender of the stock earns, which the holder can earn too. This page builds both from quotes, one pillar per quote, and uses them to price an equity forward. With a single flat spread and a single flat fee it gives exactly the stage D answer.

**Formal statement.** Times are year fractions on one axis, measured from the curve date, `t > 0`. The funding curve is given as continuous zero rates `z_k` at times `t_k`; its cumulative log discount `Z(t) t` is linear between the knots `(0, 0), (t_k, z_k t_k)` (J-C-3). Each term repo quote is a simple money-market rate `R_i` for `[0, T_i]`, so the financing discount factor at a pillar is `P_f(T_i) = 1 / (1 + R_i T_i)`. The cumulative financing spread over funding is

`S(T_i) = ln(1 + R_i T_i) - Z(T_i) T_i`,

linear between the knots `(0, 0), (T_i, S(T_i))`, so the instantaneous forward spread is piecewise flat. Then for every `t` covered,

`P_f(t) = exp(-Z(t) t - S(t))`, zero spread `s(t) = S(t)/t`, term financing rate `(1/P_f(t) - 1)/t`, forward financing rate over `[u, t]` `(P_f(u)/P_f(t) - 1)/(t - u)`.

Each borrow quote is a term-average continuous fee `b_j >= 0` for `[0, T_j]`; the cumulative fee `B(T_j) = b_j T_j` must not fall and is linear between `(0, 0)` and the knots (forward fee piecewise flat, never negative; J-C-4). The equity carry factor is

`C(t) = P_f(t) exp(B(t)) = exp(-Z(t) t - S(t) + B(t))`

and the forward with cash dividends `A_i` at `t_i` is `F(T) = (S_0 - sum_{0 < t_i <= T} A_i C(t_i)) / C(T)` (J-C-5), the form of `eq.forward.outright` with `C` read from these curves.

**Why this form.** The bootstrap is exact: each term repo covers `[0, T_i]`, so each quote fixes one pillar with no solve, and pricing a quote back on the curve returns it to rounding (property test). Linear interpolation of the cumulative quantity is the flat-forward rule of [Hagan-West06] (raw interpolation, their method 2) applied to the spread and the fee, not to the rate; it is local, keeps forwards finite and, for the fee, keeps the forward fee non-negative when the cumulative fee does not fall. Adding the spread to the funding curve, not replacing it, keeps the secured-unsecured basis explicit, as [Piterbarg10] does with collateral rates over the funding rate (`specifications/02-curves/csa-and-basis.md`).

## `repo.term.curve`

Inputs (all arrays of numbers; all keys required):

| Key | Meaning |
|---|---|
| `funding_times`, `funding_zero_rates` | Funding curve knots: positive, strictly increasing times; continuous zero rates |
| `quote_times`, `repo_rates` | Term repo pillars and simple rates. Non-empty; times positive and strictly increasing; the last no later than the last funding time |
| `borrow_times`, `borrow_fees` | Stock borrow pillars and term-average continuous fees. May both be empty (no borrow curve) |
| `query_times` | Where to read the curve. Non-empty, positive, strictly increasing |

Outputs: `pillar_spreads` (`S(T_i)/T_i` per quote), and per query time `spread`, `financing_df`, `financing_rate`, `forward_financing` (over `[q_{j-1}, q_j]` with `q_0 = 0`) and `borrow_fee` (`B(t)/t`; the whole output is `null` when no borrow quotes are given).

Coverage: the curve covers `(0, min(last funding, last quote, last borrow if any)]`. There is no extrapolation (J-C-3).

Checks, in order (after `E_PARSE`, `E_SCHEMA`, `E_LIMIT` and F-2): array pairs of unequal length, empty funding or quotes: `E_INPUT`; a time array not positive and strictly increasing: `E_INPUT`; `1 + R_i T_i <= 0`: `E_DOMAIN`; a negative borrow fee or a falling cumulative fee: `E_DOMAIN`; last quote beyond the last funding time: `E_DOMAIN`; `query_times` empty or not positive and increasing: `E_INPUT`; last query beyond coverage: `E_DOMAIN`. Repo rates and spreads may be negative (specials, J-C-2).

## `eq.forward.term_financed`

Inputs: the six curve arrays above, `spot`, `maturity_years`, `dividend_times`, `dividend_amounts` (both may be empty). Only dividends with `0 < t_i <= T` count. Outputs: `forward`, `carry` (`F - S_0`, the money a long forward position gains over spot), `carry_factor` (`C(T)`), `financing_df` (`P_f(T)`), `pv_dividends` (`sum A_i C(t_i)`).

Checks after the curve checks: dividend arrays of unequal length or times not strictly increasing: `E_INPUT`; `spot <= 0`, `maturity_years` outside `(0, coverage]`, a negative dividend, `F <= 0`: `E_DOMAIN`.

## Worked example (golden `termfin_j-0001`, hand)

Flat funding at 4 % continuous to one year; one one-year term repo at 5 % simple; no borrow; queries 0.5 and 1.

1. `Z(1) = 0.04`. `S(1) = ln 1.05 - 0.04 = 0.048790164169432 - 0.04 = 0.008790164169432`. So `pillar_spreads = [0.008790164169432]`.
2. At `t = 0.5`: `Z(0.5) 0.5 = 0.02`, `S(0.5) = 0.004395082084716` (half way on the line), `spread = 0.008790164169432`, `P_f(0.5) = exp(-0.024395082084716) = 0.9759000729485`, term rate `(1/P_f - 1)/0.5 = 0.0493901531919`.
3. At `t = 1`: `P_f(1) = exp(-0.04 - 0.008790164169432) = 1/1.05`, so `financing_rate = 0.05`: the quote comes back.
4. Forward financing over `[0.5, 1]`: `(P_f(0.5)/P_f(1) - 1)/0.5 = 0.0493901531919`, the same as over `[0, 0.5]` because both the funding curve and the spread are flat here.

Equity (golden `termfin_j-0022`, hand): on the same curve, spot 100, `T = 1`, no dividends: `C(1) = 1/1.05`, so `F = 105` and `carry = 5`. With a dividend of 2 at 0.5 (`termfin_j-0023`): `F = (100 - 2 C(0.5)) / C(1)` with `C(0.5) = exp(-0.02 - S(1)/2)`.

Reduction to D22 (property test in all four builds): flat funding `r`, repo quotes `(e^{(r+s)T} - 1)/T` and one flat borrow fee `b` give `s(t) = s` and `F = S_0 e^{(r + s - b) T}`, the stage D form.

## Acceptance

Class `simple_analytic` for every value output. Evidence (J-C-9): three value cases are hand derivations (`termfin_j-0001` to `-0003`), two more for the forward (`-0022`, `-0023`); the rest are reference-computed by `oracle/python/gen_stage_j_curves.py` in mpmath at 50 digits from this text. There is no outside library check: QuantLib's `PiecewiseZeroSpreadedTermStructure` interpolates zero spreads, not cumulative spreads, and no free published worked example of a term repo spread curve was found, so this curve is self-assessed. Property tests in each language: quote round trip, forward rates chaining to `1/P_f`, D22 reduction, borrow and dividends lowering the forward.

## Limitations

- Money-market simple quotes on a single time axis; day counts and settlement lags are the caller's (convert dates to year fractions first). No GC/special collateral classes: one curve per collateral.
- No extrapolation beyond the last quote, no smoothing, no turn-of-year jumps in the spread.
- Bond carry with a term repo curve is not an operation yet: `repo.forward` still takes one repo rate for the period, which a caller can read from this curve as `financing_rate` at the horizon.

## Sources

- [Hagan-West06] P. Hagan, G. West, "Interpolation methods for curve construction", *Applied Mathematical Finance* 13(2) 2006, 89-129. Raw (flat-forward) interpolation. Evidence class: paper, read for stage F (`interpolation-methods`); applied here to a spread.
- [Piterbarg10] V. Piterbarg, "Funding beyond discounting: collateral agreements and derivatives pricing", *Risk* February 2010. Secured and unsecured rates as separate curves. Evidence class: paper, recalled.
- [Choudhry10] M. Choudhry, *The Repo Handbook*, 2nd ed., Butterworth-Heinemann 2010: term repo as a simple money-market rate; specials below GC. Evidence class: book, recalled; definitions only.
- Ruling D22 (`stage-d-rulings.md`) and `equity-curves.md` for the flat form this page extends.


## Golden cases (13 of 13 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"termfin_j-0001","operation":"repo.term.curve","inputs":{"funding_times":[1.0],"funding_zero_rates":[0.04],"quote_times":[1.0],"repo_rates":[0.05],"borrow_times":[],"borrow_fees":[],"query_times":[0.5,1.0]},"expected":{"status":"ok","outputs":{"pillar_spreads":[0.008790164169432005],"spread":[0.008790164169432005,0.008790164169432005],"financing_df":[0.9759000729485332,0.9523809523809523],"financing_rate":[0.04939015319191968,0.05],"forward_financing":[0.04939015319191968,0.04939015319191968],"borrow_fee":null}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["hand","reference-computed","quantlib-1.44-interp"]}
{"case_id":"termfin_j-0002","operation":"repo.term.curve","inputs":{"funding_times":[1.0],"funding_zero_rates":[0.04],"quote_times":[1.0],"repo_rates":[0.040810774192388224],"borrow_times":[],"borrow_fees":[],"query_times":[0.25,0.5,1.0]},"expected":{"status":"ok","outputs":{"pillar_spreads":[-3.0422956925934172e-18],"spread":[-3.0422956925934172e-18,-3.0422956925934172e-18,-3.0422956925934172e-18],"financing_df":[0.9900498337491681,0.9801986733067553,0.9607894391523232],"financing_rate":[0.04020066833667223,0.040402680053511615,0.040810774192388224],"forward_financing":[0.04020066833667223,0.04020066833667223,0.040402680053511615],"borrow_fee":null}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["hand","reference-computed","quantlib-1.44-interp"]}
{"case_id":"termfin_j-0003","operation":"repo.term.curve","inputs":{"funding_times":[1.0],"funding_zero_rates":[0.04],"quote_times":[1.0],"repo_rates":[0.05],"borrow_times":[0.25,1.0],"borrow_fees":[0.003,0.005],"query_times":[0.25,0.625,1.0]},"expected":{"status":"ok","outputs":{"pillar_spreads":[0.008790164169432005],"spread":[0.008790164169432005,0.008790164169432005,0.008790164169432005],"financing_df":[0.9878765474230741,0.9699663948145804,0.9523809523809523],"financing_rate":[0.049088937716157084,0.04954168366405872,0.05],"forward_financing":[0.049088937716157084,0.04923923881415834,0.04923923881415834],"borrow_fee":[0.003,0.0046,0.005]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["hand","reference-computed","quantlib-1.44-interp"]}
{"case_id":"termfin_j-0004","operation":"repo.term.curve","inputs":{"funding_times":[0.25,0.5,1.0,2.0],"funding_zero_rates":[0.04,0.041,0.0415,0.042],"quote_times":[0.08333333333333333,0.25,0.5,1.0],"repo_rates":[0.0425,0.043,0.0435,0.044],"borrow_times":[0.25,1.0],"borrow_fees":[0.003,0.005],"query_times":[0.08333333333333333,0.25,0.5,1.0]},"expected":{"status":"ok","outputs":{"pillar_spreads":[0.0024249168108619232,0.0027705181549727933,0.0020336869244992704,0.001559489460446972],"spread":[0.0024249168108619232,0.0027705181549727933,0.0020336869244992704,0.001559489460446972],"financing_df":[0.9964708324683413,0.9893643334157803,0.9787129924149743,0.9578544061302682],"financing_rate":[0.0425,0.043,0.0435,0.044],"forward_financing":[0.0425,0.043097363504255755,0.04353203067029433,0.04355272816246635],"borrow_fee":[0.003,0.003,0.004333333333333333,0.005]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed","quantlib-1.44-interp"]}
{"case_id":"termfin_j-0005","operation":"repo.term.curve","inputs":{"funding_times":[0.25,0.5,1.0,2.0],"funding_zero_rates":[0.04,0.041,0.0415,0.042],"quote_times":[0.08333333333333333,0.25,0.5,1.0],"repo_rates":[0.0425,0.043,0.0435,0.044],"borrow_times":[0.25,1.0],"borrow_fees":[0.003,0.005],"query_times":[0.01,0.1,0.3,0.42,0.77,0.99]},"expected":{"status":"ok","outputs":{"pillar_spreads":[0.0024249168108619232,0.0027705181549727933,0.0020336869244992704,0.001559489460446972],"spread":[0.0024249168108619232,0.002511317146889641,0.002524907744814952,0.002174035730303751,0.0017011328588002561,0.0015642793338212378],"financing_df":[0.9995758408128445,0.9957578915548413,0.9872248318549751,0.9821088858960507,0.9673935632242738,0.9582671894161062],"financing_rate":[0.042433917451487065,0.04260180593231111,0.04313495005665053,0.04337389808343251,0.04377331356797567,0.04399018832193435],"forward_financing":[0.042433917451487065,0.04260238234820023,0.04321740815530725,0.04340952780621629,0.04346088361606423,0.04329013637118207],"borrow_fee":[0.003,0.003,0.0034444444444444444,0.004079365079365079,0.004800865800865801,0.004993265993265993]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed","quantlib-1.44-interp"]}
{"case_id":"termfin_j-0006","operation":"repo.term.curve","inputs":{"funding_times":[0.25,0.5,1.0,2.0],"funding_zero_rates":[0.04,0.041,0.0415,0.042],"quote_times":[0.08333333333333333,0.25,0.5,1.0],"repo_rates":[0.0425,0.043,0.0435,0.044],"borrow_times":[],"borrow_fees":[],"query_times":[0.2,0.6]},"expected":{"status":"ok","outputs":{"pillar_spreads":[0.0024249168108619232,0.0027705181549727933,0.0020336869244992704,0.001559489460446972],"spread":[0.0027273179869589347,0.0018756211031485043],"financing_df":[0.9914909450931304,0.9745052500087722],"financing_rate":[0.042910401496759926,0.04360289488948079],"forward_financing":[0.042910401496759926,0.043575175926977516],"borrow_fee":null}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed","quantlib-1.44-interp"]}
{"case_id":"termfin_j-0007","operation":"repo.term.curve","inputs":{"funding_times":[0.25,0.5,1.0,2.0],"funding_zero_rates":[0.04,0.041,0.0415,0.042],"quote_times":[0.25,0.5,1.0],"repo_rates":[0.0395,0.038,0.039],"borrow_times":[],"borrow_fees":[],"query_times":[0.25,0.4,0.75]},"expected":{"status":"ok","outputs":{"pillar_spreads":[-0.0006937567290575212,-0.00335649151882448,-0.0032412878829096614],"spread":[-0.0006937567290575212,-0.0026908078213827404,-0.0032796890948812675],"financing_df":[0.9902215620745142,0.9848916174877865,0.9718631922139249],"financing_rate":[0.0395,0.03835036831451352,0.03860187731701739],"forward_financing":[0.0395,0.03607804481284256,0.03830176151258097],"borrow_fee":null}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed","quantlib-1.44-interp"]}
{"case_id":"termfin_j-0008","operation":"repo.term.curve","inputs":{"funding_times":[0.25,0.5,1.0,2.0],"funding_zero_rates":[0.04,0.041,0.0415,0.042],"quote_times":[0.5,2.0],"repo_rates":[-0.001,0.002],"borrow_times":[],"borrow_fees":[],"query_times":[0.5,1.5,2.0]},"expected":{"status":"ok","outputs":{"pillar_spreads":[-0.042000250083364596,-0.04000398936523128],"spread":[-0.042000250083364596,-0.04022579611169053,-0.04000398936523128],"financing_df":[1.0005002501250626,0.9975915990301382,0.9960159362549801],"financing_rate":[-0.001,0.0016094769123311853,0.002],"forward_financing":[-0.001,0.002915673205099328,0.0031639308525174352],"borrow_fee":null}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed","quantlib-1.44-interp"]}
{"case_id":"termfin_j-0022","operation":"eq.forward.term_financed","inputs":{"funding_times":[1.0],"funding_zero_rates":[0.04],"quote_times":[1.0],"repo_rates":[0.05],"borrow_times":[],"borrow_fees":[],"spot":100.0,"maturity_years":1.0,"dividend_times":[],"dividend_amounts":[]},"expected":{"status":"ok","outputs":{"forward":105.0,"carry":5.0,"carry_factor":0.9523809523809523,"financing_df":0.9523809523809523,"pv_dividends":0.0}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["hand","reference-computed","quantlib-1.44-interp"]}
{"case_id":"termfin_j-0023","operation":"eq.forward.term_financed","inputs":{"funding_times":[1.0],"funding_zero_rates":[0.04],"quote_times":[1.0],"repo_rates":[0.05],"borrow_times":[],"borrow_fees":[],"spot":100.0,"maturity_years":1.0,"dividend_times":[0.5],"dividend_amounts":[2.0]},"expected":{"status":"ok","outputs":{"forward":102.95060984680808,"carry":2.9506098468080806,"carry_factor":0.9523809523809523,"financing_df":0.9523809523809523,"pv_dividends":1.9518001458970664}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["hand","reference-computed","quantlib-1.44-interp"]}
{"case_id":"termfin_j-0024","operation":"eq.forward.term_financed","inputs":{"funding_times":[0.25,0.5,1.0,2.0],"funding_zero_rates":[0.04,0.041,0.0415,0.042],"quote_times":[0.08333333333333333,0.25,0.5,1.0],"repo_rates":[0.0425,0.043,0.0435,0.044],"borrow_times":[0.25,1.0],"borrow_fees":[0.003,0.005],"spot":50.0,"maturity_years":0.75,"dividend_times":[0.1,0.4,0.9],"dividend_amounts":[0.3,0.35,0.4]},"expected":{"status":"ok","outputs":{"forward":50.79389914716967,"carry":0.7938991471696651,"carry_factor":0.9717032367465726,"financing_df":0.9682275311731344,"pv_dividends":0.6434037917162647}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed","quantlib-1.44-interp"]}
{"case_id":"termfin_j-0025","operation":"eq.forward.term_financed","inputs":{"funding_times":[0.25,0.5,1.0,2.0],"funding_zero_rates":[0.04,0.041,0.0415,0.042],"quote_times":[0.08333333333333333,0.25,0.5,1.0],"repo_rates":[0.0425,0.043,0.0435,0.044],"borrow_times":[],"borrow_fees":[],"spot":50.0,"maturity_years":0.75,"dividend_times":[0.1,0.4,0.9],"dividend_amounts":[0.3,0.35,0.4]},"expected":{"status":"ok","outputs":{"forward":50.97689866158578,"carry":0.9768986615857751,"carry_factor":0.9682275311731344,"financing_df":0.9682275311731344,"pv_dividends":0.6427632620297468}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed","quantlib-1.44-interp"]}
{"case_id":"termfin_j-0026","operation":"eq.forward.term_financed","inputs":{"funding_times":[0.25,0.5,1.0,2.0],"funding_zero_rates":[0.04,0.041,0.0415,0.042],"quote_times":[0.08333333333333333,0.25,0.5,1.0],"repo_rates":[0.0425,0.043,0.0435,0.044],"borrow_times":[0.25,1.0],"borrow_fees":[0.003,0.005],"spot":50.0,"maturity_years":1.0,"dividend_times":[-0.1,1.0],"dividend_amounts":[5.0,0.5]},"expected":{"status":"ok","outputs":{"forward":51.439651413858016,"carry":1.4396514138580165,"carry_factor":0.9626556713212654,"financing_df":0.9578544061302682,"pv_dividends":0.4813278356606327}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed","quantlib-1.44-interp"]}
```

## Outside-library evidence and limits (from the project's own page)

13 golden cases with status ok in `datasets/golden/stage_j` for `repo.term.curve`, `eq.forward.term_financed`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| eq.forward.term_financed: hand, reference-computed, quantlib-1.44-interp | 2 |
| eq.forward.term_financed: reference-computed, quantlib-1.44-interp | 3 |
| repo.term.curve: hand, reference-computed, quantlib-1.44-interp | 3 |
| repo.term.curve: reference-computed, quantlib-1.44-interp | 5 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free term repo or stock borrow quotes. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

- (stage-j-rulings-curves.md) | J-C-1 | Operations and contract | Adds `repo.term.curve`, `eq.forward.term_financed` (`02-curves/financing-term-structure.md`) and `liq.curve.cost` (`10-execution/liquidity-curve.md`). No new error code; the general per-array limit applies. Contract 1.15.0 (new operations are a minor version), reported by all four builds and expected by the runner. **Coordinator:** the stage J wave 3 lane may also take 1.15.0; at merge keep one number for the union (1.15.0 if only one lane bumped by then, else 1.16.0 for the later merge) and update `conformance/runner/runner.py`, `stub_cli.py`, the four `version` writers and the version tests in one commit |
