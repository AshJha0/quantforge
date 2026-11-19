# Daily paper ledger

Spec version 0.1.0 (stage K round 1, lane k-paper, 2026-11-19). Status: implemented in `tools/paper_daily/` on the Python CLI; workflow `.github/workflows/paper-ledger.yml`. **Not scheduled (2026-11-19).** The workflow's `schedule:` trigger is withheld until the different-model audit findings KA-C1, C2, C3, C9, C11 and C12 are closed (`docs/known-issues.md`); it can only be started by hand (`workflow_dispatch`). It has never run on a GitHub runner and 0 days are recorded. Rulings KR-70 to KR-89 (`stage-k-rulings-paper.md`, proposed; not normative until the stage K coordinator confirms them). Plan items: 14.8 K-1 (paper trading instruments), 14.8 K-2 (paper ledger), 12.7 Q8k (the paper ledger carries TCA per order), 14.10 rule 6 (dates checked against the prereg holdout windows). Builds on `10-execution/paper-trading.md` (H-21), `10-execution/tca.md`, `tca-pretrade.md` and `lit-matching.md`, all unchanged.

**Every row is labelled "paper marks on a fitted curve; not tradable"** (K-1 fallback, KR-70, KR-71). Fills are labelled "simulated", and the pre-trade cost estimate is labelled "placeholder weights" because its impact parameters are not calibrated. Every run prints the 11.6 sentence: "Paper trading on free data; simulated fills; no evidence of tradable profitability."

**This is plumbing evidence, not a strategy.** The trading rule is a fixed rotation that never looks at the market. No performance claim is made from this ledger, in this spec or anywhere else, and none may be made later from its P&L.

**Plain idea.** Each US business day a small job reads the Treasury par yield curve that the recorder has already written down, prices four made-up constant-maturity bonds on it, sends one order that a fixed timetable asks for, lets the venue simulator fill it against a made-up book, and writes one row that says what was held, what it was worth, what was traded, what the trade cost, and how the day's gain or loss splits into carry, roll-down, curve move and trading costs. Each row carries the hash of the row before it, and the latest hash is stamped outside the repository, so an old row cannot be changed quietly. Anyone holding only the ledger can recompute every day's P&L.

## Sources

| Ref | What | Evidence class |
|---|---|---|
| [FI-T] | TreasuryDirect "Website Terms & Conditions", `https://www.treasurydirect.gov/terms.htm`, section 2. Read 2026-11-19 through the web-fetch agent. It says material may be viewed, downloaded and printed "for non-commercial personal use only", that reproduction and distribution need "the express prior written consent of Fiscal Service", and "You should not assume anything on this site is necessarily in the public domain." | read |
| [FI-R] | `https://www.treasurydirect.gov/robots.txt`, read 2026-11-19: `User-agent: *` / `Disallow: /` (only the `usasearch` agent is allowed). | read |
| [FI-P] | FedInvest pages `https://www.treasurydirect.gov/GA-FI/FedInvest/selectSecurityPriceDate` and `.../todaySecurityPriceDetail`, read 2026-11-19. The second said "Current day prices are not available yet. Please try back after 1:00 p.m. EST." Neither page states a price source, a reuse rule or a download format. The form's action and method were not visible in the fetched text. | read |
| [FI-A] | Fiscal Service web API terms, `https://www.treasurydirect.gov/legal-information/developers/web-api-terms/`, read 2026-11-19: they allow building services on "Fiscal Service APIs". The FedInvest price pages are HTML pages, not part of that API, so these terms do not cover them. | read, inferred for the last clause |
| [TY-M] | Treasury yield curve methodology, `https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology`, read 2026-11-19: the par curve is "usually available ... by 6:00 PM Eastern Time each trading day"; its inputs are "indicative, bid-side market price quotations (not actual transactions)" taken "at or near 3:30 PM"; the method is a monotone convex par curve. | read |
| [REC] | `tools/recorder/sources.json`, entry `us-treasury-par-yields` (licence line "US federal government work (17 USC 105)", `redistribute_raw` "believed yes, unconfirmed", terms read 2026-11-06 by the recorder lane), and `docs/developer-guides/recorder-actions.md`: forward-log rows keep the parsed values of public-domain sources. | read (repository) |
| [H21] | `10-execution/paper-trading.md` rulings HR-42 to HR-55, HR-77, HR-78: book, average cost, financing, pre-trade checks, canonical bytes and hash. | read (repository) |
| [SHA] | NIST FIPS 180-4, SHA-256. | standard, recalled |

