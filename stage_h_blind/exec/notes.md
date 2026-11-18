# Blind notes (exec lane)
Errors are emitted as {"error": CODE}. Field names I had to choose (spec gives none): pair/basket `cash_imbalance` has length N (buckets 1..N); `arrival` and `close` slices as named; close `auction_quantity`; attribution outputs delay, impact, spread, execution, opportunity, fees, total, total_bps; pretrade outputs as listed in spec (expected_cost/timing_risk only with price).
- 0003: UNITS cumulative floor(C+1/2) -> 601,400. 0004: float sinh noise ~2e-16 relative.
- 0005 kappa<0 E_DOMAIN; 0006 N=0 E_INPUT.
- 0008: remainder 0 -> zero slices, auction = X.
- 0009: UNITS, remainder 5002 over equal weights, tie -> earliest (1668,1667,1667).
- 0010 p_c>1 E_DOMAIN; 0011 zero profile with remainder E_DOMAIN.
- 0013: bucket 2 has no level inside L -> c=0, avg null; residual 700.
- 0014: SELL limit inclusive (>=), bucket 1 available 400, child 200 (all at 100.0).
- 0016 alpha=0 E_DOMAIN (checked before books); 0017 unordered E_INPUT.
- 0019: leg B UNITS cumulative of r*C^A, r=3/7; imbalance sign BUY positive.
- 0020 HEDGED: r = h. 0021 same side E_INPUT. 0022 h=0 E_DOMAIN (not E_INPUT).
- 0024: UNITS twap; imbalance bucket 1 = 2*10-1*30=-10.
- 0025 empty legs E_INPUT.
- tcx 0003 p=1 E_DOMAIN; 0004 b1>1 E_DOMAIN; 0005 X=0 E_INPUT (E_INPUT precedes E_DOMAIN checks).
- tcx 0010 Q>X E_INPUT; 0011 mid 0 E_DOMAIN. Attribution `fees` echoed in output (my choice).
- 0008 attribution: BUY, delay on executed Q.
