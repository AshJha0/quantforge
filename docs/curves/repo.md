# Repo and special repo curves

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `8dddd58`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.0 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.0 (rustc 1.99.1), on one Windows machine.

## What it is

General collateral repo rates by term, and specials against them. Stage D.

## Runs

Each run is labelled. Synthetic inputs are copied from a golden case's inputs, so they show the method, not a market. Real inputs name their source and date.

### `repo.forward`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/repo_forward_d.json`](../../examples/repo_forward_d.json). Command: `quantforge batch < examples/repo_forward_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `dirty` | `102.47656626467639` |
| `forward_dirty` | `100.67489108144223` |
| `forward_clean` | `100.39312312564113` |
| `interest` | `0.32877898343250345` |
| `special_spread` | `None` |
| `specialness_value` | `None` |



## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| repo.forward: dirty | 1 | 102.47656626467639 | 102.47656626467639 | 102.47656626467639 | 102.47656626467639 | 0 |
| repo.forward: forward_dirty | 1 | 100.67489108144223 | 100.67489108144223 | 100.67489108144223 | 100.67489108144223 | 0 |
| repo.forward: forward_clean | 1 | 100.39312312564113 | 100.39312312564113 | 100.39312312564113 | 100.39312312564113 | 0 |
| repo.forward: interest | 1 | 0.3287789834325034 | 0.3287789834325034 | 0.32877898343250345 | 0.3287789834325034 | 5.55e-17 |
| repo.forward: special_spread | 1 | None | None | None | None | 0 |
| repo.forward: specialness_value | 1 | None | None | None | None | 0 |

## Oracle evidence and limits

4 golden cases with status ok in `datasets/golden/stage_d` for `repo.forward`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| repo.forward: analytic | 4 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.
