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

Class `simple_analytic` for every value output. Evidence (J-C-9): three value cases are hand derivations (`termfin_j-0001` to `-0003`), two more for the forward (`-0022`, `-0023`); the rest are reference-computed by `oracle/python/gen_stage_j_curves.py` in mpmath at 50 digits from this text. There is no outside library check: QuantLib's `PiecewiseZeroSpreadedTermStructure` interpolates zero spreads, not cumulative spreads, and no free published worked example of a term repo spread curve was found, so this curve is self-assessed (Implemented, not Validated). Property tests in each language: quote round trip, forward rates chaining to `1/P_f`, D22 reduction, borrow and dividends lowering the forward.

## Limitations

- Money-market simple quotes on a single time axis; day counts and settlement lags are the caller's (convert dates to year fractions first). No GC/special collateral classes: one curve per collateral.
- No extrapolation beyond the last quote, no smoothing, no turn-of-year jumps in the spread.
- Bond carry with a term repo curve is not an operation yet: `repo.forward` still takes one repo rate for the period, which a caller can read from this curve as `financing_rate` at the horizon.

## Sources

- [Hagan-West06] P. Hagan, G. West, "Interpolation methods for curve construction", *Applied Mathematical Finance* 13(2) 2006, 89-129. Raw (flat-forward) interpolation. Evidence class: paper, read for stage F (`interpolation-methods`); applied here to a spread.
- [Piterbarg10] V. Piterbarg, "Funding beyond discounting: collateral agreements and derivatives pricing", *Risk* February 2010. Secured and unsecured rates as separate curves. Evidence class: paper, recalled.
- [Choudhry10] M. Choudhry, *The Repo Handbook*, 2nd ed., Butterworth-Heinemann 2010: term repo as a simple money-market rate; specials below GC. Evidence class: book, recalled; definitions only.
- Ruling D22 (`stage-d-rulings.md`) and `equity-curves.md` for the flat form this page extends.
