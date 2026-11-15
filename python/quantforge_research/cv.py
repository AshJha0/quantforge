"""Walk-forward splits (plan 12.5 A1).

Plain idea: train on the past, test on the next block, roll forward. Each split is (train indices, test indices), both
ascending, every train index earlier than every test index. `gap` observations between them act as the purge for
labels that span `gap` bars (`specifications/11-research/purged-cv.md`). An expanding window keeps all history; a
rolling one keeps the last `train_size` observations.
"""

from __future__ import annotations


def walk_forward(
    n: int,
    train_size: int,
    test_size: int,
    *,
    step: int | None = None,
    gap: int = 0,
    expanding: bool = False,
) -> list[tuple[list[int], list[int]]]:
    if min(n, train_size, test_size) < 1 or gap < 0:
        raise ValueError("n, train_size and test_size must be at least 1 and gap non-negative")
    step = test_size if step is None else step
    if step < 1:
        raise ValueError("step must be at least 1")
    out = []
    start = train_size + gap  # first test index
    while start + test_size <= n:
        tr_end = start - gap
        tr_start = 0 if expanding else tr_end - train_size
        out.append((list(range(tr_start, tr_end)), list(range(start, start + test_size))))
        start += step
    return out