Not found, and said so: any Treasury or Fiscal Service page that permits automated daily fetching, storing or republishing of FedInvest prices. The pages `treasurydirect.gov/legal-information/`, `.../terms-conditions/`, `.../policies/` and `fiscal.treasury.gov/privacy.html` returned 404 on 2026-11-19. This is a reading of published terms, not legal advice.

## Data decision (KR-70, KR-72)

K-1 asks first for named Treasury CUSIPs marked to recorded FedInvest end-of-day prices, and gives a fallback "if those prices cannot be recorded under their terms". On the reading above recording is not clearly permitted: the site's robots file disallows every automated agent [FI-R], and its terms limit use to personal viewing and reserve reproduction [FI-T]. So this ledger uses the plan's fallback: **DV01-weighted constant-maturity exposures, marked on a curve fitted to the Treasury par yield curve the recorder already takes**, labelled "paper marks on a fitted curve; not tradable". No FedInvest page is fetched by any code in this repository.

The job makes no market-data request of its own. It reads `actions/log.jsonl` on branch `forward-log`, series `recorder/us-treasury-par-yields`, whose rows already publish five parsed par yields a day (3 month, 2, 5, 10 and 30 year) under the recorder's rule for public-domain sources [REC]. A DAY row repeats those five numbers for its date and names the forward-log row they came from by hash. That is the same treatment the recorder gives the series, no more: no raw file is fetched, stored or committed here. The recorder's own note that Treasury's reuse terms are "believed yes, unconfirmed" applies to this ledger too. Checked at integration (2026-11-19, ruling KR-108, evidence class read): branch `origin/forward-log`, `actions/log.jsonl`, publishes the values themselves, not only hashes. For example the row of sequence 346 (event time 2026-11-18T22:13:39Z, series `recorder/us-treasury-par-yields`) carries `observations` with the five numbers for 2026-11-18 (3 month 4.34, 2 year 4.8, 5 year 4.89, 10 year 5.07, 30 year 5.41) beside the file's `sha256` and `state_sha256`; rows where nothing changed carry an empty `observations`. `docs/developer-guides/recorder-actions.md` ("No raw data leaves the runner") states the rule: the rows carry URL, sha256, size, licence and commit, "and, for public-domain sources only, the parsed values". The ledger therefore keeps the five values, which the forward log already publishes, and adds nothing the recorder does not already publish.

## Model

### Units
One unit of quantity is USD 100 of face value. Prices are per 100 of face, so quantity times price is dollars. Yields are in percent as Treasury publishes them. Every number in a row is a decimal string (HR-44); only `seq` is an integer.

### Calendar (KR-73)
A row exists for a date only if the library calendar `USGS` (`core.calendar.is_business_day`) says it is a business day. Weekends and US government securities market holidays get no row. An early close is a full business day here, because Treasury still publishes a curve. The recorder's `tools/recorder/holidays.txt` (Federal Reserve holidays) is not used: it differs on Good Friday. If Treasury publishes no curve on a `USGS` business day, that day is a gap (below), not a silent skip.

