from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d


def normalize_available_weights(weights: dict[str, float], available: dict[str, np.ndarray]) -> dict[str, float]:
    result = {name: float(value) for name, value in weights.items() if name in available}
    total = sum(max(0.0, value) for value in result.values())
    if total <= 0:
        return {name: 1.0 / len(result) for name in result} if result else {}
    return {name: max(0.0, value) / total for name, value in result.items()}


def combine_signals(
    signals: dict[str, np.ndarray],
    weights: dict[str, float],
    smoothing_seconds: float = 3.0,
) -> np.ndarray:
    length = max((len(curve) for curve in signals.values()), default=0)
    if length == 0:
        return np.zeros(0, dtype=np.float32)

    normalized_weights = normalize_available_weights(weights, signals)
    combined = np.zeros(length, dtype=np.float32)
    for name, curve in signals.items():
        if name not in normalized_weights:
            continue
        array = np.asarray(curve, dtype=np.float32)
        if array.size < length:
            array = np.pad(array, (0, length - array.size))
        combined += normalized_weights[name] * array[:length]

    if smoothing_seconds > 0:
        combined = gaussian_filter1d(combined, sigma=smoothing_seconds)
    if combined.max() > 0:
        combined = (combined - combined.min()) / (combined.max() - combined.min() + 1e-6)
    return combined.astype(np.float32)
