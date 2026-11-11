# Stage E primary sources

Checked 2026-11-08 by the citations session. Spec sessions cite from this file (plan section 11.2.4). This file names the sources only: it does not quote them, and nothing from paywalled text was read.

## Status words

- **Read**: the text was opened and the section or equation numbers below were taken from it.
- **Bib checked**: authors, title, journal, volume, pages and DOI were confirmed from the DOI's Crossref record or a catalogue. The text itself was not read, so any equation numbers are marked *unverified*.
- **Not opened**: the citation is the usual one, given from memory. Confirm it before relying on it.
- **Licensed: needs human confirmation**: the text is paywalled or licensed. A person with access must confirm the section or equation numbers before a spec relies on them. Where one exists, a free stand-in is named.

## Volatility surface

| Model | Source | Cite | Status |
|---|---|---|---|
| SVI raw | Gatheral, J. (2004), "A parsimonious arbitrage-free implied volatility parameterization with application to the valuation of volatility derivatives", Global Derivatives & Risk Management, Madrid (slides) | Original raw form only. For equations, cite Gatheral-Jacquier below | Not opened |
| SVI, SSVI, no-arbitrage | Gatheral, J. & Jacquier, A. (2014), "Arbitrage-free SVI volatility surfaces", *Quantitative Finance* 14(1):59-71, doi:10.1080/14697688.2013.819986; arXiv:1204.0646 (free) | Numbering is from the arXiv version (v4, 21 Mar 2013, the latest on arXiv; checked 2026-11-11). Butterfly function g(k) eq. (2.1); no-butterfly condition Lemma 2.2; calendar condition Lemma 2.1 / Def. 2.2; raw SVI eq. (3.1); natural SVI eq. (3.2); raw-natural map Lemma 3.1 / eq. (3.3); SVI-JW §3.3, Lemma 3.2; SSVI eq. (4.1); ATM skew eq. (4.2); calendar no-arbitrage Thm 4.1; butterfly sufficient conditions Thm 4.2 (nearly necessary, Lemma 4.2); static no-arbitrage Cor. 4.1; calibration §5 | Read (arXiv). Journal numbering licensed: needs human confirmation |
| Local vol | Dupire, B. (1994), "Pricing with a smile", *Risk* 7(1):18-20 | Local-vol formula. The article has no equation numbers. Free stand-in: Gatheral (2006), *The Volatility Surface*, Wiley, ch. 1 (also licensed) | Not opened; licensed: needs human confirmation |

## Stochastic vol, jumps, Fourier pricing

| Model | Source | Cite | Status |
|---|---|---|---|
| Heston | Heston, S.L. (1993), "A closed-form solution for options with stochastic volatility with applications to bond and currency options", *Review of Financial Studies* 6(2):327-343, doi:10.1093/rfs/6.2.327 | Price eq. (10), characteristic function eq. (17), P_j eq. (18) (*unverified*). Branch cut: Albrecher et al. (2007), "The little Heston trap", *Wilmott* (not opened) | Bib checked; licensed: needs human confirmation |
| Bates | Bates, D.S. (1996), "Jumps and stochastic volatility: exchange rate processes implicit in Deutsche Mark options", *RFS* 9(1):69-107, doi:10.1093/rfs/9.1.69 | Heston plus lognormal jumps characteristic function (equation numbers *unverified*) | Bib checked; licensed: needs human confirmation |
| Merton jump-diffusion | Merton, R.C. (1976), "Option pricing when underlying stock returns are discontinuous", *Journal of Financial Economics* 3(1-2):125-144, doi:10.1016/0304-405X(76)90022-2 | Lognormal-jump series formula, eq. (19) (*unverified*). Free MIT working-paper version exists (not opened) | Bib checked; licensed: needs human confirmation |
| Lewis formula | Lewis, A.L. (2001), "A simple option formula for general jump-diffusion and other exponential Lévy processes", SSRN 282110, doi:10.2139/ssrn.282110 (free) | Single-integral call formula (equation number *unverified*) | Bib checked (RePEc; SSRN page refused the fetch). Free text, still to read |
| Carr-Madan FFT | Carr, P. & Madan, D. (1999), "Option valuation using the fast Fourier transform", *Journal of Computational Finance* 2(4):61-73, doi:10.21314/JCF.1999.043 | Damped call transform, eqs. (5)-(6) (*unverified*) | Bib checked; licensed: needs human confirmation |

