# SOURCES

Run as: Sonnet 5.5 (model id claude-sonnet-5-5). Date opened: 2026-11-12. No network access used; nothing outside `C:\Work\Claude\qf-rederive` and the Basel PDF was read.

Primary PDF: `C:\Work\Claude\institutional-quant-engine-plan\basel-framework-full.pdf` (1,429 pages, printed 11/11/2026). Text extracted with pdftotext; every formula that is an image was read by rendering the page to PNG (pages 570-574, 594, 599, 608, 614, 615). Page numbers below are the PDF page numbers (footer "n / 1429").

## 1. CDS index option (54 cases) - basis `own-knowledge-of-paper`
- Pedersen (2003), "Valuation of Portfolio Credit Default Swaptions": NOT opened (not fetched; no web access attempted). The default-adjusted forward (F + front-end protection / annuity), the strike adjusted for the coupon (K_adj = C + (K - C) A_K P(expiry) / A, with A_K the annuity of a flat curve whose spread equals K) and Black on the pair were written from my own knowledge of the paper and checked by the first-principles derivation (payer exercise value = protection - C*annuity + loss on defaulted names - upfront; value today = A(F_adj - K_adj)). Put-call parity holds by construction.
- Spec-only parts (conventions, not in any primary source): quarterly leg dates from expiry, ACT/365 times, ACT/360 accruals, accrual-on-default mid date, as-of survival included in A, the root solve for h_K measured from expiry. These come from `specs/credit-options-and-copulas.md`. As a convention check only: the single-name worked example in that page (forward 1.18877%, annuity 4.32865, front-end protection 43,333.06 at as_of 2026-11-06) is reproduced by my legs.
- Standard-library plus scipy `brentq` (xtol 1e-17).

## 2. FRTB SA (43 cases) - basis `primary-text`
Basel Framework MAR21 (pp. 567-618):
- Delta/vega aggregation: MAR21.4 (p. 570-571, formulas as images): K_b with floor at zero, S_b, across-bucket formula, alternative S_b = max(min(sum WS, K_b), -K_b) when the sum is negative.
- Curvature: MAR21.5 (pp. 571-573): CVR formulas, K_b^+ and K_b^- with max(CVR,0)^2 and psi, selection rule incl. tie (iii), S_b, psi(S_b,S_c), across-bucket sqrt(max(0, ...)).
- Scenarios: MAR21.6 (p. 574): high = min(1.25 x, 100%), low = max(2x - 100%, 75% x). MAR21.7 not needed (class level only).
- GIRR: MAR21.41-21.50 (pp. 592-594): Table 1 risk weights, MAR21.43 (1.6% inflation, basis), MAR21.44 and footnote 283 (divide by sqrt 2), MAR21.45, Table 2 (p. 593; the formula exp(-3% |Tk-Tl|/min) floored at 40%, footnote 284 text lost in extraction, was verified cell by cell against Table 2 in code), MAR21.47, FAQ to 21.47/21.48, MAR21.48, MAR21.49, MAR21.50.
- CSR non-sec: MAR21.51-21.57 (pp. 594-599): Tables 3, 4, 5 (Table 5 read from the page image), 21.54, 21.55, 21.56 (bucket 16 sums), 21.57.
- Equity: MAR21.72-21.80 (pp. 605-609): Tables 9, 10 (spot and repo), 21.78, 21.79, 21.80.
- Commodity: MAR21.81-21.85 (pp. 609-613): Tables 11, 12, 21.83, 21.85.
- FX: MAR21.86-21.89 (p. 613): 15%, sqrt 2 for specified pairs (footnote 293 list, 294 first-order crosses), 60%.
- Vega: MAR21.90-21.95 (pp. 613-616): Table 13, footnote 295, 21.93 (GIRR), 21.94 and its FAQ (delta correlation along the name dimension only for CSR and commodities), 21.95.
- Curvature parameters: MAR21.96-21.101 (pp. 616-618): shock sizes not needed (CVRs are inputs); FX scalar 1.5 (21.98); squared delta correlations (21.100, 21.101); other-sector formula (21.56(2), 21.79(2), pp. 599, 609).
- Not opened / not used: MAR21.15-21.38 (sensitivity definitions), MAR22, MAR23.
- Not in MAR21 (conventions taken from the spec page for field meanings only): the `binding_scenario` tie rule (first of high, medium, low); output field names (`buckets`: `bucket`, `currency` for GIRR, `k`, `s`, `s_used`, `selected`); sorting of buckets (string length, then text).

