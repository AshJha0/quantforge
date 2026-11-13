# Regime labelling: Viterbi path of a hidden Markov model

Spec version 1.0.0. Status: specified, not implemented (wave 1 code lands in v0.9.0; no build implements these operations and their goldens are not in this release). Rulings: `stage-j-rulings-w1.md` J-10 to J-12. Suite: `datasets/golden/stage_j/regime_j`, written by `oracle/python/gen_stage_j_w1.py`. Plan item A4 (plan 12.5; "Viterbi ported with goldens; descriptive only"). Baum-Welch estimation stays in the Python research package (wave 2 or later) and is not a CLI operation in wave 1.

**Plain idea.** Given a model of how the market switches between a few states (for example calm and turbulent) and how returns look in each, the Viterbi algorithm finds the single most likely sequence of states for the observed returns. The labels are descriptive: they say which regime the model thinks each day was in, not a forecast.

Sources:
- [Rab89] L. R. Rabiner, "A tutorial on hidden Markov models and selected applications in speech recognition", *Proceedings of the IEEE* 77(2), 1989, 257-286, section III.B (Viterbi recursion, eqs. 32a-35) (not opened in this session). Evidence class: paper, recalled.
- [Ham89] J. D. Hamilton, "A new approach to the economic analysis of nonstationary time series and the business cycle", *Econometrica* 57(2), 1989, 357-384 (Markov-switching regimes in finance) (not opened). Evidence class: paper, recalled.
- Textbook two-state example (states Healthy and Fever, observations normal, cold, dizzy; most likely path Healthy, Healthy, Fever with joint probability 0.01512), widely reproduced (for example the Wikipedia "Viterbi algorithm" article; not opened in this session). The generator recomputes it by hand and by enumerating all 8 paths; `regime_j-0001`. Evidence class: hand calculation plus brute force.

## `research.regime.viterbi`

### Inputs

- `initial` (length `K >= 1`): state probabilities at `t = 0`.
- `transition` (`K x K`, rows sum to 1): `A_ij = P(s_t = j | s_{t-1} = i)`.
- Emissions, exactly one of (ruling J-10):
  - `emission` (`T x K`): the probability or density of observation `t` under state `j`, given directly; or
  - `observations` (length `T`) with `means` and `sds` (length `K`, `sds > 0`): Gaussian densities.

### Checks, in order

`E_LIMIT` (`T > 100,000` or `K > 32`, J-12); F-2; both or neither emission form, or shapes wrong: `E_INPUT`; a negative probability, a row of `initial` or `transition` whose sum differs from 1 by more than `1e-9`, a negative emission, or an `sd <= 0`: `E_DOMAIN`; every path has probability zero: `E_DOMAIN`.

### Algorithm

In logs (`log 0 = -inf`): `delta_0(j) = log initial_j + log e_0(j)`; `delta_t(j) = max_i (delta_{t-1}(i) + log A_ij) + log e_t(j)`, with back-pointer the maximising `i`; the path ends at `argmax_j delta_{T-1}(j)` and follows the back-pointers. Ties (ruling J-11): the smallest state index wins, both in the recursion and at the end. The generator keeps every golden's best path at least `1e-6` in log-probability above the runner-up, so a build's tie rule is pinned only by its own property test.

Gaussian log density: `-log sd - log(2 pi)/2 - (y - mean)^2 / (2 sd^2)`.

### Outputs

`states` (Integers, 0-based, length `T`) and `log_probability` (the joint log probability of the path and the observations, `max_j delta_{T-1}(j)`). Tolerance: `simple_analytic`; `states` exact.

## Limitations

Fixed parameters only; the operation does not fit them. Labels are in-sample (smoothed over the whole sample by construction), so they must never feed a trading signal at time `t` (look-ahead). A filtered, real-time label is the forward algorithm's argmax and is a later item.
