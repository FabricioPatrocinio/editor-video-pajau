from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks

from ..models import Cut


def select_cuts(
    score: np.ndarray,
    target_duration: float,
    min_cut: float = 20,
    max_cut: float = 90,
    max_cuts: int | None = None,
    padding_before: float = 8,
    padding_after: float = 4,
    min_distance: float = 12,
    ignore_intervals: list[list[float]] | None = None,
    max_overlap: float = 0.20,
) -> list[Cut]:
    score = np.asarray(score, dtype=np.float32)
    if score.size == 0 or score.max() <= 1e-6:
        return []

    usable = np.ones(len(score), dtype=bool)
    for interval in ignore_intervals or []:
        if len(interval) >= 2:
            a, b = max(0, int(interval[0])), min(len(score), int(interval[1]))
            usable[a:b] = False

    masked = score.copy()
    masked[~usable] = 0.0
    if masked.max() <= 1e-6:
        return []

    peaks, properties = find_peaks(
        masked,
        distance=max(1, int(min_distance)),
        prominence=max(float(masked.std()) * 0.1, 1e-4),
    )
    if len(peaks) == 0:
        peaks = np.array([int(np.argmax(masked))])

    candidates: list[Cut] = []
    for peak in peaks:
        start = max(0, int(peak) - int(padding_before))
        end = min(len(score), int(peak) + int(padding_after))

        ideal = (int(min_cut) + int(max_cut)) // 2
        if end - start < int(min_cut):
            end = min(len(score), start + ideal)
            if end - start < int(min_cut):
                end = min(len(score), int(start) + int(min_cut))
        end = min(end, start + int(max_cut))

        if end - start < int(min_cut) or not usable[start:end].all():
            continue

        local_mean = float(masked[start:end].mean())
        peak_score = float(masked[peak])
        candidates.append(Cut(start=float(start), end=float(end), score=max(local_mean, peak_score)))

    candidates.sort(key=lambda cut: cut.score, reverse=True)

    selected: list[Cut] = []
    total = 0.0
    tolerance = 0.10
    target_low = target_duration * (1 - tolerance)

    for candidate in candidates:
        if max_cuts is not None and len(selected) >= max_cuts:
            break
        if total >= target_low:
            break

        overlap = False
        for previous in selected:
            intersection = max(0.0, min(candidate.end, previous.end) - max(candidate.start, previous.start))
            smaller = min(candidate.duration, previous.duration)
            if smaller > 0 and intersection / smaller > max_overlap:
                overlap = True
                break
        if overlap:
            continue

        remaining = target_duration - total
        duration = candidate.duration
        if duration > remaining:
            candidate = Cut(
                start=candidate.start,
                end=min(candidate.end, candidate.start + remaining),
                score=candidate.score,
            )
            duration = candidate.duration

        if duration < min_cut:
            continue
        selected.append(candidate)
        total += duration

    if selected:
        return sorted(selected, key=lambda cut: cut.start)
    return []
