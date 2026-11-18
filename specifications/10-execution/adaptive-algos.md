# Adaptive algorithms: arrival price, close, liquidity seeking, pairs and baskets

Spec version 0.1.0 (stage H wave 2; spec lane 2026-11-18). Status: implemented in all four builds (Python, Java, C++, Rust; 2026-11-18). Rulings: `stage-h-rulings-w2-exec.md` HR-59 to HR-63, with HR-2, HR-3, HR-4, HR-56 from earlier stage H files. Plan item STAGE_H_START.md H-14 (acceptance: schedule identities plus a simulated-book method test).

**Plain idea.** The wave-1 schedules (`schedules.md`) slice an order without looking at the market. The algorithms here react to something: arrival price trades early because waiting costs risk; a close algorithm puts what it can into the closing auction and spreads the rest over the last buckets; liquidity seeking takes a share of whatever depth sits inside its limit; pairs and baskets keep several legs in step so the cash (or the hedge) stays balanced while the orders work.

Sources:
- [AC00] R. Almgren, N. Chriss, "Optimal execution of portfolio transactions", *Journal of Risk* 3(2) (2000/01) 5-39; read 2026-11-15 in the December 2000 preprint (see `almgren-chriss.md` for the copy and the preprint page numbers). Used: eq. (17), p. 14, `x_j = X sinh(kappa (T - t_j)) / sinh(kappa T)`, for the arrival-price holdings; eq. (10), p. 12, with N to infinity, `V = 1/3 sigma^2 X^2 T`, for the timing-risk line in `tca-pretrade.md`. Evidence class: paper, read.
- [CJP15] A. Cartea, S. Jaimungal, J. Penalva, *Algorithmic and High-Frequency Trading*, Cambridge University Press, 2015: chapters on targeting volume / close and on pairs (co-integrated) trading. **UNVERIFIED**: not free, not read in this lane; chapter and page numbers not checked. Cited only for the vocabulary (close auction participation cap, cash-balanced and hedge-ratio legs); no formula below rests on it. Evidence class: textbook, recalled, UNVERIFIED.
- [Kis13] as in `schedules.md` (arrival price and close algorithms as families). Pages NOT verified.
- Hand calculation for every golden below (exact rational arithmetic, `ln 2` urgency chosen so that every `sinh` ratio is rational), by this spec lane on 2026-11-18. Blind re-derivation (DR-H2, 2026-11-18, second lane, inputs-only packet from `wave2_make_packet.sh exec`): 25/25 agree (14 MATCH, 11 error cases SHAPE-ONLY in the error wrapper only), 0 VALUE MISMATCH; program/STAGE_H_BLIND_EXEC.md. Generator: `oracle/python/gen_stage_h_w2_exec.py`.

Shared conventions (HR-2, HR-3, HR-56): `side` is `BUY` (s = +1) or `SELL` (s = -1); `mode` is `UNITS` or `CONTINUOUS`, absent means `CONTINUOUS`; quantities > 0 unless stated; non-integer quantity in `UNITS` is `E_INPUT`; prices <= 0 are `E_DOMAIN`; non-finite numbers are `E_DOMAIN`. UNITS largest-remainder allocation and its tie rule (earliest index wins) are HR-3. An error in a pair or basket leg names the leg's own key as its `field` (for example `quantity` for a non-positive or, in `UNITS`, non-integer leg quantity), not `leg_a`, `leg_b` or `legs` (decided at integration, 2026-11-18, so the four builds agree).

## `exec.algo.arrival`
Inputs `quantity` X, `n_buckets` N (1 to 100,000), `urgency` kappa (per bucket, >= 0), `mode`. Holdings `x_j = X sinh(kappa (N - j)) / sinh(kappa N)` for j = 0..N ([AC00] eq. (17) with tau = 1 bucket); kappa = 0 is the limit `x_j = X (N - j) / N` (TWAP). Output `slices` n_j = x_{j-1} - x_j, j = 1..N.
UNITS (HR-67, amending HR-59 on 2026-11-18): the continuous slices are allocated by largest remainder, ties to the earliest bucket, exactly as HR-3, so kappa = 0 equals `exec.schedule.twap` in UNITS too and every slice is within 1 of its continuous value. (HR-59 rounded the cumulative half up, which gave [333, 334, 333] for X = 1000, N = 3, kappa = 0 against TWAP [334, 333, 333]; found by the implementation lane. No golden value changed: alg_h-0003 gives [601, 400] under both rules.) kappa < 0: `E_DOMAIN`; N < 1: `E_INPUT`.
Identities: slices sum to X (exactly in UNITS); for kappa > 0 the CONTINUOUS slices are strictly decreasing; kappa = 0 equals `exec.schedule.twap`.

