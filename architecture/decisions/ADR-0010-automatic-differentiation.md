# ADR: Automatic differentiation

## Status
Accepted for stage B. Stage F may revisit how AD is built, not whether.

## Decision
Stage B has no AD. Sensitivities come from bump and full recalculation, using central differences where cost allows. The plan puts "AD for named products" in stage F.

In stage F each language writes its own small reverse-mode tape for the named products. There are no shared tapes and no generated derivative code across languages. A tape is a general numerical tool, so a proven per-language library is allowed by plan rule 4 if one fits.

Bumped results stay as the check on AD: the two must agree within a per-product target.

## Consequences
Stage B curve code need not be generic over a number type, but calculations must stay pure functions of their inputs so that a tape can be added. Curve Jacobians in stage B use bumps.