### Instruments and the daily re-strike (KR-74)
Four exposures: `UST-CM-2Y`, `UST-CM-5Y`, `UST-CM-10Y`, `UST-CM-30Y`. On ledger day D each is a hypothetical semi-annual bond struck at par: coupon equal to that day's recorded par yield at its tenor, maturity D plus the tenor in whole years (29 February becomes 28 February), price exactly 100 with no accrued interest. These are not securities; no CUSIP exists for them.

On the next ledger day D' the bond struck on D is one or more days older. It is marked on D' (below), the gain or loss on the open position is paid into cash, and the position is re-struck, unit for unit, into the new par bond of D' at 100. The re-strike has no cost and no fill: it is a bookkeeping convention that keeps the maturity constant, and it is one reason the label says "not tradable".

### Marks (KR-76)
For the bond struck on D (coupon c, maturity M), on day D':
- curve time `tau = (M - D') in days / 365.25`, held inside the first and last knot;
- `y_roll` = the curve of day D read at tau; `y_close` = the curve of day D' read at tau. The curve is the linear interpolant (`core.interp.evaluate`, method `linear`) through the five recorded par yields at 0.25, 2, 5, 10 and 30 years. Both yields are rounded half-even to 6 decimals of a percent;
- `bond.price.from_yield` (semi-annual, actual/actual accrual inside the coupon period) at each yield gives `clean_roll`, `clean_close` and `accrued`, each rounded half-even to 6 decimals;
- `mark = clean_close + accrued` (exact).
The modified duration of each new par bond comes from the same operation at its own coupon, rounded to 6 decimals.

### The fixed trading rule (KR-75)
Let k be the number of on-time DAY rows already in the ledger. Step `k mod 8` of this list is the day's one order:

| Step | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| Order | BUY 2Y | BUY 5Y | BUY 10Y | BUY 30Y | SELL 2Y | SELL 5Y | SELL 10Y | SELL 30Y |

A BUY is for the reference quantity `q_ref = floor(500 x 100 / D_mod / 100) x 100` units, which has a DV01 of about USD 500 (one unit at par moves `D_mod / 100` dollars per basis point). A SELL is for the whole position in that instrument; if there is none, no order is sent and the row says why. The order is an IOC limit order at `100 +/- (half spread + 2 ticks)`. On a late day (below) no order is sent. The rule reads no price, yield or P&L.

### Pre-trade (KR-88, Q8k)
Before the order goes to the simulator:
- `exec.tca.pretrade` gives the pre-trade cost estimate, with assumed inputs: ADV 10 times `q_ref`, participation 0.1, the instrument's assumed daily volatility, the assumed half spread, and impact parameters a1 700, a2 0.5, a3 1, a4 0.5, b1 0.9. These parameters are placeholders, not calibrated to any market; the record is labelled "placeholder weights".
- `paper.pretrade.check` applies the limits: `max_order_qty` 40,000 units, `max_notional` 4,500,000, `max_abs_position` 40,000 units, `price_band` 0.005, `max_orders_per_day` 2, `kill_switch` false, `allow_short` false. Reference price 100; cash is the balance after the day's re-strike. A rejected order is recorded with its reasons and never reaches the simulator.

### Fill simulator and assumed cost (KR-77, KR-78)
Fills come only from `exec.sim.lit.run` (`lit-matching.md`), tick 1/256, lot 100 units, fees zero. The book is synthetic: three levels a side, the best at `100 +/- half spread` and the others one tick apart. The **assumed cost** is the half spread: 1/128 of a point for 2Y and 5Y, 1/64 for 10Y, 1/32 for 30Y. These are assumptions with no source. Each level shows `floor(q_ref x pct / 100 / 100) x 100` units (at least one lot), where `pct = 20 + (byte mod 31)` and the bytes are the first six of

`seed = SHA-256("qf-paper-ledger/1|" + date + "|" + hash of the previous row + "|" + symbol)`

(asks from bytes 0 to 2, bids from bytes 3 to 5). The book therefore shows 60% to 150% of `q_ref`, some orders fill in part and the remainder is cancelled, and nobody can choose the book after seeing the day: it is fixed by the date and the chain.

