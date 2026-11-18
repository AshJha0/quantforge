# Blind notes (uc5)
Method: Decimal 60 digits for AC; exact Fractions for rounding and TCA (decimal-literal prices read exactly). Outputs as floats; lots/filled ints.
- Output names exactly as use-case-5 spec. No `model` label output (HR-10) produced; not a defined output field.
- lambda=0 (0002, 0003): linear trades X/N used exactly (HR-5); lots from exact fractions, so 0003 ties (333.33 each) go to the earliest: [334,333,333].
- lambda>0 (0001): lots by largest remainder on the float trades as profile weights; no tie arises. E and V by direct sums eq (8), (5) (not eq 20 closed form). V sums x_1..x_N (x_N=0).
- E includes 1/2 gamma X^2 + epsilon X + (eta_tilde/tau) sum n^2, eta_tilde = eta - gamma tau/2.
- "fees" is the TCA fees argument = fee_per_unit*filled, added to total.
- total_bps = total/(quantity*decision_price)*1e4 with order_quantity = quantity (not filled).
- SELL: s=-1; delay/execution/opportunity signed as tca spec; positive = hurts.
- Case 0001 completed_steps=5: opportunity exactly 0. Case 0002 completed 3 of 5 gives opportunity 200000.
- Spec says "trades" before rounding sum to quantity; float trades normalised by their own sum in the largest-remainder step.