## 3. Traffic light (20 cases) - basis `primary-text`
- MAR32.8-32.9 and Table 1 (pp. 660-661): zones and "backtesting dependent multiplier" 1.50 (0-4 exceptions), 1.70, 1.76, 1.83, 1.88, 1.92 (5-9), 2.00 (10 or more).
- MAR99.9-99.21 and Tables 1, 2 (pp. 755-759): amber begins where P(X <= x) >= 95%, red where >= 99.99%, binomial with coverage 99%, boundaries for other sample sizes deduced from the binomial. My cumulative probabilities match Table 2 (8.11%, 28.58%, 54.32%, 75.81%, 89.22%, 95.88%, 98.63%, 99.60%, 99.89%, 99.97%, 99.99%).
- MAR33.42 (pp. 684-685): multiplier m_c fixed at 1.5, plus factor 0 to 0.5. So plus_factor = multiplier - 1.5.
- The 1996 supervisory text itself is not a separate document in the PDF; MAR99 carries it.
- For n != 250 or confidence != 99% the PDF gives no multiplier table, so `plus_factor` is null (zone and probability still derived by the stated binomial rule; for 97.5% the zone rule is an extension, the PDF defines zones for 99% only).

## 4. Book lifecycle and marks (23 cases) - basis `spec-only`
Independent implementation from `specs/book-lifecycle.md` by a different model; no primary source exists. Exact rational arithmetic (Fraction of the JSON decimal text), converted to float at the end.

## Spec versus primary: findings
1. **Plus factor (traffic light).** Spec page: 0 for 0-4, then 0.40, 0.50, 0.65, 0.75, 0.85 for 5-9, 1.00 from 10 (1996 table, multiplier base 3.0). Primary (MAR32.9 Table 1 with MAR33.42, pp. 661, 684): multipliers 1.70, 1.76, 1.83, 1.88, 1.92, 2.00 on a base of 1.5, i.e. plus factors 0.20, 0.26, 0.33, 0.38, 0.42, 0.50. I report the primary values in `plus_factor`, and the spec-page values in the extra field `spec_page_reading_plus_factor_NOT_FROM_PRIMARY`. The spec zones (green 0-4, yellow 5-9, red 10+) agree with the primary at 250 and 99%.
2. **Vega risk weight, equity large cap and indices.** Table 13 prints 77.78%; footnote 295 (min(55% sqrt(LH/10), 100%)) gives 77.7817%. Primary text contains both. I use the printed 77.78% in `vega` and give the footnote value in `alt_capital_unrounded_vega_rw` for frtb_f2c-0002 (667,084.88 vs 667,079.05). The spec page uses the printed value too (no disagreement, but the primary is internally ambiguous).
3. **Binding-scenario tie rule** and the statement of the class-only maximum: not in MAR21 (MAR21.7 takes the maximum over scenarios of the sum across classes). Convention taken from the spec.
4. **Specified-currency reduction (MAR21.44):** "the above risk weights" could cover inflation and basis weights; I divide all GIRR weights of a specified currency. No case has inflation or basis with the reduction on.
5. **FX specified_pairs:** MAR21.88 names the Basel pairs and first-order crosses; I additionally require each listed pair to be eligible (all case pairs are). The spec says "pairs the bank elects".
6. No numeric disagreement was found in any other FRTB parameter (risk weights, correlation tables, Table 5, equity, commodity, scalars). Note: before the tightened brief I had read parts of the FRTB and traffic-light spec pages; every number used in `results.json` was then taken from, and checked against, the PDF.
7. **CDS:** the spec says the Pedersen worked example is not reproduced; I did not open the paper either.