Recommendation for the spec: use Lewis as the primary pricing method, because its text is free and anyone can check the formula. Use Carr-Madan for the FFT grid only.

## FX options

| Model | Source | Cite | Status |
|---|---|---|---|
| Garman-Kohlhagen | Garman, M.B. & Kohlhagen, S.W. (1983), "Foreign currency option values", *Journal of International Money and Finance* 2(3):231-237, doi:10.1016/S0261-5606(83)80001-1 | GK call and put | Bib checked; licensed: needs human confirmation |
| Delta conventions (licensed) | Clark, I.J. (2011), *Foreign Exchange Option Pricing: A Practitioner's Guide*, Wiley, ISBN 978-0-470-68368-2, doi:10.1002/9781119208679 (Crossref gives 2012-01-02; cite as 2011) | Delta and ATM conventions, ch. 3 (*unverified*) | Bib checked; licensed: needs human confirmation |
| Delta conventions (free, primary for specs) | Reiswich, D. & Wystup, U. (2009), "FX volatility smile construction", Frankfurt School CPQF Working Paper No. 20 (PDF revised 2010-09), econstor.eu/bitstream/10419/40186/1/613825101.pdf | Spot and forward setup §1.2; delta types §1.3: spot delta eqs. (5)-(6), forward delta (7)-(8), premium-adjusted spot (9)-(11), premium-adjusted forward (12)-(13) | Read |

## American, barrier, spread options

| Model | Source | Cite | Status |
|---|---|---|---|
| Barone-Adesi-Whaley | Barone-Adesi, G. & Whaley, R.E. (1987), "Efficient analytic approximation of American option values", *Journal of Finance* 42(2):301-320, doi:10.1111/j.1540-6261.1987.tb02569.x | Quadratic approximation and critical-price equation (numbers *unverified*) | Bib checked; licensed: needs human confirmation |
| Barriers | Reiner, E. & Rubinstein, M. (1991), "Breaking down the barriers", *Risk* 4(8):28-35 | Single-barrier closed forms. Stand-in: Haug (2007), *The Complete Guide to Option Pricing Formulas*, 2nd ed., McGraw-Hill, §4.17.1 (licensed, *unverified*) | Not opened; licensed: needs human confirmation |
| Kirk spread | Kirk, E. (1995), "Correlation in the energy markets", in *Managing Energy Price Risk*, Risk Publications / Enron, pp. 71-78 | Kirk approximation. Stand-in: Haug (2007), spread-option section (*unverified*) | Not opened; licensed: needs human confirmation |

## Correlation, GARCH

| Model | Source | Cite | Status |
|---|---|---|---|
| Nearest correlation matrix | Higham, N.J. (2002), "Computing the nearest correlation matrix: a problem from finance", *IMA Journal of Numerical Analysis* 22(3):329-343, doi:10.1093/imanum/22.3.329; free MIMS EPrint 232, eprints.maths.manchester.ac.uk/232/ | Alternating projections with Dykstra correction: Algorithm 3.3, §3 "Computation" (EPrint numbering) | Read (EPrint); journal bib checked |
| GARCH | Bollerslev, T. (1986), "Generalized autoregressive conditional heteroskedasticity", *Journal of Econometrics* 31(3):307-327, doi:10.1016/0304-4076(86)90063-1 | GARCH(p,q) definition (equation number *unverified*) | Bib checked; licensed: needs human confirmation |

## Volatility indices, variance swaps

