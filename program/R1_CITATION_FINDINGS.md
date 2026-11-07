# R1 citation backfill: findings

Branch `r1-cite`, phase R1 (v0.4.1). Work list: section 3 of `R5_STAGE_D_AUDIT.md`. Plan 11.2.4 and 11.5 require primary-source citations in every spec.

## What changed

A `## Sources` section is appended to 50 specs in `specifications/01-core` to `08-hedging`. Nothing else changed: no normative text, number or golden. No spec used inline `[S1]` markers before, so none were added in the text; the list items carry `[S1]` labels so later edits can point at them.

Every reference was checked from memory and is marked "(not opened)". Section numbers are given only where known (ISDA 2006 s.4.12 and s.4.16, RFC 8259 s.9, ICMA Rule 251, 31 CFR 356 Appendix B, SIFMA Uniform Practices chapter SF, ISDA Supplement 70). Textbooks are cited by edition and chapter title, not chapter number, where the number was not certain. A later pass that opens the documents should drop "(not opened)" item by item.

Not touched, as they are not specs of a convention: `README.md` files, `rulings.md`, `clean-room-followups.md`, the `stage-*-targets.md`, `stage-*-rulings.md`, `stage-*-handover.md`, `stage-b-followups.md` and `cli-contract.md`.

## Specs that may disagree with a source

Reported to the coordinator, not fixed here. Status as of r1 at 1d6e585.

| # | Spec | Point | Source | Note |
|---|---|---|---|---|
| F1 (resolved by R1-3, `specifications/r1-rulings.md`) | `04-pricing/bonds.md`, `bond.futures.conversion_factor` | Months to maturity are always rounded down to a multiple of 3 | CME Group, *Calculating U.S. Treasury Futures Conversion Factors* (not opened) | From memory, CME rounds to the quarter for the bond, Ultra bond and 10-year note contracts, but to the whole month for the 2-, 3- and 5-year note contracts (with `v = z - 6` when `z >= 7`). The spec is right for the long contracts but does not say it excludes the short ones. Suggest a scope sentence, or an input naming the contract. To confirm against the CME document. |

No other disagreement was seen. Checked in passing, from memory, and consistent: TIPS reference CPI (31 CFR 356 App. B), PSA ramp and SMM (SIFMA SF), ISDA 2020 fallback (2-day observation shift, spread fixed 5 March 2021), CDS standard-model dates (step-in T+1, cash settlement T+3, 20th roll dates), CBOT conversion-factor formula itself, ARRC lockout.

## Summary table

