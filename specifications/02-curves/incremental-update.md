# Incremental curve update (stage K)

Spec version 0.1.0. Status: **PROPOSED** (stage K wave 1, plan 14.8 K-4). Rulings: `stage-k-rulings-w1.md` KR-5.

**Plain idea.** In a sequential bootstrap each discount factor depends only on the quotes up to its own maturity. When one quote ticks, the pillars before it cannot change, so only that pillar and the later ones need solving again. The test is that this shortcut gives the same curve as rebuilding everything.

**Formal statement.** Annual par swaps with accrual 1 and quotes `S_1..S_n` give `P_k = (1 - S_k sum_{i<k} P_i) / (1 + S_k)` [standard bootstrap identity; Hagan and West, "Interpolation methods for curve construction", *Applied Mathematical Finance* 13(2) 2006, section 2 (free preprint, UNVERIFIED section number)]. If quotes change only at indices `>= j` (0-based), then `P_0..P_{j-1}` are unchanged and `P_j..P_{n-1}` follow from the same recursion. The library's production bootstraps (stage B) use the same split by first changed index; this hand-sized instrument set exists so a blind lane can check the arithmetic.

## Operations

| Operation | Inputs | Outputs |
|---|---|---|
| `curve.bootstrap.par_annual` | `quotes` (decimals, 1 to 200, each > -1; else `E_DOMAIN`; more than 200 `E_LIMIT`) | `discount_factors` |
| `curve.incremental.update` | `previous_quotes`, `previous_discount_factors`, `new_quotes` (same length, else `E_INPUT`) | `discount_factors`, `first_changed_index` (`null` if none changed), `recomputed` (count) |

`curve.incremental.update` checks that `previous_discount_factors` equals `curve.bootstrap.par_annual(previous_quotes)` bit for bit; if not, `E_INPUT` (a stale cache must not be patched).

## Golden value cases (hand-derived; 30-digit check by mpmath)

Base quotes `[0.02, 0.025, 0.03]`.

Output fields compared: `curve.bootstrap.par_annual` returns `discount_factors` (array of binary64, same length as `quotes`). `curve.incremental.update` returns `discount_factors` (array of binary64, length 3 here), `first_changed_index` (0-based integer, or `null`) and `recomputed` (integer). Error cases compare `error.code` (string) only.

| Case | Operation | Input | Expected discount_factors | Expected first_changed_index | Expected recomputed |
|---|---|---|---|---|---|
| inc_k-0001 | `curve.bootstrap.par_annual` | `quotes` = base | [0.980392156862745098, 0.951697752271640363, 0.914599323034920812] | not an output | not an output |
| inc_k-0002 | `curve.incremental.update` | previous = base and its bootstrap; `new_quotes` = [0.02, 0.026, 0.03] | [0.980392156862745098 (copied), 0.949814623705232580, 0.914654171439767640] | 1 | 2 |
| inc_k-0003 | `curve.incremental.update` | previous = base and its bootstrap; `new_quotes` = [0.02, 0.025, 0.031] | [first two copied from inc_k-0001, 0.911838227756386082] | 2 | 1 |
| inc_k-0004 | `curve.incremental.update` | previous = base and its bootstrap; `new_quotes` = base | inc_k-0001 values, all copied | null | 0 |

<!-- blind:strip -->
Derivation of inc_k-0001: `P_1 = 1/1.02`; `P_2 = (1 - 0.025 P_1)/1.025 = 0.975490196.../1.025`; `P_3 = (1 - 0.03 (P_1 + P_2))/1.03`.
<!-- /blind:strip -->
Tolerance against the expected decimals: 1e-15 absolute (binary64). Between `update` and a full rebuild in the same build: equal to 1e-12 relative (K-4), expected bit-identical.

| Case | Operation | Input | Expected error.code |
|---|---|---|---|
| inc_k-0005 | `curve.incremental.update` | previous = base and its bootstrap; `new_quotes` = [0.02, 0.025] (lengths differ) | E_INPUT |
| inc_k-0006 | `curve.incremental.update` | previous = base; `previous_discount_factors` = the base bootstrap with the last element moved up by one unit in the last place (next binary64 toward +infinity); `new_quotes` = [0.02, 0.026, 0.03] | E_INPUT |

## Acceptance (fixed before any run)

- inc_k-0001..0006 in four languages.
- Property: for 10,000 random quote vectors and random single or multi-index changes, `update` equals full rebuild to 1e-12 relative, and copied pillars are bit-identical.
- The same property on the stage B production bootstrap (all instrument types it supports), which is the K-4 claim; this hand set alone does not make it.