### Post-trade TCA per order (Q8k)
Every order, filled or rejected, carries `exec.tca.attribution` with decision price, arrival mid and end price all 100 and each fill's mid 100. Delay, impact and opportunity are therefore zero by construction, and `spread` is the cost paid against par. TCA values are binary64 results rounded half-even to 10 decimals.

### Cash and financing (KR-88)
Cash earns or pays, at one rate, the previous ledger day's recorded 3 month par yield on the opening balance, actual/365, rounded half-even to the cent (`paper.book.end_of_day`, HR-52). There is no repo rate, no borrow charge and no short position.

### Daily P&L explain (KR-79)
With n the opening units of an instrument and the sums over instruments:
- `coupon_accrual` = sum n x accrued; `cash_interest` as above; **carry** = coupon_accrual + cash_interest
- **roll_down** = sum n x (clean_roll - 100)
- **curve_move** = sum n x (clean_close - clean_roll)
- **fills_costs** = sum over fills s q (100 - p) minus fees (s = +1 BUY, -1 SELL)
- **unexplained** = (nav_close - nav_open) - (carry + roll_down + curve_move + fills_costs)

NAV = cash + 100 x units held. **Threshold: |unexplained| must be exactly 0.** Reason: every term is an exact decimal product of recorded 6-decimal marks and whole lots, the three market terms telescope to n x (mark - 100), and the only rounding (cash interest, to the cent) is posted to cash as rounded. A non-zero residual can only be a bookkeeping defect (HR-53), so no allowance is given. The writer refuses to append a day that fails this, and the verifier fails a ledger that contains one.

What this does and does not show: the identity tests the bookkeeping. It is not a test of a risk model, because the terms are successive revaluations, not sensitivities times moves.

## Ledger row format (KR-80)

Format string `qf-paper-ledger/1`. JSON Lines, one row per line, file `ledger/ledger.jsonl` on branch `paper-ledger`.

| Field | Meaning |
|---|---|
| `seq` | integer from 0 |
| `ts` | UTC time of the run that wrote the row, `YYYY-MM-DDTHH:MM:SSZ` |
| `kind` | `GENESIS` (row 0 only), `DAY`, `GAP` |
| `label` | "paper marks on a fitted curve; not tradable" |
| `format` | `qf-paper-ledger/1` |
| `body` | object, below |
| `prev` | hash of the previous row; 64 zeros for row 0 |
| `hash` | lowercase hex SHA-256 of the canonical bytes |

Canonical bytes are HR-45 of `paper-trading.md` unchanged: the row without `hash`, keys sorted by code point at every level, separators `,` and `:`, ASCII only. A line that repeats a key is a parse failure (HR-78).

`GENESIS` body: `config` (the whole of `tools/paper_daily/config.json` with every scalar as a string), `config_sha256`, `spec`, `statement`, `ceiling`, `start_cash`. The configuration is fixed here: the verifier fails if the file on `main` later differs from the genesis row. A change of instruments, rule, sizes, limits, costs, thresholds or row fields needs a new format string, a ruling, and a new ledger; version 1 rows are never rewritten.

`DAY` body:

