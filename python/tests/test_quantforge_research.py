"""Tests for the research package: walk-forward, trial registry, Reality Check (gap items G10, G11, G14)."""

import numpy as np
import pytest

from quantforge_research.cv import walk_forward
from quantforge_research.snooping import reality_check, stationary_indices
from quantforge_research.trials import register, trial_count


def test_walk_forward_rolling_by_hand():
    s = walk_forward(10, 4, 2)
    assert s == [([0, 1, 2, 3], [4, 5]), ([2, 3, 4, 5], [6, 7]), ([4, 5, 6, 7], [8, 9])]


def test_walk_forward_gap_expanding_and_order():
    s = walk_forward(20, 5, 3, gap=2, expanding=True, step=4)
    for tr, te in s:
        assert tr[0] == 0 and max(tr) + 2 < min(
            te
        )  # gap observations dropped between train and test
    assert [te[0] for _, te in s] == [7, 11, 15]


def test_walk_forward_rejects_bad_sizes():
    with pytest.raises(ValueError):
        walk_forward(10, 0, 2)
    assert walk_forward(5, 4, 2) == []


def test_trial_registry(tmp_path):
    p = tmp_path / "trials.csv"
    assert trial_count("S", p) == 0
    assert register("S", "S-T01", "L=60", p) == 1
    assert register("S", "S-T02", "L=120", p) == 2
    register("Other", "O-T01", "x", p)
    assert trial_count("S", p) == 2
    with pytest.raises(ValueError):
        register("S", "S-T01", "again", p)


def test_repo_registry_counts_r3():
    assert trial_count("R3-01") >= 1  # research/trials.csv is the source of N for DSR (J-13)


def test_stationary_indices_in_range():
    idx = stationary_indices(50, 0.1, np.random.default_rng(1))
    assert idx.min() >= 0 and idx.max() < 50


def test_reality_check_detects_planted_edge():
    rng = np.random.default_rng(7)
    X = rng.normal(0, 0.01, (500, 10))
    X[:, 3] += 0.004
    r = reality_check(X, np.zeros(500), n_boot=300, seed=1)
    assert r["best"] == 3 and r["p_value"] < 0.01


def test_reality_check_size_on_nulls():
    """J-4: size at most 5 % on simulated null strategies (200 null sets of 5 strategies, all means 0, the least
    favourable null). Pass if the rejection rate at nominal 5 % is within 5 % plus 3 SE (0.096)."""
    rng = np.random.default_rng(20261114)
    rej = 0
    for k in range(200):
        X = rng.normal(0, 0.01, (250, 5))
        rej += reality_check(X, np.zeros(250), n_boot=200, mean_block=5, seed=k)["p_value"] <= 0.05
    assert rej / 200 <= 0.05 + 3 * np.sqrt(0.05 * 0.95 / 200)
