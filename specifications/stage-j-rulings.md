# Stage J rulings

Normative for stage J (v0.9). Earlier rulings still hold, among them `r6-rulings.md` R6-8.1 (intermediate overflow is `E_NON_FINITE`) and `01-core/limits.md` (order `E_PARSE`, `E_SCHEMA`, `E_LIMIT`, then rule checks). Append-only; an amendment is a new row that names the row it amends.

## Lane J-0b, fuzz findings (main run 43390662426, seed 3)

| # | Point | Ruling |
|---|---|---|
| J-0b.1 | `vol.garch.forecast` horizon limit | `horizon` above 100,000 is `E_LIMIT` (field `horizon`), checked after `E_SCHEMA` and before the rule checks (`H < 1` stays `E_INPUT`). The output holds one variance per step, so the closed form would not bound the work; the limit is the output-size limit of `core.rng.*`. Java already applied it; Rust and C++ looped on `horizon` 2^31. Goldens `fuzzfix_j-0001`, `-0002` |
| J-0b.2 | `vol.garch.estimate` on overflowing squares | When the mean, the sample variance `(1/n) sum e_t^2` or the `SAMPLE` initial variance of finite returns is not finite, the result is `E_NON_FINITE` (R6-8.1), decided before the `E_DOMAIN` zero-variance checks and before any search. Python searched with an all-infinite objective (20 s); Java returned `E_DOMAIN`, C++ `E_NO_CONVERGENCE`, Rust already `E_NON_FINITE`. Goldens `fuzzfix_j-0003`, `-0004` |
| J-0b.3 | Ragged matrices in `exotic.basket.moment` | `correlation` must have `n` rows of length `n` (`n` the number of forwards); any other shape, including an empty or short row, is `E_INPUT`, checked for every row before symmetry or the diagonal is read. Java read `rho[1][0]` of an empty row and crashed with exit 70. Goldens `fuzzfix_j-0005`, `-0006` |
