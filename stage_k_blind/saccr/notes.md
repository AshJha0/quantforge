# SA-CCR blind lane notes (saccr_k-0006 to 0016)

Packet (hashes in packet_MANIFEST.sha256): stripped sa-ccr.md (Expected/Derivation/Check columns removed; sections Worked example, Goldens, Acceptance removed), sa-ccr-parameters.json, stage-k-rulings-w1b.md, saccr.inputs.json (inputs only of the 11 cases). Built by program/stage_h_blind_w2/saccr_blind_packet.py. Reference: blind_ref.py, plain Python, binary64, math.erf for the normal CDF.

## Leaks (process, stated plainly)
The lane read the UNSTRIPPED sa-ccr.md once, before the packet was built. What that exposed, per case:
- 0006: the Worked example gives the Example 1 intermediates (D values, EN 59,270 with offset); 0006 is the same trades without offset. NOT BLIND.
- 0015: the Acceptance text says "capped margined EAD" (names the output flag `capped`). NOT BLIND on `capped`; counted as not blind for the case.
- 0016: the Acceptance text says "exactly offsetting FX (multiplier 0.05)". Names the output `multiplier`. NOT BLIND.
- 0013: Acceptance text says "(MPOR 40)", an output `mpor_days`. NOT BLIND on that field; case counted not blind.
- 0014: "own MPOR estimate 15" is an input, no leak.
- 0007 to 0012: descriptions give trade structure only (inputs). No leak.
The lane did not open the golden file beyond case_id and inputs, nor any implementation, test or generator.

## Ambiguities and assumptions
1. MF for an option: used the `maturity` field (M_i), not `exercise`. Step 2 says M_i; ruling silent. Matters for 0007 (f3 maturity 1, exercise 0.75), 0008 (e3 maturity 2, exercise 0.5), 0012.
2. Supervisory duration only for IR and CREDIT; SD uses start and end; the floor 10/250 applies to SD and to M.
3. Output `supervisory_factor` per trade: the scaled factor (x0.5 basis, x5 volatility), as step 5 defines SF_i.
4. Per-trade margined fields: when margined, `maturity_factor` is the margined MF (1.5 sqrt(MPOR/250)); the unmargined figures are not output per trade. Per-trade fields are therefore comparable only on the stated names and the margined values.
5. Commodity NORMAL hedging-set key: ENERGY, METALS, AGRICULTURAL, OTHER (the KR-33 derived set). Credit and equity NORMAL key "".
6. Credit single-factor: rho per entity from its subclass row; entities of mixed subclasses in one set aggregate with their own rho.
7. Commodity basis set (0010 p4): a single entity in its own set; add-on = |a| (the single-factor formula collapses). KR-34 says internal aggregation is not stated; for one entity it does not matter.
8. MPOR: floor 10 if remargin_days = 1 else 9 + remargin_days; illiquid (or > 5000 trades) lifts the floor to at least 20; disputes doubles the floor (after the lift; order of lift and doubling gives 40 either way for 0013); MPOR = max(floor, estimate).
9. Margined multiplier uses the margined aggregate add-on and V - C; unmargined EAD for the cap uses the unmargined add-on.
10. `rc` for margined is max(V-C, TH+MTA-NICA, 0); `pfe` = multiplier x aggregate add-on.
11. Delta of a linear trade: LONG +1, SHORT -1 for every class (including credit).
12. Zero add-on with V - C < 0: multiplier 0.05 (stated in step 7).
