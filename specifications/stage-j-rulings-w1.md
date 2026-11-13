# Stage J rulings, wave 1 (spec lane)

**Status: specified, not implemented (wave 1 code lands in v0.9.0).** In v0.8.3 only this document ships; the stage J goldens, CLI contract block and name-map entries it mentions are not in this release.

Normative for stage J (v0.9) wave 1: backtester, purged CV, regime labelling, research statistics. Kept in a separate file from `stage-j-rulings.md` (lane J-0b, rulings J-0b.1 to J-0b.3) so the two branches merge without conflict; the coordinator may fold both into one file at the stage J merge without renumbering. Earlier rulings still hold, among them `stage-f-rulings.md` F-1 to F-3 and F-5, F-6, `stage-g-rulings.md` G-50 and `r6-rulings.md` R6-8.1. Append-only; an amendment is a new row that names the row it amends.

## Wave 1

| # | Point | Ruling |
|---|---|---|
| J-1 | Operations and contract | Wave 1 adds `research.backtest.run` (`11-research/backtester.md`), `research.cv.purged_kfold`, `research.cv.cpcv_paths` (`purged-cv.md`), `research.regime.viterbi` (`regimes.md`), `research.stats.psr`, `research.stats.dsr`, `research.stats.pbo`, `research.stats.power` (`research-statistics.md`). No new error code: target contract 1.13.0 (new operations are a minor version). The fill model is full fill at the close plus or minus the half spread; stage H's queue fill simulator is a separate operation and does not change this one |
| J-2 | Execution lag and look-ahead | The position that earns bar `t`'s price move is the one held before bar `t`'s trade. `lag = 0` (decide and trade at the same close) is legal so that a look-ahead canary can be built and caught; a study runner refuses `lag = 0` unless its prereg says so |
| J-3 | Two engines, one answer | `engine = EVENT` and `VECTOR` are two implementations of one definition; every golden is valid for both, and each language's property test compares them to 1e-10 relative (plan J-3). The hand example `backtest_j-0001` is the 1e-12 check |
| J-4 | Costs | Spread cost is charged on traded notional times the half spread; commission per unit; fixed fee per bar with a non-zero trade. Costs scale linearly so the 0.5x, 1x, 2x cost table of plan 11.3 is three calls with scaled inputs |
| J-5 | `E_LIMIT` sizes, backtester | Bars 1,000,000. Checked after `E_SCHEMA`, before F-2 |
| J-6 | Drawdown peak | Peak equity starts at 0 (the starting capital before any P&L), so a strategy that only loses has drawdown equal to its loss |
| J-7 | Fold layout | Contiguous blocks in `array_split` order, no shuffle; time order is the caller's index order |
| J-8 | Embargo size | `h = floor(embargo_pct * n)` observations after each test block, as `int(n * pct)` in [LdP18] section 7.4.2; overlap tests use closed intervals |
| J-9 | `E_LIMIT` sizes, CV | Observations 1,000,000; CPCV groups 64 |
| J-10 | Emission input | Exactly one of `emission` or (`observations`, `means`, `sds`); both or neither is `E_INPUT`. The direct form lets a textbook example with discrete emissions be a golden |
| J-11 | Viterbi ties | Smallest state index wins in the recursion and at the end. Goldens keep a margin of `1e-6` in log probability (asserted), so the tie rule is tested only by property tests |
| J-12 | `E_LIMIT` sizes, Viterbi | Steps 100,000; states 32. A path of zero probability is `E_DOMAIN` |
| J-13 | DSR with one trial | `N = 1` gives `SR0 = 0`, so DSR equals PSR against 0. `N` is the logged trial count (`research/trials.csv`), never a smaller number |
| J-14 | PSR variance term | `1 - skew sr + (kurtosis - 1)/4 sr^2 <= 0` is `E_DOMAIN`, not a clamp. `kurtosis < 1` is `E_DOMAIN` (impossible for any distribution) |
| J-15 | CSCV partitions | `S` even, `2 <= S <= 16`, `T` divisible by `S`, at least 2 rows per block; otherwise `E_INPUT`, `S > 16` is `E_LIMIT` (12,870 combinations). Cells `T x N` at most 10,000,000, strategies at most 10,000 |
| J-16 | CSCV ties | In-sample winner: lowest strategy index among equal metrics. Out-of-sample rank: average rank (1 = worst) |
| J-17 | Zero dispersion | Under `SHARPE`, a block where a strategy's sample standard deviation is 0 is `E_DOMAIN` |
| J-18 | Units | PSR and DSR take per-period Sharpe ratios; `research.stats.power` takes years and returns annualised Sharpe ratios, as `research/preregs/README.md` |
| J-19 | Outside checks of wave 1 | Counted in the handover: DSR worked example (recalled printed digits, paper not yet opened: provisional), textbook Viterbi example (hand plus brute force), prereg MDS table (hand), ten-trade backtest (hand), purged CV example (hand). No outside library oracle is used in wave 1; the outside share is reported, not claimed, until J-1 opens the papers |