| Spec | Families | Sources added |
|---|---|---|
| 01-core/asof-store | bitemporal store, hash | Snodgrass; FIPS 180-4; RFC 8259 |
| 01-core/calendars | Easter, holidays, business days | Meeus; UK BFDA 1971; ECB TARGET; SIFMA; ISDA 2006 s.4.12 |
| 01-core/compounding | compounding | Hull |
| 01-core/conventions | registry | ISDA 2006 s.4.12, s.4.16; BoE, NY Fed, ECB |
| 01-core/cos | Fourier pricing | Fang-Oosterlee 2008; Heston 1993 |
| 01-core/data-checks | robust outliers | Rousseeuw-Croux 1993; Hampel 1974 |
| 01-core/daycount | day counts | ISDA 2006 s.4.16; ICMA Rule 251; ISDA 1998 ACT/ACT note; AFB |
| 01-core/differentiation-and-linalg | FD, LU, Cholesky, eigen | Numerical Recipes 3rd ed.; Golub-Van Loan |
| 01-core/integration | quadrature | Numerical Recipes; QUADPACK; Lyness 1969 |
| 01-core/interpolation | curve interpolation | Hagan-West 2006, 2008; Fritsch-Butland 1984 |
| 01-core/limits | input limits | RFC 8259 s.9 |
| 01-core/monte-carlo | MC, GBM | Glasserman; Black-Scholes |
| 01-core/pde | finite differences | Crank-Nicolson 1947; Rannacher 1984; Tavella-Randall |
| 01-core/rng | PRNG, normals | SplitMix (Steele et al.); xoshiro (Blackman-Vigna); AS 241; Glasserman |
| 01-core/root-finders | roots | Brent 1973 ch.4; Numerical Recipes |
| 01-core/snapshot-hash | canonical JSON, SHA-256 | FIPS 180-4; RFC 8259; RFC 8785 (related only) |
| 01-core/sobol | QMC | Sobol 1967; Joe-Kuo 2008; Glasserman |
| 01-core/statistics-and-time-series | stats, EWMA, Ljung-Box | Numerical Recipes; Ljung-Box 1978; RiskMetrics 1996; Hyndman-Fan; ISO 8601 |
| 01-core/test-functions | registry | Numerical Recipes; Black-Scholes |
| 01-core/timezone-and-cutoff | time zones | IANA tzdb; ISO 8601 |
| 01-core/units-and-money | units, currency | ISO 4217 |
| 02-curves/commodity | carry, seasonality | Hull; Geman |
| 02-curves/cross-currency | xccy basis, NDF | Fujii-Shimada-Takahashi; Andersen-Piterbarg; Hull; NY Fed; ECB |
| 02-curves/csa-and-basis | CSA discounting | Piterbarg 2010; Fujii et al.; ISDA 2016 VM CSA |
| 02-curves/curve-framework | curves | Hull; Hagan-West |
| 02-curves/equity-curves | dividends, borrow | Hull; Eurex/CME dividend futures |
| 02-curves/equity-forward | equity forward | Hull |
| 02-curves/futures-convexity | HW convexity | Hull; Brigo-Mercurio ch.3; Kirikos-Novak 1997 |
| 02-curves/fx | FX spot and forwards | Clark 2011; 1998 FX Definitions |
| 02-curves/inflation | CPI, linkers | 31 CFR 356 App. B; UK DMO; Kerkhof 2005; Brigo-Mercurio |
| 02-curves/meeting-steps | step curves | FOMC/MPC/ECB calendars; Andersen-Piterbarg |
| 02-curves/ois-curves | OIS | BoE; NY Fed; ECB; ISDA 2021; Ametrano-Bianchetti |
| 02-curves/overnight-compounding | lookback, shift, lockout, fallbacks | ISDA 2021; ARRC; ISDA Supplement 70 and Bloomberg rule book; BoE; NY Fed; ECB |
| 02-curves/projection-and-fra | FRA, swaps, basis | ISDA 2006 s.4.16; Hull; Ametrano-Bianchetti |
| 02-curves/schedules | schedules | ISDA 2006 s.4.12 |
| 03-calibration/curve-fits | smoothing, Huber NS | Nelson-Siegel 1987; Huber 1964; Fisher-Nychka-Zervos 1995; BoE (Anderson-Sleath 2001) |
| 03-calibration/least-squares | GN, LM, BFGS | Nocedal-Wright 2nd ed.; Marquardt 1963; Nelson-Siegel |
| 04-pricing/bonds | yields, repo, futures | ICMA Rule 251; UK DMO; CME conversion factors; Fabozzi; Burghardt; O'Kane asset swaps; Nelson-Siegel |
| 04-pricing/credit | ISDA CDS | ISDA CDS Standard Model; 2014 Credit Definitions; O'Kane 2008; 2015 roll change |
| 04-pricing/equity-index | index, TRS | S&P DJI Index Mathematics; Eurex dividend futures; Hull |
| 04-pricing/mbs | PSA, pass-through | SIFMA Uniform Practices ch. SF; Fabozzi MBS handbook |
| 04-pricing/pricing-framework | valuation record | internal contract; RFC 8259 |
| 04-pricing/use-cases | hedging | Hull |
| 05-volatility/black-models | Black, Bachelier | Black-Scholes 1973; Black 1976; Bachelier 1900; Hull |
| 05-volatility/caps-and-swaptions | caps, swaptions | Hull; Brigo-Mercurio ch.1; Black 1976; Bachelier |
| 05-volatility/sabr | SABR | Hagan et al. 2002, 2014; Breeden-Litzenberger 1978 |
| 05-volatility/smile-and-surface | SVI, SSVI, delta | Gatheral 2006; Gatheral-Jacquier 2014; Clark; Reiswich-Wystup |
| 06-risk/rates-sensitivities | DV01 | Hull; Andersen-Piterbarg |
| 06-risk/vol-greeks | Greeks | Hull; Black-Scholes; Black; Bachelier |
| 08-hedging/stage-b-hedges | weighted LS hedge | Numerical Recipes ch.15; Hull |

