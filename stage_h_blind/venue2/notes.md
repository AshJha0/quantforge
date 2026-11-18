# Blind notes (venue_h)
- 0004: horizons empty -> fill_rates only, markouts [].
- 0005/0008: "with order (A,500,600)" read as replacing A's order; adding instead gives the same E_INPUT. 0005 has empty horizons (error regardless). 0008: filled>sent E_INPUT precedes h<0 E_DOMAIN (HR-66/75).
- 0006: fill at t=-1 has no mid at or before -1 -> E_INPUT (value-dependent, after domain checks; none apply).
- 0007: h=-1 -> E_DOMAIN.
- 0009: the F-2 non-finite case has no input in the packet; not computed, absent from results.
- Output h emitted as float (e.g. 5.0); success outputs carry no status field. Mid lookup uses t+h exact; mids at equal time n/a.
- 0010: toxic share = 1e20/(2e20+1e-20) exact, rounded once.
