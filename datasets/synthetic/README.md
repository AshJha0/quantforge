# Synthetic datasets

Generate deterministic datasets from documented seeds and parameters. For curve calibration, generate instrument quotes from a known underlying curve/model and preserve the generating parameters separately from the calibration input. Avoid constructing an incoherent set of arbitrary par quotes.

No dataset is stored here yet. Stage B's synthetic quotes live inside the golden cases (`datasets/golden/stage_b/`, tagged `synthetic` where the generator set it) and in `program/exercises/data/`. They are written by `oracle/python/`.
