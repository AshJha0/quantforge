# Notes (blind lane, trig_k v2)

MANIFEST.sha256 check: all 5 files matched (sha256sum -c OK). Read only the packet folder and this folder.

Files read: README.md, MANIFEST.sha256, output_template.json, inputs/K-4c.inputs.json,
rulings/stage-k-rulings-trig.blind.md (KR-6, KR-13, KR-232, KR-233), specs/recalibration-triggers.blind.md.

Assumptions / ambiguities
1. threshold = k*sigma*sqrt(d), evaluated left to right as (k*sigma)*sqrt(d). Spec gives no order. Affects every case's threshold and the equality-sensitive fire decisions (0004 at x_now=2.5 vs threshold 2.5 exactly: not strictly greater, no fire; 0005 fires).  fire = abs(x_now - x_ref) > threshold on binary64 values (KR-13).
2. sigma (KR-233): mean = fsum(c)/n; S2 = fsum((c-mean)*(c-mean)); sigma = sqrt(S2/(n-1)). Noise-scale check sigma <= 2^-26*max|c| would be E_DOMAIN; case 0021 (sigma 1.5556e-8 vs 2^-26 = 1.4901e-8) passes, so it is a value case. No other case near the limit.
3. false_alarm_rate (KR-232): implemented as written. Ambiguities: (a) in the remainder loop I test the stop condition (t <= R*2^-60) first, then the 2^-500 rescale (the text lists stop first); (b) the scale test in the first loop is "0 < t < 2^-500" as written; (c) nu = n-1 integer, odd/even branch by parity; (d) final multiply by 2^-500 applied e times, one multiplication each. Affects all cases with A < 0.125: 0009 (k=30, nu=3), 0014 (nu=299? long window), 0016 (k=1000, nu=7), 0013, 0001/0003 etc. only if A<0.125; the remainder branch is taken whenever the complement is < 0.125.
   Sanity check: nu=1,k=3 gives 0.20483276469913345-ish (0.2048327646991334 exact 2*(0.5-atan(3)/pi)); matches 0010/0021.
4. nominal_rate = 2*Phi(-k): own implementation, not math.erfc, because k/sqrt2 rounding loses relative precision in the tail. Used 700-digit Decimal arithmetic: for k<10 the Taylor series of erf(k/sqrt2) with 1-erf (precision large enough that cancellation is harmless); for k>=10 phi(k)*Mills-ratio continued fraction (3000 terms) with Decimal exp, then float(Decimal) (correct rounding). k=1000 gives 0.0 (true value ~1e-217000 underflows binary64) - assumed correct to report 0.0 rather than an error (0016). Values differ from math.erfc(k/sqrt2) by 1e-15 relative at k=3, 1.2e-13 at k=30 (as the spec warns).
5. Output keys exactly as template; fire as JSON boolean; floats written with json.dump (repr, shortest round-trip, full binary64).
