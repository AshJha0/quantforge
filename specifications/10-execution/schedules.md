# Execution schedules: TWAP, VWAP, POV (DRAFT)

Spec version 0.1.0 (DRAFT, stage H wave 1). Status: Specified, not implemented. Rulings: `stage-h-rulings-w1.md` HR-2 to HR-4, HR-9. Plan items 14.7 H-3, 15.1 "Execution schedules".

**Plain idea.** A parent order of `X` units is split into child slices over `N` buckets: evenly in time (TWAP), in proportion to an expected volume profile (VWAP), or as a fixed share of the market volume actually seen (POV).

Sources:
- [Kis13] R. Kissell, *The Science of Algorithmic Trading and Portfolio Management*, Academic Press, 2013 (VWAP and POV definitions). Not free; chapter and pages NOT verified. Evidence class: textbook, recalled.
- [BL98] D. Bertsimas, A. Lo, "Optimal control of execution costs", *J. Financial Markets* 1 (1998) 1-50 (equal slicing optimal under linear permanent impact without risk aversion). Page of the result NOT verified. Evidence class: paper, recalled.
- Hand calculation for every golden below (integer arithmetic). Evidence class: hand calculation.

## `exec.schedule.twap`
Inputs `quantity` X (> 0), `n_buckets` N (1 to 100,000), `mode` `UNITS` or `CONTINUOUS`. Output `slices` (length N). UNITS: `floor(X/N)` each, remainder `X mod N` one unit to slices 0, 1, ... (HR-3). X <= 0, or non-integer X in UNITS: `E_INPUT`.

## `exec.schedule.vwap`
Inputs `quantity`, `profile` (length N, non-negative; normalised internally), `mode`. Slice i = `X w_i / sum w`; UNITS by largest remainder (HR-3). All-zero profile: `E_DOMAIN`.

## `exec.schedule.pov`
Inputs `quantity`, `participation` p in (0, 1) (HR-4), `market_volume` (outside volume per bucket). Child i = `min(remaining, p v_i / (1 - p))`, floored in UNITS. Outputs `slices`, `filled`, `residual` (may be > 0; never an error).

## Golden cases

| Case | Input | Expected | Derivation |
|---|---|---|---|
| sched_h-0001 | TWAP X = 1,000, N = 3, UNITS | [334, 333, 333] | floor 333, remainder 1 to slice 0 |
| sched_h-0002 | TWAP X = 1,000, N = 4, CONTINUOUS | [250, 250, 250, 250] | X/N |
| sched_h-0003 | VWAP X = 1,000, profile [1, 2, 3, 4], CONTINUOUS | [100, 200, 300, 400] | weights over 10 |
| sched_h-0004 | VWAP X = 10, profile [1, 1, 1], UNITS | [4, 3, 3] | 3.333 each, equal remainders, earliest wins |
| sched_h-0005 | POV X = 1,000, p = 0.2, v = [1000, 2000, 4000], UNITS | [250, 500, 250], residual 0 | p/(1-p) = 0.25; third capped at remaining 250 |
| sched_h-0006 | POV X = 1,000, p = 0.1, v = [900, 900], CONTINUOUS | [100, 100], residual 800 | 0.1/0.9 x 900 |
| sched_h-0007 | POV p = 1.0 | `E_DOMAIN` | HR-4 |
| sched_h-0008 | VWAP profile [0, 0] | `E_DOMAIN` | |

## Property tests
Slices sum to X (HR-3); POV realised participation `s_i / (s_i + v_i)` equals p wherever not capped.

## Limitations
The volume profile is an input (no forecast); no limit prices. Adaptive algos (arrival price, market-on-close, liquidity seeking) and baskets are wave 2.
