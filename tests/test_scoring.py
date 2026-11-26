import numpy as np

from highlights.scoring.scoring import combine_signals, normalize_available_weights


def test_normalize_available_weights_redistributes_missing_signals():
    weights = {"audio": 0.5, "chat": 0.5, "scene": 0.0}
    normalized = normalize_available_weights(weights, {"audio": np.ones(10), "chat": np.zeros(10)})
    assert abs(normalized["audio"] - 0.5) < 1e-6
    assert abs(normalized["chat"] - 0.5) < 1e-6


def test_combine_signals_has_values_in_zero_one():
    signals = {
        "audio": np.array([0.0, 0.5, 1.0]),
        "chat": np.array([1.0, 0.5, 0.0]),
    }
    score = combine_signals(signals, {"audio": 0.5, "chat": 0.5})
    assert score.min() >= 0.0
    assert score.max() <= 1.0