| Field | Meaning |
|---|---|
| `date`, `prev_date`, `days` | the business day, the previous DAY row's date, calendar days between them (0 on the first day) |
| `timing` | `on_time` or `late` (below) |
| `gaps_since_prev` | dates of the GAP rows since the previous DAY row |
| `run` | `commit` (of `main`) and `impl` |
| `source` | `series` and `row_hash` of the forward-log row that last set this date's yields |
| `par_yields` | the five recorded par yields, percent |
| `instruments.<symbol>` | `position_open`; `old` (the bond being marked: coupon, maturity, mod_duration); `tau`, `y_roll`, `y_close`, `accrued`, `clean_roll`, `clean_close`, `mark`; `pnl` (carry, roll, curve); `new` (the bond struck today). The first day has only `position_open` and `new` |
| `orders[]` | `order_id`, `symbol`, `side`, `type`, `quantity`, `limit_price`, `ref_price`, `rule_step`, `seed`, `book`, `fill_source`, `tca_pretrade`, `pretrade` (accepted, reasons), `status`, `fills[]` (quantity, price, fee), `filled`, `cancelled`, `tca` |
| `no_order` | why no order was sent, or empty |
| `cash_rate`, `cash_open`, `cash_close`, `positions_close`, `nav_open`, `nav_close`, `pnl` | the book |
| `explain` | carry, coupon_accrual, cash_interest, roll_down, curve_move, fills_costs, trading, fees, unexplained, total |
| `cumulative` | `recorded_trading_days`, `pnl` since the start |

`GAP` body: `date`, `reason`, `run`.

## Chain and anchor (KR-81)
The chain is the `prev`/`hash` link above. After each push the job writes `anchors/<UTC time>.json` with `count`, `head`, `format` and `config_sha256` to branch `paper-ledger-anchors` and stamps it with OpenTimestamps, exactly as `recorder.yml` anchors the forward log (plan 13.2 R4). Before each push, every anchor already held must still match line `count` of the ledger. The head hash is also in each commit message on `paper-ledger` (HR-46). Verifying a Bitcoin attestation is `ots verify` on the `.ots` file, as in `docs/developer-guides/forward-log-anchors.md`.

## On time, late, gap, start (KR-82, KR-83)
- **On time.** A DAY row for business day D is on time if its run started before 19:30:00 UTC on the next business day. That is before the next day's 3:30 PM Eastern input quotes in either daylight regime [TY-M], so an on-time row was written before the next curve existed.
- **Late.** If a run finds that D has a recorded curve but its cut-off has passed (the job did not run), it still writes D's row, with `timing` "late", the writing run's `ts`, the marks and the explain, and **no order**. A late day does not count as a recorded trading day. It is never presented as on time: the verifier recomputes the label from `ts`.
- **Gap.** If D's cut-off has passed and no complete curve for D is in the recorded log, the run writes a GAP row for D. The next DAY row lists it in `gaps_since_prev`, and its P&L covers the whole span from the previous DAY row. A gap is never filled in later.
- **Missing row.** Every business day after the first has exactly one row, DAY or GAP. A ledger with a business day missing between two rows fails verification.
- **Start.** The first run writes the genesis row and one DAY row for the latest business day that has a recorded curve and is still on time. Earlier days are never back-filled.
- A run that finds nothing due writes nothing.

## Recorded trading day (KR-87)
For the K-2 count "at least 20 trading days recorded before the tag", a recorded trading day is a DAY row with `timing` "on_time" in a ledger that passes the full verification below (including its anchors). Late days and gaps do not count. `verify_ledger.py verify --require-days 20` is the gate.

## Verification (KR-84 to KR-86, KR-89)
`tools/paper_daily/verify_ledger.py verify`, in this order; it stops at the first failure and never repairs.

| Reason | Check |
|---|---|
| `PARSE`, `SEQ`, `HASH`, `LINK`, `LABEL`, `FORMAT`, `KIND` | the chain, row by row |
| `CONFIG` | genesis `config_sha256`, and the configuration equals `config.json` |
| `DATE`, `MISSING_DAY`, `TIMING` | dates increase, each is a `USGS` business day, none is missing, `ts` not before the date, timing label matches `ts`, gap rows listed |
| `HOLDOUT` | no row date inside a prereg holdout window (`research/holdout_scan.py`, plan 14.10 rule 6) |
| `CASH`, `POSITION`, `NAV`, `EXPLAIN`, `ORDER`, `COUNT` | **exact replay from the ledger alone**: starting from the genesis cash, each day's opening state must be the previous day's closing state, and cash interest, every explain term, cash, positions, NAV and P&L are recomputed in exact decimal from the row's own marks and fills and must equal the row. This path uses no CLI and no data outside the ledger |
| `RECOMPUTE` | **rebuild through the CLI**: each DAY body is rebuilt from the previous state, the row's par yields, its `ts` and the previous hash, and compared with the row: the marks, the rule's order, the seed and book, the limit check, the simulated fills and both TCA records. Decimal fields may differ by at most 1e-6 relative to max(1, value); everything else must be equal |
| `ANCHOR`, `DAYS` | with `--anchors`, `--require-days` |