## `exec.algo.close`
Inputs `quantity` X, `close_volume` V_c (forecast closing-auction volume, >= 0), `auction_participation` p_c in [0, 1], `profile` w (length M >= 1, non-negative; the buckets before the close), `mode`. Output `auction_quantity` A = `min(X, p_c V_c)` (UNITS: `min(X, floor(p_c V_c))`), `slices` = the remainder X - A allocated over w exactly as `exec.schedule.vwap` (UNITS by largest remainder, HR-3) (HR-60).
If X - A = 0 the slices are all zero and the profile may be all zero; otherwise an all-zero profile is `E_DOMAIN`. p_c outside [0, 1] or V_c < 0: `E_DOMAIN`; empty profile: `E_INPUT`.
Identity: `auction_quantity + sum slices = X`.

## `exec.algo.liquidity_seek`
Inputs `side`, `quantity` X, `limit_price` L (> 0), `take_fraction` alpha in (0, 1], `books`: a list of K bucket snapshots, each a list of opposite-side levels `[price, size]` best first (asks ascending for BUY, bids descending for SELL; sizes > 0). Bucket i: available `A_i` = total size at levels with price <= L (BUY) or >= L (SELL); child `c_i = min(R_{i-1}, alpha A_i)` with R_0 = X; the child walks the levels best first, inside the limit only (HR-61). Quantities are reals (no UNITS mode).
Outputs `slices` c_i, `avg_prices` (volume-weighted fill price per bucket; `null` when c_i = 0), `filled` = sum c_i, `residual` = X - filled, `notional` = sum of size x price over all fills, `avg_fill_price` = notional / filled (`null` when filled = 0).
Errors: alpha outside (0, 1], L <= 0, a level price <= 0: `E_DOMAIN`; a level size <= 0, levels not strictly ordered as stated, empty `books`: `E_INPUT`.
Method test (simulated book, acceptance H-14): on a planted book sequence the algorithm's per-bucket fills equal `min(R, alpha A_i)` exactly, every bucket average lies in [best level price, L] (BUY; mirrored for SELL), and no fill lies outside L.

## `exec.algo.pair`
Inputs `leg_a` {`side`, `quantity` X_A, `price` P_A}, `leg_b` {`side`, `price` P_B}, `pair_mode` `CASH_BALANCED` or `HEDGED`, `hedge_ratio` h (> 0, HEDGED only), `n_buckets` N, `mode`. Ratio r = P_A / P_B (CASH_BALANCED) or h (HEDGED); target X_B = r X_A. Leg A slices are `exec.schedule.twap` of X_A (HR-3). Leg B follows leg A: cumulative target `T_j = r C^A_j` (C^A_j cumulative leg-A quantity), UNITS `floor(T_j + 1/2)`, slices the differences (HR-62).
Outputs `slices_a`, `slices_b`, `quantity_b` (= sum slices_b), `cash_imbalance` per bucket `s_A C^A_j P_A + s_B C^B_j P_B` (signed; positive = net cash paid).
Errors: CASH_BALANCED with both legs on the same side: `E_INPUT`; h <= 0 or a price <= 0: `E_DOMAIN`.
Identities: CONTINUOUS CASH_BALANCED has `cash_imbalance` 0 in every bucket; UNITS CASH_BALANCED has `|cash_imbalance_j| <= P_B / 2` in every bucket; `quantity_b = floor(r X_A + 1/2)` in UNITS.

## `exec.algo.basket`
Inputs `legs` (list of {`side`, `quantity`, `price`}, at least one), `n_buckets` N, `mode`. Every leg is sliced by `exec.schedule.twap` (HR-3). Outputs `slices` (one list per leg), `cash_imbalance` per bucket `sum_k s_k C_kj P_k`, `gross_notional` = `sum_k X_k P_k` (HR-63).
Errors: empty `legs`: `E_INPUT`; a price <= 0: `E_DOMAIN`.
Identity: in CONTINUOUS mode `cash_imbalance_j = (j / N) cash_imbalance_N`; a basket with zero net cash at the end has zero imbalance in every bucket.

