# Glossary

Terms are listed under the stage that first needed them. The [Curves gallery](docs/curves/README.md) shows most stage B terms on real output.

## Stage A: Foundation

| Term | Meaning |
|---|---|
| As-of view | What was known at a given instant |
| Bitemporal | Tracking both when something happened and when it became known |
| Business-day convention | How a date that falls on a holiday moves |
| Canonical form | The one byte spelling of a document, used for hashing |
| Clean room | Writing an implementation from the spec alone, unable to see the other three |
| Compounding | How interest is reinvested: simple, periodic, continuous |
| Conformance | An implementation matching golden cases within tolerance |
| COS method | Option pricing from a characteristic function, by cosine series |
| Crossed quote | Bid above ask |
| Day count | The rule that turns two dates into a year fraction |
| Discount factor | The value today of one unit paid later |
| Evidence class | How a claim is backed: analytic, simulated, proxy or observed |
| Forward log | An append-only, hash-chained record of dated entries |
| Golden case | A stored case with an independently obtained expected result |
| Golden suite | A file of golden cases on one topic, such as `daycount` |
| Knowledge time | The instant the store learned a value |
| Locked quote | Bid equal to ask |
| Method test | A test on synthetic data, proving a method and not market accuracy |
| Monotone convex | Forward-rate interpolation that reprices all inputs (Hagan and West) |
| Oracle | The source of expected results, separate from the implementations |
| Rannacher start-up | Implicit half steps that damp a payoff kink before Crank-Nicolson |
| Ruling | A recorded decision on a point a spec left silent, in `rulings.md` or `stage-b-rulings.md` |
| Snapshot | A frozen, hashed document of everything a calculation read |
| Sobol sequence | Deterministic points that fill a cube evenly |
| Tension spline | A spline with a parameter pulling it towards straight lines |
| Tolerance class | A named, justified comparison rule |

## Stage B: FX and rates slices

| Term | Meaning |
|---|---|
| Basis point | 0.0001 |
| Bootstrap | Solving a curve so that each input quote reprices |
| DV01 | Change in PV for rates up 1 bp, signed, by bumping quotes and rebuilding the curve |
| Forward points | The forward minus spot, in pips |
| FRA | Forward rate agreement: one fixed-against-floating payment on a future period |
| Key-rate DV01 | The same change for one quote at a time, showing where on the curve risk sits |
| OIS | Overnight indexed swap: fixed against a compounded overnight rate such as SONIA or SOFR |
| Par rate | The fixed rate that makes a swap worth zero |
| Pillar | A dated node of a curve, holding a solved discount factor |
| Projection curve | A curve that forecasts floating rates, while another curve discounts |
| Quote-driven basis | The gap between the FX-implied base rate and the base OIS rate, taken straight from quotes |
| Zero rate | The continuously compounded rate from today to a date: `-ln(D)/t` |