| Model | Source | Cite | Status |
|---|---|---|---|
| VIX | Cboe Global Indices, *Cboe Volatility Index Mathematics Methodology*, v5.0, revised 26 Feb 2026, cdn.cboe.com/resources/indices/Cboe_Volatility_Index_Mathematics_Methodology.pdf (free) | Series selection §2 (bracket method, nearest term, bounded cubic spline for rates, BEY to continuous conversion); single-term variance formula (1), §3(a); time to expiry §3(a)(i); forward and K0 §3(a)(ii). This document replaces the old "VIX White Paper", so cite this one, not the white paper | Read |
| Variance swaps | Demeterfi, K., Derman, E., Kamal, M. & Zou, J. (1999), "A guide to volatility and variance swaps", *Journal of Derivatives* 6(4):9-32, doi:10.3905/jod.1999.319129. Free version: "More than you ever wanted to know about volatility swaps", Goldman Sachs Quantitative Strategies Research Notes, Mar 1999 | Log-contract replication and strip weights (numbers *unverified*) | Journal bib checked; Goldman note not opened. Read the free note before citing numbers |

## Credit portfolio and CDS options

| Model | Source | Cite | Status |
|---|---|---|---|
| Gaussian copula | Li, D.X. (2000), "On default correlation: a copula function approach", *Journal of Fixed Income* 9(4):43-54, doi:10.3905/jfi.2000.319253 (Crossref title lacks the subtitle). Free version: RiskMetrics WP 99-07 (not opened) | Survival-time copula construction | Bib checked; licensed: needs human confirmation |
| Vasicek large pool | Vasicek, O. (2002), "The distribution of loan portfolio value", *Risk* 15(12):160-162; earlier KMV note (1987), "Probability of loss on loan portfolio" | Large-pool limiting loss distribution | Not opened; licensed: needs human confirmation |
| CDS pricing | ISDA CDS Standard Model, cdsmodel.com. Source code and Excel add-in are a free download behind a disclaimer page; documentation and IBOR and RFR test grids are public. RFR curves are moving to rfr.spglobal.com (rfr.ihsmarkit.com was due to shut 2026-08-15) | Use the public documentation and test grids. The disclaimer was not read or accepted, so the code licence needs human confirmation before anyone reads the code | Home page opened |
| CDS index options | ISDA 2014 Credit Derivatives Definitions (licensed, ISDA bookstore); IHS Markit / S&P index option primers (client-only). Free academic stand-in: Pedersen, C. (2003), "Valuation of portfolio credit default swaptions", Lehman Brothers QCR (not opened) | No public ISDA spec for index swaption conventions was found | Licensed: needs human confirmation |

## QuantLib (oracle versions)

- QuantLib C++ **v1.44**, released 2026-10-13 (GitHub releases). The previous releases were v1.43 (2026-07-14) and v1.42.1 (2026-04-17). **Read.**
- QuantLib-Python (PyPI `QuantLib`) **1.44**, released 2026-10-13. **Read.**
- Class files (paths from memory, *not checked at 1.44*; the oracle session confirms them before pinning):
  - `ql/experimental/volatility/sviinterpolation.hpp`
  - `ql/pricingengines/vanilla/analytichestonengine.hpp`
  - `ql/pricingengines/vanilla/batesengine.hpp`
  - `ql/pricingengines/vanilla/baroneadesiwhaleyengine.hpp`
  - `ql/pricingengines/barrier/analyticbarrierengine.hpp`
  - `ql/pricingengines/basket/kirkengine.hpp` (may have been renamed)
  - `ql/pricingengines/vanilla/qdfpamericanengine.hpp`
  - `ql/pricingengines/vanilla/fdblackscholesvanillaengine.hpp`

## Open items for a person

1. Confirm the equation numbers in every row marked "licensed: needs human confirmation", above all Heston, Bates, BAW, Reiner-Rubinstein and Kirk, where the specs need formula-level citations.
2. Read the free Lewis (2001) and Goldman (1999) notes and fill in their equation numbers.
3. Decide whether to accept the cdsmodel.com disclaimer and read its code licence. The project does not accept terms for you.