The 1e-6 allowance (KR-86) exists only because bond prices and the pre-trade estimate are binary64 results that pass through `pow`, which may differ in the last bit between platforms; it is one unit of the last recorded decimal of a mark. It cannot hide a wrong P&L, because the exact replay has no allowance.

The writer applies the holdout check to every date before writing, replays each day it builds, and runs the whole verification on the new ledger before the file is replaced.

## Errors
The job is a script, not a CLI operation, so it has refusals instead of error codes. A refusal prints `REFUSED: <why>`, exits 1 and writes nothing: the recorder log fails its own chain check or is empty; the existing ledger does not verify; a date falls in a holdout window; a CLI case returns an error; the simulator rejects the order; the day built does not replay or its explain does not sum.

## Worked example
Synthetic yields (invented by the test, not market data), second day of the offline run, instrument `UST-CM-2Y`. Previous day 2027-01-04: 2 year par yield 4.81, 3 month 4.28; 26,500 units bought; cash 7,349,714.0625. Day 2027-01-05, one calendar day later:
- bond: coupon 4.81, maturity 2029-01-04; `tau` = 730 / 365.25 = 1.998631; `y_roll` 4.809585, `y_close` 4.849562;
- `accrued` = 2.405 x 1 / 181 = 0.013287; `clean_roll` 100.000625; `clean_close` 99.925390; `mark` 99.938677;
- coupon_accrual = 26,500 x 0.013287 = 352.1055; cash_interest = 7,349,714.0625 x 0.0428 / 365 = 861.83; carry 1,213.9355;
- roll_down = 26,500 x 0.000625 = 16.5625; curve_move = 26,500 x (99.925390 - 100.000625) = -1,993.7275;
- the rule's step 1 buys 5Y: 11,300 units asked, the book shows 4,200, 2,200 and 4,700 at 100.0078125, 100.01171875 and 100.015625, so 11,100 fill and 200 are cancelled; fills_costs = -(32.8125 + 25.78125 + 73.4375) = -132.03125; TCA spread 132.03125, 1.1684 bp of the order;
- P&L = 1,213.9355 + 16.5625 - 1,993.7275 - 132.03125 = -895.26075 = NAV 9,998,818.80175 - 9,999,714.0625; unexplained 0.

## Golden cases
Pinned in `python/tests/test_paper_daily.py` (`pl_k`), computed on the synthetic yields of that file with run commit "testcommit". `"reviewer": "none: self-assessment; no second review (owner decision 2026-11-18)"`. Hand check: the worked example above, done with a calculator from the row's own numbers. No outside tool has checked these values.

| Case | Input | Expected |
|---|---|---|
| pl_k-0001 | first DAY row, 2027-01-04 | row hash `d7f22a80b63fa8ad612907dd6c8b1d4ba0e67527398887bb7848f5e6e5d191f3`; P&L -285.9375 |
| pl_k-0002 | second DAY row, 2027-01-05 | row hash `f887e3d3d0a9ac889d95d5a6e3ee3578b4908286700c5428ea1c7daee2980cb4`; the worked example |
| pl_k-0003 | 30 business days from 2027-01-04 | head `56a3dd05b177badb7e91c5f1033058282773df03d7fc58b5d1676def5258cf28`; 30 recorded trading days; 17 orders filled, 13 partly filled |