## Golden cases

Urgency `ln 2` is written to 17 significant digits as 0.69314718055994531; with it `sinh(ln 2) = 3/4`, `sinh(2 ln 2) = 15/8`, `sinh(3 ln 2) = 63/16`.

| Case | Input | Expected | Derivation |
|---|---|---|---|
| alg_h-0001 | arrival X = 1,000, N = 4, kappa = 0, CONTINUOUS | slices [250, 250, 250, 250] | kappa = 0 is TWAP |
| alg_h-0002 | arrival X = 1,000, N = 2, kappa = ln 2, CONTINUOUS | slices [600, 400] | x_1 = X / (2 cosh ln 2) = 1000 / 2.5 = 400 |
| alg_h-0003 | arrival X = 1,001, N = 2, kappa = ln 2, UNITS | slices [601, 400] | C_1 = 1001 - 400.4 = 600.6, rounds to 601 |
| alg_h-0004 | arrival X = 2,100, N = 3, kappa = ln 2, CONTINUOUS | slices [1100, 600, 400] | x = 2100 x (63/16, 15/8, 3/4, 0) / (63/16) = (2100, 1000, 400, 0) |
| alg_h-0005 | arrival X = 1,000, N = 4, kappa = -0.1 | `E_DOMAIN` | kappa < 0 |
| alg_h-0006 | arrival X = 1,000, N = 0, kappa = 0.5 | `E_INPUT` | N < 1 |
| alg_h-0007 | close X = 10,000, V_c = 50,000, p_c = 0.1, profile [1, 1, 2, 4], CONTINUOUS | auction 5000, slices [625, 625, 1250, 2500] | A = 5000; 5000 x w / 8 |
| alg_h-0008 | close X = 3,000, V_c = 50,000, p_c = 0.1, profile [1, 1, 2, 4], CONTINUOUS | auction 3000, slices [0, 0, 0, 0] | X below the cap |
| alg_h-0009 | close X = 10,002, V_c = 50,000, p_c = 0.1, profile [1, 1, 1], UNITS | auction 5000, slices [1668, 1667, 1667] | 5002 / 3 = 1667.33 each; equal remainders, earliest wins |
| alg_h-0010 | close X = 1,000, V_c = 50,000, p_c = 1.5, profile [1] | `E_DOMAIN` | p_c > 1 |
| alg_h-0011 | close X = 10,000, V_c = 50,000, p_c = 0.1, profile [0, 0] | `E_DOMAIN` | remainder 5000 > 0 with all-zero profile |
| alg_h-0012 | liquidity_seek BUY X = 1,000, L = 100.2, alpha = 0.5, books [[[100.0, 400], [100.1, 400], [100.3, 1000]], [[100.1, 600], [100.2, 600]]] | slices [400, 600], avg_prices [100.0, 100.1], filled 1000, residual 0, notional 100060, avg_fill_price 100.06 | A_1 = 800 (100.3 outside L), child 400 at 100.0; A_2 = 1200, child min(600, 600) at 100.1 |
| alg_h-0013 | liquidity_seek BUY X = 1,000, L = 100, alpha = 1, books [[[100, 300], [100.5, 1000]], [[101, 500]]] | slices [300, 0], avg_prices [100, null], filled 300, residual 700, notional 30000, avg_fill_price 100 | nothing inside L in bucket 2 |
| alg_h-0014 | liquidity_seek SELL X = 500, L = 99.9, alpha = 0.5, books [[[100, 200], [99.9, 200], [99.8, 1000]], [[99.95, 1000]]] | slices [200, 300], avg_prices [100, 99.95], filled 500, residual 0, notional 49985, avg_fill_price 99.97 | A_1 = 400, child 200 at 100; A_2 = 1000, child min(300, 500) at 99.95 |
| alg_h-0015 | liquidity_seek BUY X = 1,000, L = 101, alpha = 1, books [[[100, 300], [100.5, 300], [101, 1000]]] | slices [1000], avg_prices [100.55], filled 1000, residual 0, notional 100550, avg_fill_price 100.55 | walks three levels: 30000 + 30150 + 40400 |
| alg_h-0016 | liquidity_seek BUY X = 1,000, L = 101, alpha = 0, books [[[100, 300]]] | `E_DOMAIN` | alpha outside (0, 1] |
| alg_h-0017 | liquidity_seek BUY X = 1,000, L = 101, alpha = 1, books [[[100.5, 300], [100, 300]]] | `E_INPUT` | asks not ascending |
| alg_h-0018 | pair BUY A 1,000 at 50, SELL B at 25, CASH_BALANCED, N = 4, CONTINUOUS | slices_a [250, 250, 250, 250], slices_b [500, 500, 500, 500], quantity_b 2000, cash_imbalance [0, 0, 0, 0] | r = 2 |
| alg_h-0019 | pair BUY A 1,000 at 30, SELL B at 70, CASH_BALANCED, N = 3, UNITS | slices_a [334, 333, 333], slices_b [143, 143, 143], quantity_b 429, cash_imbalance [10, -10, -30] | r = 3/7; T = 143.14, 285.86, 428.57 round to 143, 286, 429; 10020 - 10010, 20010 - 20020, 30000 - 30030 |
| alg_h-0020 | pair BUY A 1,000 at 100, SELL B at 50, HEDGED, h = 0.8, N = 2, CONTINUOUS | slices_a [500, 500], slices_b [400, 400], quantity_b 800, cash_imbalance [30000, 60000] | 50000 - 20000; 100000 - 40000 |
| alg_h-0021 | pair BUY A 1,000 at 50, BUY B at 25, CASH_BALANCED, N = 2 | `E_INPUT` | same side |
| alg_h-0022 | pair BUY A 1,000 at 50, SELL B at 25, HEDGED, h = 0, N = 2 | `E_DOMAIN` | h <= 0 |
| alg_h-0023 | basket legs BUY 300 at 10, BUY 200 at 20, SELL 700 at 10, N = 2, CONTINUOUS | slices [[150, 150], [100, 100], [350, 350]], cash_imbalance [0, 0], gross_notional 14000 | 1500 + 2000 - 3500 |
| alg_h-0024 | basket legs BUY 3 at 10, SELL 1 at 30, N = 2, UNITS | slices [[2, 1], [1, 0]], cash_imbalance [-10, 0], gross_notional 60 | 20 - 30; 30 - 30 |
| alg_h-0025 | basket legs [], N = 2 | `E_INPUT` | empty legs |

