import numpy as np

from highlights.selection.selection import select_cuts


def test_selection_respects_minimum_distance():
    score = np.zeros(300, dtype=np.float32)
    score[50] = 1.0
    score[51] = 0.9
    score[100] = 0.8
    cuts = select_cuts(score, target_duration=60, min_cut=20, max_cut=40, min_distance=30)
    assert cuts
    assert all(c.end - c.start >= 20 for c in cuts)


def test_selection_returns_no_cut_for_flat_score():
    cuts = select_cuts(np.zeros(300), target_duration=60, min_cut=20, max_cut=40)
    assert cuts == []
