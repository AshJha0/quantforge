# Hedge slippage: realised execution cost against the cost model

Spec version 1.0.0. Status: Specified (stage I, wave 4d). Rulings: `stage-i-rulings.md` I-36 to I-38. Suite `datasets/golden/stage_i/hedgeslip_i`, written by `oracle/python/gen_stage_i_w4d.py`.

**Plain idea.** Wave 4a chose hedges with a model of what trading costs: half the spread plus linear impact. After the hedge is traded, the fills show what it really cost. Implementation shortfall measures that cost against the price when the decision was made. It splits into the cost of what was filled and the opportunity cost of what was not [P88]. Slippage is the realised execution cost minus the model's cost for the same filled size. A slippage that is persistently positive says the cost model is too optimistic and the cost weights of wave 4a should be revisited. This is the traceability row "Hedge slippage estimation" (v1 Phase 6).

Sources:
- [P88] A. F. Perold, "The implementation shortfall: paper versus reality", *Journal of Portfolio Management* 14(3), 1988, 4-9 (not opened in this session).
- [K14] R. Kissell, *The Science of Algorithmic Trading and Portfolio Management*, Academic Press, 2014, chapter 3 (cost decomposition: execution and opportunity cost) (not opened).
- `08-hedging/hedge-costs-and-frontier.md` (the cost model `h |q| + eta q^2`), normative here.

## `hedge.slippage.report`

### Inputs

`orders`: one or more, each `{quantity, decision_price, final_price, half_spread, impact, fills}`, where `quantity` is signed (positive buys) and `fills` is a list of `{quantity, price}`, possibly empty. Fill quantities carry the order's sign. `final_price` is the price at which the unfilled rest is valued, normally the price at the end of the trading horizon.

### Checks, in order

1. No orders; an order quantity of 0; a fill of the other sign or of 0; fills adding up to more than the order in absolute value: `E_INPUT`.
2. A price (decision, final or fill) at or below 0; a negative `half_spread` or `impact`: `E_DOMAIN`.

### Outputs (I-36, I-37)

Per order, with `d` the decision price, `q_f` the filled quantity and `Q` the order:
- `filled_quantity = sum fill quantities`;
- `average_price = sum q p / q_f`, or `null` when nothing was filled (I-37);
- `execution_cost = sum q (p - d)` (positive is a cost, for buys and sells alike);
- `opportunity_cost = (Q - q_f)(final_price - d)`;
- `shortfall = execution_cost + opportunity_cost` [P88];
- `model_cost = half_spread |q_f| + impact q_f^2` (the wave 4a model, on the filled size);
- `slippage = execution_cost - model_cost`.

`total`: the sums of `execution_cost`, `opportunity_cost`, `shortfall`, `model_cost` and `slippage` over orders.

## Validation cases and oracle

`hedgeslip_i`: 6 value cases and 6 error cases. The value cases are a buy filled in two pieces, a partly filled sell, both together, an order with no fills, a fill better than the decision price (negative cost), and a fill exactly at the model cost (slippage exactly 0). Values use exact rational arithmetic on the binary64 inputs and are rounded once. The generator asserts the identities `shortfall = execution + opportunity` and `slippage = execution - model` on every order and total.

Outside (I-2): 0 of 12. No library computes implementation shortfall, and the operation is arithmetic. Stage I so far: 108 of 263 = 41.1%.

## Convergence and limit cases

| Method | Asserted behaviour | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Exact arithmetic | No iteration; identities hold to rounding | Every value case | No fills: all opportunity cost, model cost 0 (`-0004`) | Exact rational values |

## Limitations

- The decision price is one number per order. Arrival-price, VWAP or close benchmarks are other choices and would be new inputs.
- Fees and commissions are not separated. Add them to the fill prices, or wait for a later input.
- Slippage estimation over many hedges, a regression of slippage on size, is research (stage J), not a golden.

## Spec questions and rulings

| # | Question | Ruling |
|---|---|---|
| Q-I19 | Model cost on the ordered or the filled size? | Filled (I-36). The model prices what was traded; the unfilled part is the opportunity cost |
| Q-I20 | Average price with no fill? | `null` (I-37), the only `null` in this operation |