These hashes were computed on Windows with Python 3.15. They depend on binary64 `pow` results rounded to 6 and 10 decimals, so a different platform should agree; that is not verified until the Linux CI run of this test.

## Acceptance tests (fixed in this commit, before the first scheduled run)

| ID | Plan | Test |
|---|---|---|
| P1 | K-1 | Every row carries the label; no code path fetches FedInvest; fills only from `exec.sim.lit.run`, each fill a level of the recorded book |
| P2 | K-2 | On every day of a 30-business-day offline run, P&L equals carry + roll_down + curve_move + fills_costs with unexplained exactly 0, and the terms are non-zero on at least 25 days |
| P3 | K-2 | On every day cash_close + 100 x units = nav_close, and each day opens from the previous close |
| P4 | K-2 | The exact replay from the ledger alone (no CLI) passes on the run and fails on each planted fault of P7 |
| P5 | K-2 | Anchors: a rewrite of an old row with every later hash recomputed passes the chain and the replay and fails the anchor check; a truncated ledger fails it |
| P6 | Q8k | Every order has a pre-trade estimate and a post-trade TCA record whose parts sum to its total within 1e-10 |
| P7 | 14.10 rule 1 | Planted faults, each shown failing with its reason: a changed byte (`HASH`); a removed row (`SEQ`); a repeated key (`PARSE`); with all hashes recomputed: an explain term, a consistent rewrite that leaves the terms not summing (`EXPLAIN`), P&L or NAV (`NAV`), cash (`CASH`), positions (`POSITION`), the day count (`COUNT`), a removed day (`MISSING_DAY`), a removed gap row (`MISSING_DAY`), a late day relabelled (`TIMING`), a wrong label (`LABEL`), a changed configuration (`CONFIG`), a derived mark input, yield, TCA value, seed or rule step (`RECOMPUTE`), fills on a rejected order (`ORDER`). The writer refuses a day whose explain is off by one cent, and refuses to extend a ledger that does not verify |
| P8 | K-2 | A pre-trade limit breach is rejected: with tightened limits the rule's order is `REJECTED` with reasons `MAX_QTY`, `MAX_NOTIONAL`, has no fills, and positions stay zero; the kill switch rejects |
| P9 | K-2 | A business day with no recorded curve becomes a GAP row; a day the job missed becomes a late row with no order; neither counts; a federal holiday has no row; the start is not back-filled |
| P10 | 14.10 rule 6 | A date inside a prereg holdout window is refused by the writer and fails verification |
| P11 | K-2 | `--require-days 20` fails on 19 recorded trading days and passes on 30. **The tag needs this to pass on the real ledger; on 2026-11-19 the real ledger has 0 days** |

## Limits
- **Open audit findings (2026-11-19): KA-C1 to KA-C5, KA-C12, KA-C13.** Among them: the on-time label is the runner's own clock, and the gate command as written does not check anchors. The job is not scheduled until the schedule-blocking ones are closed. Register: `docs/known-issues.md`.
- The marks are not prices of any security. Five par yields joined by straight lines are a crude curve, and a par yield is used as the yield to maturity of a bond that is one or more days off par.
- The cash rate is the 3 month par yield for both credit and debit; there is no repo market, no borrow cost and no short position.
- The book, the half spreads, the volatilities and the ADV are assumptions. The pre-trade impact parameters are placeholders.
- Post-trade TCA has only a spread term, because the order meets one static book at par.
- Recorded yields that Treasury later revises are not re-applied: a row keeps what the recorder held when it was written, and names that row.
- The daily job and its verification run on the Python CLI only. The rebuild has not been run on the Java, C++ or Rust CLI.
- The explain identity is exact by construction (see above); it finds bookkeeping faults, not model error.
- On free data paper results are never evidence of tradable profitability (11.6).
