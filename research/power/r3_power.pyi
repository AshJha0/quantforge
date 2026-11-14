# Type stub for the functions of r3_power.py that research/r3_runner.py calls. Types only: r3_power.py is the
# estimator pinned by amendment 4 C5 (commit 09c596f) and is not edited.
from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray

Arr: TypeAlias = NDArray[np.float64]

def lo_sharpe(x: Arr, q: int, lags: int) -> tuple[Arr, Arr]: ...
def boot_sharpe(x: Arr, q: int, mean_block: int, rng: np.random.Generator, draws: int = ...,
                chunk: int = ...) -> tuple[Arr, Arr]: ...
def thirds_positive(x: Arr) -> NDArray[np.bool_]: ...
def expected_max_z(n: int) -> float: ...
