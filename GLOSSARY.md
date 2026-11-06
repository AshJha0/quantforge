# Glossary

| Term | Meaning |
|---|---|
| As-of view | What was known at a given instant |
| Basis point | 0.0001 |
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
| Ruling | A recorded decision on a point a spec left silent, in `rulings.md` |
| Snapshot | A frozen, hashed document of everything a calculation read |
| Sobol sequence | Deterministic points that fill a cube evenly |
| Tension spline | A spline with a parameter pulling it towards straight lines |
| Tolerance class | A named, justified comparison rule |