Canonical JSON for every case: `datasets/golden/stage_h/alg_h.json` (inputs exactly as above; field names as in the operation sections).

## Acceptance tests (fixed 2026-11-18, before any build)
1. Schedule identities, every case and a property run of 1,000 random inputs per operation: slices sum to the order (`arrival`, `basket`; `close` with the auction; `pair` leg A and leg B against `quantity_b`), exactly in UNITS and to 1e-12 relative in CONTINUOUS; `filled + residual = X` for `liquidity_seek` to 1e-12 relative.
2. Arrival: kappa = 0 equals `exec.schedule.twap` on the same input; kappa > 0 CONTINUOUS slices strictly decreasing.
3. Pair: the CONTINUOUS and UNITS cash-imbalance bounds above; HEDGED `quantity_b = h X_A` (CONTINUOUS).
4. Simulated-book method test for `liquidity_seek`: 200 planted books (seeded generator, seed 20261118, 5 to 20 levels, tick 0.01) with known depth inside L; recovered per-bucket fills equal `min(R, alpha A_i)` to 1e-12 relative, every bucket average within [best, L], no fill outside L.
5. Goldens alg_h-0001..0025 in all four languages to the `simple_analytic` tolerance.

## Post-blind shape changes (2026-11-18, after the blind lane froze; no value changed)
Output field names are fixed as one name each: `slices` (arrival, close, liquidity_seek, basket), `auction_quantity`, `avg_prices`, `filled`, `residual`, `notional`, `avg_fill_price`, `slices_a`, `slices_b`, `quantity_b`, `cash_imbalance` (pair and basket: length N, entry j after bucket j = 1..N), `gross_notional`. An error is reported in the conformance case format `{"status": "error", "error_code": CODE}`; the blind lane's `{"error": CODE}` is the same result in another wrapper. Record: program/STAGE_H_BLIND_EXEC.md.

## Limitations
No forecasting: the close volume, profile and books are inputs. Arrival urgency is a parameter, not derived from a risk aversion (use `exec.ac.trajectory` for that). Liquidity seeking does not model queue position, hidden size or the book's reaction to our own orders. Pairs and baskets balance cash or a fixed hedge ratio only; no co-integration estimate, no beta re-estimation and no cross-leg fill risk.
