# Data availability

Per plan section 8. A row that cannot run on real data is a method test on labelled synthetic data. "Reachable" means the site answered on 2026-11-06. No licence terms were read for this table and no data was downloaded, so the "expected result" column is a judgement to verify. Each source's terms must be read and recorded in a manifest before use. US Treasury did not answer the first check on 2026-11-06, but the recorder fetched it later that day.

| Backtest | Data needed | Likely free source | Reachable | Expected result |
|---|---|---|---|---|
| Sovereign curve rebuilds | Yields | Bank of England, ECB, US Treasury | Yes | Fitted curves only. Rebuilding a central bank's fitted curve is circular, so use it for interpolation tests, not curve validation |
| Interpolation leave-one-out | Published curve nodes | As above | As above | Can run |
| OIS and swap curves | OIS and swap quotes | None confirmed | n/a | Method test |
| Gilt RV, bond fits | Bond-level history | UK DMO | Yes | Partial at best |
| FX forwards, hedging | Spot, forward points | ECB and FRED for spot | Yes | Spot can run; forwards are a method test |
| Cross-currency basis | Basis quotes | None known | n/a | Method test |
| Vol surface, Greeks and hedging | Option surface history | None known | n/a | Method test |
| FX vol, swaptions | Vol quotes | None known | n/a | Method test |
| Inflation | Index levels; swaps | FRED for indices; none for swaps | Yes | Indices can run; swaps are a method test |
| Credit, CDS | Spreads | None known | n/a | Method test |
| Equity borrow, dividends | Borrow, dividend history | None known | n/a | Method test |
| VaR, ES | Daily returns | FRED series | Yes | Can run on those series |
| Order books, execution | Book and trade data | None; no Nasdaq or LOBSTER | n/a | Simulated only |
| Paper trading | Free live equity data | To find in stage K | n/a | Open |

A 250-day record cannot exist inside the build, so v1.0 verdicts stay "conditionally approved".
