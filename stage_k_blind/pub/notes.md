# Notes (blind derivation)

Packet MANIFEST.sha256 checked with sha256sum -c: all 9 files matched.
Method: Python stdlib only (`blind_ref.py`). Binomial sums exact with `fractions.Fraction`, converted to float once at the end; zone comparisons done on exact fractions. Normal cdf = 0.5*math.erfc(-x/sqrt(2)). No rounding anywhere. Real inputs used as given.

## Recognised cases
saccr_k-0001..0005 (trade ids, notionals, entities, mixed IR/credit/commodity netting sets) look like the regulator's published SA-CCR worked examples; btk_k-0001..0012 and tlk_k-0001..0011 look like the published 250-observation traffic-light table. Nothing was checked against any remembered figure; all values come from the rules.

## Ambiguities and assumptions
1. Margined trade rows (saccr_k-0005; sa-ccr spec Outputs, "the margined figures when margined"): the template names only 7 trade fields, so I report those 7 with the margined maturity factor (1.5*sqrt(MPOR/250)) and margined effective notional. No extra unmargined per-trade fields are given. Also top-level rc, pfe, multiplier, addon_aggregate, addon, hedging_sets in case 5 are the margined figures; ead_unmargined holds the unmargined EAD.
2. Case 5 MPOR (KR-35): remargin_days 5 -> floor 9+5 = 14; 6 trades (not >5000), illiquid/disputes absent -> 14; no estimate. mpor_days = 14.
3. Case 5 margined RC: max(V-C, TH+MTA-NICA, 0) = max(-120, -145, 0) = 0. Cap did not bind (capped false).
4. Case 5 multiplier uses V-C = -120 and the margined add-on (the margined add-on scales every trade's MF).
5. Commodity hedging-set key (cases 3, 5): the Table 2 "hedging_set" label uppercase as in the table: ENERGY, METALS (spec does not fix the key text for commodity; KR-33). Credit/equity NORMAL key is "" per spec. IR key = caller's hedging_set (currency).
6. Commodity correlation 0.4 for single-factor aggregation (from table and spec step 6). Credit correlation per entity from the entity's subclass (AA 0.5, BBB 0.5, IG 0.8; saccr_k-0002, 0004); rho_e taken per entity.
7. IR bucket by end date E (KR-32): trade 3 has E=11 -> bucket 3; trade 2 E=4 -> bucket 2; trade 1 E=10 -> bucket 3. SD uses start/end (trade 3 start 1, end 11), not exercise.
8. IR option (saccr_k-0001, 0004, 0005, trade 3): bought put, delta = -Phi(-d1), sigma 0.50 (IR row), T=exercise=1, no shift. Maturity factor uses `maturity` 11 -> capped at 1 unmargined.
9. Trade `supervisory_factor` reported with the treatment scale applied (all NORMAL here so unscaled).
10. `capped` false and `ead_unmargined`/`mpor_days` null for unmargined cases; margined false.
11. Traffic light: confidence 0.99 converted exactly as decimal 99/100 (via repr), so p = 1/100 exactly (not 1 - binary64 0.99). Plus factor from the spec table for x 0..9 and 1.00 for x>=10 at n=250, c=0.99.
12. FRTB zone: multiplier from table for exceptions 0..9, 2.00 for >=10 at n=250 (table JSON gives 10 entries). amber_from and red_from computed from the binomial rule, not looked up.
13. No field was marked not derivable.

## Hand checks (done on the output)
- saccr_k-0003 trade 7: 10000*sqrt(0.75)=8660.254; ENERGY add-on 0.18*|8660.254-20000|=2041.154; METALS 1800; total 3841.154; EAD=1.4*(20+3841.154)=5405.616. Matches.
- saccr_k-0005: MF=1.5*sqrt(14/250)=0.35496; metals add-on 0.18*10000*0.35496=638.94; multiplier 0.05+0.95*exp(-120/(1.9*1400.96)) = 0.9581. Matches.
- btk_k-0006 (x=5): cdf(250,0.01) at 5 = 0.95882 >= 0.95 with cdf(4) < 0.95, so amber_from 5; red_from 10; multiplier 1.70. Consistent with computed values.