## Follow-up after R1-3 and R1-4

F1 is closed: ruling R1-3 adds the `contract` input (whole months for 2Y, 3Y, 5Y; quarters otherwise) and withdraws the half-even rounding claim. Sources added after the merge of r1: the CME conversion-factor document marked as the basis of R1-3 (`bonds.md` S3); TP ICAP's EUR OIS term sheet and Strata 2.12.78 for the `ESTR` payment lag (`conventions.md` S5, S6); the ISDA CDS Standard Model flat-forward assumption behind R1-4 (`credit.md` S5). All marked "(not opened)".

## R2: opening the public sources (2026-11-07)

Branch `r2-cite` from main `eaf6933`. Each public source was fetched once and the result applied to every spec that cites it. Only citation lines changed.

| Result | Sources | Count |
|---|---|---|
| Opened, confirms | RFC 8259 (s.9 confirmed), RFC 8785, IANA tzdb, Joe-Kuo direction numbers page, SIFMA holiday schedule, UK BFDA 1971 Sch. 1, BoE SONIA key features, NY Fed reference-rate methodology page (title corrected), ECB €STR methodology (title corrected), CDS semi-annual roll note (wording corrected) | 10 |
| Opened, partial | prng.di.unimi.it (code and SplitMix seeding; paper details not shown), cdsmodel.com (free source; step-in, settlement and flat-forward not found there) | 2 |
| Contradicts a spec | none | 0 |
| Not reachable | CME conversion factors (timeout), ARRC loan conventions (PDF not decodable), Bloomberg fallback rule book (signed redirect), eCFR 31 CFR 356 App. B (bot redirect), UK DMO formulae (404 and bot check), TP ICAP (TLS error), ECB TARGET closing days (404), SIFMA Uniform Practices ch. SF, S&P DJI Index Mathematics (403), Eurex FEXD, FIPS 180-4 (PDF not decodable), BoE WP 126, FEDS 95-1, SSRN 2219548, Strata 2.12.78 ESTR convention file, Fujii et al. | 16 |
| Licensed, left "(not opened)" | ISDA 2006 and 2021 Definitions, Supplement 70, 2014 Credit Definitions, 2016 VM CSA, 1998 FX Definitions, ICMA Rule 251, ISO 4217 and 8601, all textbooks and journal papers | the rest |

Corrections to citations (not to specs):

- R2-C1, CDS roll (`credit.md`): the change took effect on 21 December 2015. The roll dates are 20 March and 20 September; maturities fall on 20 June and 20 December. The old citation wording blurred the two. The spec's rule agrees with the source.
- R2-C2, ARRC (`overnight-compounding.md`): the linked loan-conventions PDF sits under a `2020` folder, while the citation says 2019. Not resolved, as the PDF could not be read.
- R2-C3, UK holidays (`calendars.md`): BFDA Schedule 1 gives Easter Monday, the May and August Mondays and the 26/27 December rule. Good Friday, Christmas Day and 1 January come from common law and proclamation, which the citation already names.

Human-confirmation items: everything still marked "(not opened)", first the 16 unreachable public sources, which a browser with a person at it can likely open (CME, eCFR, DMO, ARRC and TP ICAP above all).
